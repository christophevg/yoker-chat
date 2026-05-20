# ChatClient API Design: Message Bridge Architecture

**Date**: 2026-05-20
**Status**: Final Design
**Related Task**: 1.3 ChatClient Class
**Reference**: [analysis/yoker-chat-client.md](/Users/xtof/Workspace/agentic/yoker-chat/analysis/yoker-chat-client.md)

## 1. Architecture Overview

The `ChatClient` bridges three components:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ChatClient                                      │
│                                                                             │
│  ┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐   │
│  │  Roomz           │      │  Message         │      │  Yoker           │   │
│  │  AsyncClient     │ ──── │  Queue &         │ ──── │  Agent           │   │
│  │                  │      │  Processor       │      │                  │   │
│  │  - WebSocket     │      │                  │      │  - process()     │   │
│  │  - send()        │      │  - Filter        │      │  - emit events   │   │
│  │  - on("message") │      │  - Queue         │      │                  │   │
│  └──────────────────┘      │  - Buffer       │      └──────────────────┘   │
│                            └──────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **Roomz AsyncClient** | Transport layer. Handles WebSocket connection, authentication, and raw message I/O. |
| **Message Queue & Processor** | Business logic layer. Filters messages, maintains processing order, buffers responses. |
| **Yoker Agent** | Intelligence layer. Processes messages, generates responses via events. |

---

## 2. Class Structure

### 2.1 Primary Async API (Async-First Design)

```python
# src/yoker_chat/client.py

from typing import Protocol, Any
import asyncio
import structlog

from roomz import AsyncClient as RoomzAsyncClient
from yoker import Agent

log = structlog.get_logger()


class AgentEventHandler(Protocol):
  """Protocol for agent event handlers."""
  def __call__(self, event: Any) -> None: ...


class ChatClient:
  """
  Bridges Roomz chat rooms to Yoker agents.
  
  Async-first design with internal message queue for sequential processing.
  """
  
  def __init__(
    self,
    server_url: str,
    agent: Agent,
    session_cache_path: str,
    *,
    name: str | None = None,
    mention_triggers: list[str] | None = None,
    respond_to_all: bool = False,
  ) -> None:
    self.server_url = server_url
    self.agent = agent
    self.name = name
    self.mention_triggers = mention_triggers or ["@bot"]
    self.respond_to_all = respond_to_all
    
    # Roomz client (transport layer)
    self.roomz_client = RoomzAsyncClient(server_url=server_url)
    
    # Session persistence
    self.cache = SessionCache(session_cache_path)
    
    # Message processing
    self._message_queue: asyncio.Queue[str] = asyncio.Queue()
    self._processing_lock = asyncio.Lock()
    self._response_buffer: list[str] = []
    
    # Worker task reference
    self._queue_worker: asyncio.Task | None = None
    self._running = False
    
    # Current user email (for filtering own messages)
    self._current_user_email: str | None = None

  async def start(self) -> None:
    """
    Start the client:
    1. Authenticate
    2. Register event handlers
    3. Start queue processor
    4. Connect to Roomz
    """
    self._running = True
    self._queue_worker = asyncio.create_task(self._process_queue())
    self._register_agent_handlers()
    self._register_roomz_handlers()
    await self.roomz_client.connect()
    
  async def stop(self) -> None:
    """
    Gracefully stop the client:
    1. Stop accepting new messages
    2. Wait for current message to complete
    3. Disconnect from Roomz
    """
    self._running = False
    if self._queue_worker:
      self._queue_worker.cancel()
      try:
        await self._queue_worker
      except asyncio.CancelledError:
        pass
    await self.roomz_client.disconnect()
```

### 2.2 Message Flow Architecture

```python
# Event flow: Roomz → ChatClient → Yoker Agent

async def _register_roomz_handlers(self) -> None:
  """Register handlers for Roomz client events."""
  self.roomz_client.on("message", self._on_roomz_message)
  self.roomz_client.on("authenticated", self._on_roomz_authenticated)
  self.roomz_client.on("disconnect", self._on_roomz_disconnect)

async def _register_agent_handlers(self) -> None:
  """Register handlers for Yoker agent events."""
  self.agent.add_event_handler("ContentChunk", self._on_agent_content_chunk)
  self.agent.add_event_handler("ContentEnd", self._on_agent_content_end)
  self.agent.add_event_handler("Error", self._on_agent_error)
```

---

## 3. Message Filtering

### 3.1 Filter Pipeline

Messages pass through a filter pipeline before being queued:

