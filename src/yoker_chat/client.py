"""Chat client that bridges Roomz to Yoker Agent."""

import asyncio
import getpass
import os
import structlog
from typing import Any

from roomz import AsyncClient
from yoker_chat.session import SessionCache

log = structlog.get_logger()

class AuthenticationError(Exception):
  """Base exception for authentication failures."""
  pass

class ChatClient:
  """Main client for Yoker Chat."""

  def __init__(
    self,
    server_url: str,
    agent: Any, # Using Any for Agent as it's defined in another module
    session_cache_path: str,
    name: str | None = None,
  ) -> None:
    self.server_url = server_url
    self.agent = agent
    self.cache = SessionCache(session_cache_path)
    self.name = name
    self.roomz_client = AsyncClient(server_url=self.server_url)

  async def authenticate(
    self,
    login: str | None = None,
    token: str | None = None,
  ) -> None:
    """
    Orchestrate the authentication flow.
    Supports cached sessions, CLI arguments, and interactive prompts.
    """
    # 1. Try cached session
    cached_data = self.cache.load()
    if cached_data:
      session_info = cached_data.get("session")
      if session_info:
        log.info("attempting_cached_reconnect", email=session_info.get("email"))
        try:
          await self.roomz_client.connect(cookie=session_info.get("cookie"))
          log.info("auth_success", source="cached_session", email=session_info.get("email"))
          await self._set_display_name()
          return
        except Exception as e:
          log.warning("cached_session_invalid", error=str(e))
          self.cache.clear()

    # 2. Handle token fallback from env var
    if token is None:
      token = os.environ.get("YOKER_CHAT_TOKEN")

    # 3. Interactive or Non-Interactive Flow
    if login and token:
      # Non-interactive: both provided
      log.info("authenticating", email=login)
      await self._connect_with_token(token)
      log.info("auth_success", email=login)
    elif login:
      # Partial non-interactive: only email provided, need token
      await self._request_magic_link(login)
      token = self._prompt_for_token()
      await self._connect_with_token(token)
      log.info("auth_success", email=login)
    else:
      # Full interactive
      login = self._prompt_for_email()
      await self._request_magic_link(login)
      token = self._prompt_for_token()
      await self._connect_with_token(token)
      log.info("auth_success", email=login)

    await self._set_display_name()

  async def _request_magic_link(self, email: str) -> None:
    """Request a magic link from the server."""
    log.info("requesting_magic_link", email=email)
    result = await self.roomz_client.login(email)
    if isinstance(result, dict) and "error" in result:
      log.error("magic_link_failed", email=email, error=result["error"])
      raise AuthenticationError(result["error"])
    log.info("magic_link_sent", email=email)

  async def _connect_with_token(self, token: str) -> None:
    """Connect to the server using a magic link token."""
    try:
      await self.roomz_client.connect(session_token=token)
      # Save session on successful connect
      user_email = self.roomz_client.user.get("email", "unknown")
      cookie = getattr(self.roomz_client, "_cached_cookie", None)
      self.cache.save(session_cookie=cookie, server_url=self.server_url, email=user_email)
    except Exception as e:
      log.error("connection_failed", token="[REDACTED]", error=str(e))
      raise AuthenticationError(f"Failed to connect with token: {e}")

  async def _set_display_name(self) -> None:
    """Set the bot's display name if provided."""
    if self.name:
      log.info("setting_display_name", name=self.name)
      await self.roomz_client.set_name(self.name)

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

  async def disconnect(self) -> None:
    """Disconnect from the server."""
    await self.roomz_client.disconnect()
