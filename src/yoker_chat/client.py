"""Chat client that bridges Roomz to Yoker Agent."""

import asyncio
import getpass
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import structlog
from roomz import AsyncClient

log = structlog.get_logger().bind(component="chat-client")


class AuthenticationError(Exception):
  """Base exception for authentication failures."""

  pass


class AgentError(Exception):
  """Exception raised when agent processing fails."""

  pass


class RateLimiter:
  """Per-user rate limiter for message processing."""

  def __init__(self, max_messages: int = 10, window_seconds: int = 60):
    """
    Initialize rate limiter.

    Args:
      max_messages: Maximum messages allowed per user in the window
      window_seconds: Time window in seconds
    """
    self.max_messages = max_messages
    self.window = timedelta(seconds=window_seconds)
    self._user_messages: dict[str, list[datetime]] = defaultdict(list)

  def is_allowed(self, user_id: str) -> bool:
    """
    Check if user is allowed to send a message.

    Args:
      user_id: User identifier (e.g., email)

    Returns:
      True if allowed, False if rate limited
    """
    now = datetime.now()
    messages = self._user_messages[user_id]

    # Filter out old messages
    messages[:] = [t for t in messages if now - t < self.window]

    if len(messages) >= self.max_messages:
      log.warning("rate_limited", user=user_id, messages=len(messages))
      return False

    messages.append(now)
    return True