```
Incoming Message
       │
       ▼
┌──────────────────┐
│  Own Message?    │ ──── Yes ──▶ Discard
│  (same email)    │
└────────┬─────────┘
         │ No
         ▼
┌──────────────────┐
│  Mentioned?      │ ──── No ──▶ Discard (unless respond_to_all)
│  (check triggers)│
└────────┬─────────┘
         │ Yes
         ▼
┌──────────────────┐
│  Extract Message │ ──── Remove @mention
│  Clean content   │
└────────┬─────────┘
         │
         ▼
   Queue for Processing
```

### 3.2 Filter Implementation

```python
def _should_process_message(self, data: dict[str, Any]) -> bool:
  """
  Determine if a message should be processed.
  
  Filtering criteria:
  1. Must not be from the current user (prevent feedback loop)
  2. Must contain a mention trigger OR respond_to_all is enabled
  """
  # Extract sender email
  sender_email = data.get("user", {}).get("email", "")
  
  # Filter 1: Ignore own messages
  if sender_email == self._current_user_email:
    log.debug("filtered_own_message", sender=sender_email)
    return False
  
  # Filter 2: Check for mention trigger
  content = data.get("content", "")
  if self.respond_to_all:
    log.debug("processing_all_messages", sender=sender_email)
    return True
  
  # Check mention triggers
  if self._contains_mention(content):
    log.debug("message_mentioned", sender=sender_email, content_preview=content[:50])
    return True
  
  log.debug("filtered_unmentioned_message", sender=sender_email)
  return False


def _contains_mention(self, content: str) -> bool:
  """
  Check if content contains any mention trigger.
  
  Matching rules:
  - Case-insensitive
  - Word boundary check (prevents matching "@bot-user" when trigger is "@bot")
  """
  content_lower = content.lower()
  
  for trigger in self.mention_triggers:
    trigger_lower = trigger.lower()
    
    # Word boundary matching
    import re
    pattern = rf'\b{re.escape(trigger_lower)}\b'
    if re.search(pattern, content_lower):
      return True
  
  return False


def _extract_message(self, content: str) -> str:
  """
  Extract the actual message by removing mention triggers.
  
  Example:
    Input: "@bot What is the weather?"
    Output: "What is the weather?"
  """
  message = content
  
  for trigger in self.mention_triggers:
    # Remove trigger with surrounding whitespace
    import re
    pattern = rf'\s*{re.escape(trigger)}\s*'
    message = re.sub(pattern, ' ', message, flags=re.IGNORECASE)
  
  return message.strip()
```

---

## 4. Message Queue Design

### 4.1 Sequential Processing Requirement

The queue ensures messages are processed one at a time:

- **Context Integrity**: Yoker Agent maintains conversation context per turn
- **Response Ordering**: Responses match message order
- **Rate Limiting**: Natural backpressure on rapid message arrival

### 4.2 Queue Implementation

```python
async def _process_queue(self) -> None:
  """
  Worker coroutine that processes messages sequentially.
  
  This runs continuously while the client is active, pulling
  messages from the queue and processing them one at a time.
  """
  while self._running:
    try:
      # Wait for next message
      message = await asyncio.wait_for(
        self._message_queue.get(),
        timeout=1.0  # Periodic check for _running
      )
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


async def _on_roomz_message(self, data: dict[str, Any]) -> None:
  """
  Handle incoming Roomz message event.
  
  Filter and queue the message for processing.
  """
  # Log incoming message
  sender = data.get("user", {}).get("email", "unknown")
  content = data.get("content", "")
  log.info("message_received", sender=sender, content=content[:100])
  
  # Apply filter pipeline
  if not self._should_process_message(data):
    return
  
  # Extract clean message
  message = self._extract_message(content)
  
  # Queue for processing
  await self._message_queue.put(message)
  log.debug("message_queued", queue_size=self._message_queue.qsize())


async def _process_single_message(self, message: str) -> None:
  """
  Process a single message through the Yoker Agent.
  
  This method:
  1. Clears the response buffer
  2. Sends the message to the agent
  3. Waits for response completion (via ContentEnd event)
  4. Sends the buffered response to Roomz
  """
  log.info("processing_message", message_preview=message[:50])
  
  # Clear response buffer
  self._response_buffer.clear()
  
  # Create a future for response completion
  self._response_complete = asyncio.get_event_loop().create_future()
  
  # Process through agent (events will be captured by handlers)
  try:
    await self.agent.process(message)
    
    # Wait for ContentEnd event (with timeout)
    await asyncio.wait_for(self._response_complete, timeout=60.0)
  except asyncio.TimeoutError:
    log.warning("agent_timeout", message_preview=message[:50])
    await self._send_error_response("Response generation timed out")
  finally:
    self._response_complete = None
```

---

## 5. Agent Response Capture

### 5.1 Event Flow

```
Agent.process(message)
        │
        ├───── emits ──────▶ ContentChunkEvent
        │                         │
        │                         ▼
        │                    _on_agent_content_chunk()
        │                         │
        │                         ▼
        │                    Buffer: ["Hello", " there", "!"]
        │
        ├───── emits ──────▶ ContentEndEvent
        │                         │
        │                         ▼
        │                    _on_agent_content_end()
        │                         │
        │                         ▼
        │                    Join buffer + send()
        │
        └───── emits ──────▶ ErrorEvent (if failure)
```

### 5.2 Event Handlers

```python
def _on_agent_content_chunk(self, event: Any) -> None:
  """
  Handle ContentChunk events from the agent.
  
  Each chunk is appended to the response buffer.
  Chunks arrive in order during agent.process() execution.
  """
  chunk_text = event.text if hasattr(event, 'text') else str(event)
  self._response_buffer.append(chunk_text)
  log.debug("chunk_received", chunk_preview=chunk_text[:20])


def _on_agent_content_end(self, event: Any) -> None:
  """
  Handle ContentEnd event from the agent.
  
  This signals that the agent has finished generating content.
  The complete response is joined and sent to Roomz.
  """
  response = "".join(self._response_buffer)
  
  # Signal completion to waiting coroutine
  if self._response_complete and not self._response_complete.done():
    self._response_complete.set_result(response)
  
  log.info("response_complete", length=len(response))


def _on_agent_error(self, event: Any) -> None:
  """
  Handle Error events from the agent.
  
  Errors are logged and an error message is sent to the chat.
  """
  error_message = event.message if hasattr(event, 'message') else str(event)
  log.error("agent_error", error=error_message)
  
  # Signal completion with error
  if self._response_complete and not self._response_complete.done():
    self._response_complete.set_exception(AgentError(error_message))


async def _send_error_response(self, error_message: str) -> None:
  """Send an error message to the chat room."""
  user_friendly_message = f"❌ Error: {error_message}"
  await self.roomz_client.send(user_friendly_message)
  log.info("error_response_sent", error=error_message)
```

---

## 6. Response Buffering and Sending

### 6.1 Complete Response Flow

```python
async def _send_response(self, response: str) -> None:
  """
  Send a response to the Roomz chat room.
  
  Handles:
  - Empty responses (skip sending)
  - Long responses (split into chunks)
  - Connection failures (log and continue)
  """
  if not response.strip():
    log.debug("empty_response_skipped")
    return
  
  # TODO: Implement response splitting for long messages
  # if len(response) > MAX_MESSAGE_LENGTH:
  #   await self._send_chunked_response(response)
  #   return
  
  try:
    await self.roomz_client.send(response)
    log.info("response_sent", length=len(response), preview=response[:50])
  except Exception as e:
    log.error("send_failed", error=str(e))
```

### 6.2 Chunked Response (Future Enhancement)

For platforms with message length limits:

```python
MAX_MESSAGE_LENGTH = 2000  # Typical chat platform limit

async def _send_chunked_response(self, response: str) -> None:
  """
  Split a long response into multiple messages.
  
  Strategy:
  1. Split on paragraph boundaries
  2. If still too long, split on sentence boundaries
  3. If still too long, split on word boundaries
  """
  chunks = self._split_response(response, MAX_MESSAGE_LENGTH)
  
  for i, chunk in enumerate(chunks):
    await self.roomz_client.send(chunk)
    log.debug("chunk_sent", chunk_num=i+1, total=len(chunks))
    
    # Small delay to prevent rate limiting
    await asyncio.sleep(0.1)
```

---

## 7. State Management

### 7.1 Authentication State

Authentication state is managed by the existing implementation in `client.py` (Task 1.2).

### 7.2 Processing State

```python
@dataclass
class ClientState:
  """Immutable snapshot of client state."""
  running: bool
  authenticated: bool
  queue_size: int
  processing: bool  # Currently processing a message
  last_message_time: float | None
  last_response_time: float | None


@property
def state(self) -> ClientState:
  """Get current client state."""
  return ClientState(
    running=self._running,
    authenticated=self._current_user_email is not None,
    queue_size=self._message_queue.qsize(),
    processing=self._processing_lock.locked(),
    last_message_time=self._last_message_time,
    last_response_time=self._last_response_time,
  )
```