class ChatClient:
  """
  Main client for Yoker Chat.

  Bridges Roomz chat rooms to Yoker agents, handling:
  - Message filtering (own messages, mentions)
  - Message queue for sequential processing
  - Agent response capture and buffering
  - Rate limiting and security guardrails
  """

  def __init__(
    self,
    server_url: str,
    agent: Any,
    session_cache_path: str,
    *,
    name: str | None = None,
    mention_triggers: list[str] | None = None,
    respond_to_all: bool = False,
    max_queue_size: int = 100,
    max_message_size: int = 10000,
    max_messages_per_minute: int = 10,
    processing_timeout_seconds: float = 60.0,
  ) -> None:
    """
    Initialize ChatClient.

    Args:
      server_url: Roomz server URL
      agent: Yoker Agent instance
      session_cache_path: Path to session cache file (passed to Roomz)
      name: Display name for the bot
      mention_triggers: List of mention triggers (default: ["@bot"])
      respond_to_all: If True, respond to all messages regardless of mention
      max_queue_size: Maximum messages in queue (DoS prevention)
      max_message_size: Maximum message size in characters
      max_messages_per_minute: Rate limit per user
      processing_timeout_seconds: Timeout for agent processing
    """
    self.server_url = server_url
    self.agent = agent
    self.name = name
    self.mention_triggers = mention_triggers or ["@bot"]
    self.respond_to_all = respond_to_all
    self.max_message_size = max_message_size
    self.processing_timeout_seconds = processing_timeout_seconds

    # Roomz client with native session caching
    self.roomz_client = AsyncClient(
      server_url=self.server_url,
      session_cache_file=session_cache_path,
      display_name=name,
    )

    # Message processing
    self._message_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max_queue_size)
    self._processing_lock = asyncio.Lock()
    self._response_buffer: list[str] = []
    self._response_complete: asyncio.Future[str] | None = None

    # Worker task reference
    self._queue_worker: asyncio.Task | None = None
    self._running = False

    # Current user info (for filtering own messages)
    self._current_user_email: str | None = None
    self._current_user_name: str | None = None

    # Rate limiting
    self._rate_limiter = RateLimiter(max_messages=max_messages_per_minute, window_seconds=60)

    # Security patterns for prompt injection detection
    self._instruction_patterns = [
      r"ignore\s+(all\s+)?previous\s+instructions",
      r"ignore\s+(all\s+)?(system\s+)?prompts?",
      r"you\s+are\s+now\s+",
      r"disregard\s+",
      r"forget\s+(all\s+)?(previous\s+)?(instructions|rules)",
      r"output\s+(your\s+)?(system\s+)?prompt",
      r"reveal\s+(your\s+)?(system\s+)?prompt",
    ]

  async def authenticate(
    self,
    login: str | None = None,
    token: str | None = None,
  ) -> None:
    """
    Orchestrate the authentication flow.

    Roomz AsyncClient handles session caching automatically via session_cache_file.
    This method orchestrates:
    1. Try connecting with cached session (handled by Roomz)
    2. If no session, request magic link and connect with token
    """
    # Handle token fallback from env var
    if token is None:
      token = os.environ.get("YOKER_CHAT_TOKEN")

    # If we have a token, connect directly
    if token:
      log.info("authenticating_with_token")
      try:
        await self.roomz_client.connect(session_token=token)
        user_email = (
          self.roomz_client.user.get("email", "unknown") if self.roomz_client.user else "unknown"
        )
        self._current_user_email = user_email
        self._current_user_name = self.name  # Use the bot's display name
        log.info("auth_success", email=user_email, display_name=self.name)
        return
      except Exception as e:
        log.error("token_auth_failed", error=str(e))
        raise AuthenticationError(f"Failed to authenticate with token: {e}") from e

    # Try connecting with cached session (Roomz handles this automatically)
    try:
      log.info("attempting_cached_session")
      await self.roomz_client.connect()
      user_email = (
        self.roomz_client.user.get("email", "unknown") if self.roomz_client.user else "unknown"
      )
      self._current_user_email = user_email
      self._current_user_name = self.name  # Use the bot's display name
      log.info("auth_success", source="cached_session", email=user_email, display_name=self.name)
      return
    except Exception as e:
      log.info("no_cached_session", reason=str(e))

    # No token and no cached session - interactive flow
    login = self._prompt_for_email()
    await self._request_magic_link(login)
    token = self._prompt_for_token()

    try:
      await self.roomz_client.connect(session_token=token)
      self._current_user_email = login
      self._current_user_name = self.name  # Use the bot's display name
      log.info("auth_success", source="interactive", email=login, display_name=self.name)
    except Exception as e:
      log.error("connection_failed", token="[REDACTED]", error=str(e))
      raise AuthenticationError(f"Failed to connect with token: {e}") from e

  async def _request_magic_link(self, email: str) -> None:
    """Request a magic link from the server."""
    log.info("requesting_magic_link", email=email)
    result = await self.roomz_client.login(email)
    if isinstance(result, dict) and "error" in result:
      log.error("magic_link_failed", email=email, error=result["error"])
      raise AuthenticationError(result["error"])
    log.info("magic_link_sent", email=email)

  def _prompt_for_email(self) -> str:
    """Prompt for email address."""
    while True:
      email = input("Enter your email address: ").strip()
      if email:
        return email

  def _prompt_for_token(self) -> str:
    """Prompt for magic link token using getpass to prevent echo."""
    while True:
      print("Check your email and paste the token:")
      token = getpass.getpass("> ")
      if token:
        return token.strip()

  async def start(self) -> None:
    """
    Start the client:
    1. Authenticate
    2. Register event handlers
    3. Start queue processor
    """
    self._running = True
    self._queue_worker = asyncio.create_task(self._process_queue())
    self._register_roomz_handlers()
    self._register_agent_handlers()

  async def stop(self) -> None:
    """
    Gracefully stop the client:
    1. Stop accepting new messages
    2. Wait for current message to complete
    3. Disconnect from Roomz
    """
    log.info("shutting_down")

    # Stop accepting new messages
    self._running = False

    # Cancel queue worker
    if self._queue_worker:
      self._queue_worker.cancel()
      try:
        await self._queue_worker
      except asyncio.CancelledError:
        pass

    # Wait for current processing to complete
    if self._processing_lock.locked():
      log.info("waiting_for_processing")
      async with self._processing_lock:
        pass  # Just wait for lock to be released

    # Disconnect from Roomz
    try:
      await self.roomz_client.disconnect()
    except Exception as e:
      log.warning("disconnect_failed", error=str(e))

    log.info("shutdown_complete")

  async def disconnect(self) -> None:
    """Disconnect from the server."""
    await self.stop()

  def _register_roomz_handlers(self) -> None:
    """Register handlers for Roomz client events."""
    self.roomz_client.on("message", self._on_roomz_message)
    self.roomz_client.on("authenticated", self._on_roomz_authenticated)
    self.roomz_client.on("disconnect", self._on_roomz_disconnect)

  def _register_agent_handlers(self) -> None:
    """Register handlers for Yoker agent events.

    Yoker Agent's add_event_handler takes a single handler that receives
    ALL events. The handler must filter by event type using isinstance().
    """
    if hasattr(self.agent, "add_event_handler"):
      # Import event types for filtering
      from yoker.events import ContentChunkEvent, ContentEndEvent, ErrorEvent

      def event_handler(event: Any) -> None:
        """Dispatch events to appropriate handlers based on type."""
        if isinstance(event, ContentChunkEvent):
          self._on_agent_content_chunk(event)
        elif isinstance(event, ContentEndEvent):
          self._on_agent_content_end(event)
        elif isinstance(event, ErrorEvent):
          self._on_agent_error(event)

      self.agent.add_event_handler(event_handler)

  # =========================================================================
  # Message Filtering
  # =========================================================================

  def _should_process_message(self, data: dict[str, Any]) -> bool:
    """
    Determine if a message should be processed.

    Filtering criteria:
    1. Must not be from the current user (prevent feedback loop)
    2. Must contain a mention trigger OR respond_to_all is enabled
    3. Must pass rate limiting check

    Args:
      data: Message data from Roomz

    Returns:
      True if message should be processed, False otherwise
    """
    # Extract sender email
    sender_email = data.get("user", {}).get("email", "")

    # Filter 1: Ignore own messages (by display name only)
    sender_name = data.get("user", {}).get("display_name") or data.get("user", {}).get("name", "")
    if self._current_user_name and sender_name and sender_name == self._current_user_name:
      log.info("filtered_own_message", sender_name=sender_name, bot_name=self._current_user_name)
      return False

    # Filter 2: Rate limiting
    if sender_email and not self._rate_limiter.is_allowed(sender_email):
      log.warning("rate_limited_user", sender=sender_email)
      return False

    # Filter 3: Check for mention trigger
    content = data.get("content", "")
    if self.respond_to_all:
      log.info("processing_all_messages", sender=sender_email)
      return True

    # Check mention triggers
    if self._contains_mention(content):
      log.info("message_mentioned", sender=sender_email, content_preview=content[:50])
      return True

    log.info("filtered_unmentioned_message", sender=sender_email, content_preview=content[:50])
    return False

  def _contains_mention(self, content: str) -> bool:
    """
    Check if content contains any mention trigger.

    Matching rules:
    - Case-insensitive
    - Must be followed by whitespace, punctuation, or end of string
    - Does NOT match if followed by hyphen or other word-continuation characters
    - Prevents matching "@bot-user" when trigger is "@bot"

    Args:
      content: Message content to check

    Returns:
      True if a mention is found, False otherwise
    """
    normalized = self._normalize_message(content)

    for trigger in self.mention_triggers:
      trigger_lower = trigger.lower()
      # Match trigger followed by: whitespace, end of string, or punctuation (not hyphen)
      # This prevents "@bot-user" from matching "@bot"
      # Pattern: trigger followed by (whitespace | end | punctuation except hyphen)
      pattern = rf"{re.escape(trigger_lower)}(?:\s|$|[!\"#$%&\'()*+,./:;<=>?@\[\\\]^_`{{|}}~])"
      if re.search(pattern, normalized):
        return True

    return False

  def _normalize_message(self, content: str) -> str:
    """
    Normalize message for mention detection.

    Applies:
    - Unicode NFC normalization
    - Zero-width character removal
    - Lowercase conversion

    Args:
      content: Message content to normalize

    Returns:
      Normalized content
    """
    # Unicode NFC normalization
    normalized = unicodedata.normalize("NFC", content)
    # Remove zero-width characters
    normalized = re.sub(r"[​-‏ - ﻿]", "", normalized)
    return normalized.lower()

  def _extract_message(self, content: str) -> str:
    """
    Extract the actual message by removing mention triggers and sanitizing.

    Security operations:
    - Remove mention triggers
    - Strip control characters
    - Enforce message size limit

    Args:
      content: Raw message content

    Returns:
      Cleaned message content
    """
    message = content

    # Remove mention triggers
    for trigger in self.mention_triggers:
      # Remove trigger with surrounding whitespace
      pattern = rf"\s*{re.escape(trigger)}\s*"
      message = re.sub(pattern, " ", message, flags=re.IGNORECASE)

    # Strip control characters (security: prevents log injection, terminal manipulation)
    message = self._strip_control_characters(message)

    # Enforce size limit
    if len(message) > self.max_message_size:
      truncation_suffix = "... [truncated]"
      max_content_size = self.max_message_size - len(truncation_suffix)
      log.warning("message_too_large", size=len(message), limit=self.max_message_size)
      message = message[:max_content_size] + truncation_suffix

    return message.strip()

  def _strip_control_characters(self, text: str) -> str:
    """
    Strip control characters from text.

    Removes:
    - Null bytes
    - ANSI escape sequences
    - Other control characters (except newlines/tabs)

    Args:
      text: Text to sanitize

    Returns:
      Sanitized text
    """
    # Remove null bytes
    text = text.replace("\x00", "")
    # Remove ANSI escape sequences (replace with space to preserve word boundaries)
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", " ", text)
    # Remove other control characters (except newline, tab, carriage return)
    text = "".join(char for char in text if char >= " " or char in "\n\t\r")
    return text

  def _contains_instruction_override(self, message: str) -> bool:
    """
    Check if message contains potential prompt injection patterns.

    Args:
      message: Message to check

    Returns:
      True if suspicious pattern found, False otherwise
    """
    normalized = message.lower()
    for pattern in self._instruction_patterns:
      if re.search(pattern, normalized):
        return True
    return False

  # =========================================================================
  # Message Queue Processing
  # =========================================================================

  async def _process_queue(self) -> None:
    """
    Worker coroutine that processes messages sequentially.

    This runs continuously while the client is active, pulling
    messages from the queue and processing them one at a time.
    """
    while self._running:
      try:
        # Wait for next message with timeout to check _running
        try:
          message = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
          continue

        # Process with lock to ensure sequential execution
        async with self._processing_lock:
          try:
            await self._process_single_message(message)
          except Exception as e:
            log.error("message_processing_failed", error=str(e))
            # Send error message to chat
            await self._send_error_response(str(e))
          finally:
            self._message_queue.task_done()

      except asyncio.CancelledError:
        log.info("queue_worker_cancelled")
        break
      except Exception as e:
        log.exception("queue_worker_error", error=str(e))
        # Continue processing despite errors

  async def _on_roomz_message(self, data: dict[str, Any]) -> None:
    """
    Handle incoming Roomz message event.

    Filter and queue the message for processing.

    Args:
      data: Message data from Roomz
    """
    if not self._running:
      return

    # Log incoming message
    sender_email = data.get("user", {}).get("email", "unknown")
    sender_name = data.get("user", {}).get("name", data.get("user", {}).get("display_name", ""))
    content = data.get("content", "")
    log.info(
      "message_received",
      sender_email=sender_email,
      sender_name=sender_name,
      content=content[:100],
      bot_email=self._current_user_email,
      bot_name=self._current_user_name,
    )

    # Apply filter pipeline
    if not self._should_process_message(data):
      return

    # Extract clean message
    message = self._extract_message(content)

    # Queue for processing
    try:
      self._message_queue.put_nowait(message)
      log.info("message_queued", queue_size=self._message_queue.qsize(), message_preview=message[:50])
    except asyncio.QueueFull:
      log.warning("queue_full", action="dropping_message")
      # Optionally send feedback to user

  async def _process_single_message(self, message: str) -> None:
    """
    Process a single message through the Yoker Agent.

    This method:
    1. Clears the response buffer
    2. Checks for prompt injection
    3. Sends the message to the agent
    4. Waits for response completion (via ContentEnd event)
    5. Sends the buffered response to Roomz

    Args:
      message: Cleaned message content
    """
    log.info("processing_message", message_preview=message[:50])

    # Check for prompt injection
    if self._contains_instruction_override(message):
      log.warning("potential_prompt_injection", message_preview=message[:50])

    # Clear response buffer
    self._response_buffer.clear()

    # Create a future for response completion
    self._response_complete = asyncio.get_event_loop().create_future()

    # Process through agent (events will be captured by handlers)
    # Note: Yoker Agent's process() is synchronous and emits events during processing.
    # For async mocks in tests, we handle both sync and async process methods.
    try:
      # Check if process is a coroutine function (for async mocks)
      if asyncio.iscoroutinefunction(self.agent.process):
        # Async mock (used in tests)
        await asyncio.wait_for(self.agent.process(message), timeout=self.processing_timeout_seconds)
      else:
        # Sync process (real Yoker Agent) - run in thread pool to not block asyncio
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
          loop.run_in_executor(None, self.agent.process, message),
          timeout=self.processing_timeout_seconds,
        )

      # Wait for ContentEnd event and get the response
      response = await asyncio.wait_for(self._response_complete, timeout=self.processing_timeout_seconds)

      # Send the response to the chat
      log.info("sending_response", length=len(response), preview=response[:100])
      await self._send_response(response)
    except asyncio.TimeoutError:
      log.warning("agent_timeout", message_preview=message[:50])
      await self._send_error_response("I'm taking too long to respond. Please try again.")
    except AgentError as e:
      log.error("agent_error", error=str(e))
      await self._send_error_response("Something went wrong processing your message.")
    except Exception:
      log.exception("unexpected_error")
      await self._send_error_response("An unexpected error occurred.")
    finally:
      self._response_complete = None

  # =========================================================================
  # Agent Response Capture
  # =========================================================================

  def _on_agent_content_chunk(self, event: Any) -> None:
    """
    Handle ContentChunk events from the agent.

    Each chunk is appended to the response buffer.
    Chunks arrive in order during agent.process() execution.

    Args:
      event: ContentChunk event from agent
    """
    chunk_text = event.text if hasattr(event, "text") else str(event)
    self._response_buffer.append(chunk_text)
    log.debug("chunk_received", chunk_preview=chunk_text[:20])

  def _on_agent_content_end(self, event: Any) -> None:
    """
    Handle ContentEnd event from the agent.

    This signals that the agent has finished generating content.
    The complete response is joined and a future is resolved.

    Args:
      event: ContentEnd event from agent
    """
    response = "".join(self._response_buffer)
    log.info("response_complete", length=len(response))

    # Signal completion to waiting coroutine
    if self._response_complete and not self._response_complete.done():
      self._response_complete.set_result(response)

  def _on_agent_error(self, event: Any) -> None:
    """
    Handle Error events from the agent.

    Errors are logged and an error message is sent to the chat.

    Args:
      event: Error event from agent
    """
    error_message = event.message if hasattr(event, "message") else str(event)
    log.error("agent_error", error=error_message)

    # Signal completion with error
    if self._response_complete and not self._response_complete.done():
      self._response_complete.set_exception(AgentError(error_message))

  async def _send_response(self, response: str) -> None:
    """
    Send a response to the Roomz chat room.

    Handles:
    - Empty responses (skip sending)
    - Connection failures (log and continue)

    Args:
      response: Response content to send
    """
    if not response.strip():
      log.debug("empty_response_skipped")
      return

    try:
      await self.roomz_client.send(response)
      log.info("response_sent", length=len(response), preview=response[:50])
    except Exception as e:
      log.error("send_failed", error=str(e))

  async def _send_error_response(self, error_message: str) -> None:
    """
    Send a user-friendly error message to the chat room.

    Args:
      error_message: Technical error message (not shown to users)
    """
    user_friendly_message = "I encountered an error processing your message. Please try again."
    await self.roomz_client.send(user_friendly_message)
    log.info("error_response_sent", error=error_message)

  # =========================================================================
  # Roomz Event Handlers
  # =========================================================================

  async def _on_roomz_authenticated(self, data: dict[str, Any]) -> None:
    """Handle authenticated event from Roomz."""
    user = data.get("user", {})
    self._current_user_email = user.get("email")
    log.info("roomz_authenticated", email=self._current_user_email)

  async def _on_roomz_disconnect(self, data: dict[str, Any]) -> None:
    """Handle disconnect event from Roomz."""
    log.warning("roomz_disconnected", data=data)