---

## 8. Error Handling

### 8.1 Error Categories and Responses

| Error Type | Source | Response Strategy |
|------------|--------|-------------------|
| **Agent Processing Error** | Yoker Agent | Log error, send user-friendly message to chat, continue |
| **Send Failure** | Roomz AsyncClient | Log error, retry once, continue |
| **Connection Lost** | Roomz AsyncClient | Log, trigger reconnection flow |
| **Timeout** | Agent processing | Send timeout message, continue |
| **Queue Overflow** | Internal | Drop oldest message, log warning |

### 8.2 Error Recovery

```python
async def _process_single_message(self, message: str) -> None:
  """Process with error recovery."""
  try:
    await self.agent.process(message)
    await asyncio.wait_for(self._response_complete, timeout=60.0)
  except asyncio.TimeoutError:
    log.warning("agent_timeout")
    await self._send_error_response("I'm taking too long to respond. Please try again.")
  except AgentError as e:
    log.error("agent_error", error=str(e))
    await self._send_error_response(f"Something went wrong: {str(e)}")
  except Exception as e:
    log.exception("unexpected_error")
    await self._send_error_response("An unexpected error occurred.")
```

---

## 9. Graceful Shutdown

### 9.1 Shutdown Sequence

```
SIGINT/SIGTERM
       │
       ▼
┌──────────────────┐
│ stop() called    │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ _running = False │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Cancel queue     │ ──── Stop accepting new messages
│ worker           │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Wait for current │ ──── If processing lock held, wait
│ message to finish│
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Drain queue      │ ──── Optionally log remaining
│ (optional)       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Disconnect from  │
│ Roomz            │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Exit clean       │
└──────────────────┘
```

### 9.2 Shutdown Implementation

```python
async def stop(self) -> None:
  """
  Gracefully stop the client.
  
  Guarantees:
  - No new messages are accepted
  - Current message processing completes
  - Connection is cleanly closed
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
```

---

## 10. Configuration

### 10.1 Configuration Parameters

```python
@dataclass
class ChatClientConfig:
  """Configuration for ChatClient."""
  
  # Identity
  display_name: str | None = None
  mention_triggers: list[str] = field(default_factory=lambda: ["@bot"])
  
  # Behavior
  respond_to_all: bool = False
  max_response_length: int = 2000
  
  # Timeouts
  agent_timeout_seconds: float = 60.0
  connection_timeout_seconds: float = 30.0
  
  # Rate limiting
  min_response_interval_ms: int = 1000
  max_responses_per_minute: int = 10
```

### 10.2 Configuration Loading

```toml
# yoker-chat.toml

[behavior]
respond_to_all = false
mention_triggers = ["@assistant", "@bot", "@help"]
max_response_length = 2000
agent_timeout_seconds = 60.0

[rate_limiting]
min_response_interval_ms = 1000
max_responses_per_minute = 10
```

---

## 11. Integration Points

### 11.1 Roomz AsyncClient API

The ChatClient interacts with Roomz AsyncClient through:

| Method | Purpose |
|--------|---------|
| `connect(cookie=...)` | Establish WebSocket connection |
| `disconnect()` | Close connection |
| `send(message)` | Send message to chat room |
| `on(event, handler)` | Register event handler |
| `set_name(name)` | Set display name |
| `login(email)` | Request magic link |
| `user` | Property with current user info |

### 11.2 Yoker Agent API

The ChatClient interacts with Yoker Agent through:

| Method | Purpose |
|--------|---------|
| `process(message)` | Process a message |
| `add_event_handler(event, handler)` | Register event handler |

### 11.3 Agent Events

| Event | When Fired | Handler Action |
|-------|------------|----------------|
| `ContentChunk` | Each chunk of generated text | Append to buffer |
| `ContentEnd` | Agent finished generating | Send buffered response |
| `Error` | Agent encountered error | Send error message |
| `ThinkingStart` | Agent starts thinking | (Optional) Send status |
| `ThinkingEnd` | Agent stops thinking | (Optional) Clear status |
| `ToolCall` | Agent uses tool | (Optional) Send status |

---

## 12. Testing Strategy

### 12.1 Unit Tests

| Test | Description |
|------|-------------|
| `_should_process_message` | Test own message filtering, mention detection |
| `_contains_mention` | Test word boundary matching, case insensitivity |
| `_extract_message` | Test mention removal, whitespace handling |
| `_send_error_response` | Test error message formatting |

### 12.2 Integration Tests

| Test | Description |
|------|-------------|
| Message flow | Mock Roomz → ChatClient → Mock Agent |
| Response capture | Agent events → buffer → Roomz send |
| Queue processing | Sequential message processing |
| Error recovery | Agent errors, connection failures |

### 12.3 Test Helpers

```python
# tests/conftest.py

@pytest.fixture
def mock_roomz_client():
  """Create a mock Roomz AsyncClient."""
  client = AsyncMock(spec=AsyncClient)
  client.user = {"email": "bot@example.com"}
  return client

@pytest.fixture
def mock_agent():
  """Create a mock Yoker Agent."""
  agent = AsyncMock(spec=Agent)
  return agent

@pytest.fixture
def chat_client(mock_roomz_client, mock_agent, tmp_path):
  """Create a ChatClient with mocked dependencies."""
  return ChatClient(
    server_url="http://localhost:5000",
    agent=mock_agent,
    session_cache_path=str(tmp_path / "session.json"),
    name="TestBot",
    mention_triggers=["@bot"],
  )
```

---

## 13. Implementation Checklist

### Phase 1: Core Functionality

- [ ] Implement `_register_roomz_handlers()`
- [ ] Implement `_register_agent_handlers()`
- [ ] Implement message filtering (`_should_process_message`, `_contains_mention`, `_extract_message`)
- [ ] Implement message queue (`_message_queue`, `_process_queue`, `_on_roomz_message`)
- [ ] Implement response capture (`_on_agent_content_chunk`, `_on_agent_content_end`)
- [ ] Implement response sending (`_send_response`)

### Phase 2: Error Handling

- [ ] Implement `_on_agent_error`
- [ ] Implement `_send_error_response`
- [ ] Add timeout handling in `_process_single_message`
- [ ] Add connection error recovery

### Phase 3: Graceful Shutdown

- [ ] Implement graceful `stop()` method
- [ ] Add signal handlers for SIGINT/SIGTERM
- [ ] Ensure current message completes before exit

### Phase 4: Configuration

- [ ] Add `ChatClientConfig` dataclass
- [ ] Load configuration from TOML
- [ ] Add command-line argument support

---

## 14. Future Enhancements

### 14.1 Streaming Responses

Instead of buffering the complete response, stream chunks directly to the chat:

```python
def _on_agent_content_chunk(self, event: Any) -> None:
  """Stream chunks directly to chat."""
  if self._streaming_enabled:
    asyncio.create_task(self.roomz_client.send(event.text))
  else:
    self._response_buffer.append(event.text)
```

### 14.2 Rate Limiting

Implement rate limiting to prevent spam:

```python
class RateLimiter:
  """Token bucket rate limiter."""
  
  def __init__(self, max_per_minute: int = 10):
    self.max_per_minute = max_per_minute
    self.tokens = max_per_minute
    self.last_refill = time.time()
  
  async def acquire(self) -> bool:
    """Try to acquire a token. Returns True if allowed."""
    now = time.time()
    elapsed = now - self.last_refill
    
    # Refill tokens
    self.tokens = min(
      self.max_per_minute,
      self.tokens + elapsed * (self.max_per_minute / 60.0)
    )
    self.last_refill = now
    
    if self.tokens >= 1:
      self.tokens -= 1
      return True
    return False
```

### 14.3 Typing Indicators

Show "typing" status while processing:

```python
async def _process_single_message(self, message: str) -> None:
  await self.roomz_client.set_typing(True)
  try:
    # ... process message ...
  finally:
    await self.roomz_client.set_typing(False)
```

---

## 15. Dependencies

### Required Packages

| Package | Version | Purpose |
|---------|---------|---------|
| `roomz` | `>=0.1.0` | Roomz AsyncClient |
| `yoker` | `>=0.1.0` | Agent engine |
| `structlog` | `>=23.0.0` | Structured logging |
| `asyncio` | stdlib | Async runtime |

### Optional Packages

| Package | Version | Purpose |
|---------|---------|---------|
| `rich` | `>=14.0.0` | Console formatting |

---

## 16. Security Considerations

### 16.1 Message Filtering

- **Own Message Filtering**: Prevents feedback loops
- **Mention Validation**: Prevents responding to malformed patterns
- **Rate Limiting**: Prevents spam/DoS from bot

### 16.2 Agent Capabilities

- Agent has limited tools (defined in agent definition)
- Path guardrails prevent unauthorized file access
- Web guardrails prevent SSRF attacks

### 16.3 Error Messages

- User-friendly error messages don't expose internal details
- Errors are logged with full details for debugging
- Sensitive data (tokens, sessions) are redacted in logs