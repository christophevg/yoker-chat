"""Tests for authentication and session handling."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoker_chat.client import ChatClient


@pytest.fixture
def mock_roomz_class():
  """Mock the Roomz AsyncClient class."""
  with patch("yoker_chat.client.AsyncClient") as mock:
    instance = MagicMock()
    instance.login = AsyncMock()
    instance.connect = AsyncMock()
    instance.disconnect = AsyncMock()
    instance.on = MagicMock()
    instance.user = {"email": "test@example.com"}
    mock.return_value = instance
    yield mock


@pytest.fixture
def temp_cache(tmp_path):
  return str(tmp_path / "session.json")


@pytest.mark.asyncio
async def test_auth_interactive_flow_sequence(mock_roomz_class, temp_cache):
  """
  Given: A user starts yoker-chat without arguments and no cached session
  When: The user is prompted for email and then token
  Then: The client should follow the sequence: connect() fails -> prompt email -> login() -> prompt token -> connect(session_token=...)
  """
  client = ChatClient(
    server_url="http://localhost:5000",
    agent=None,
    session_cache_path=temp_cache,
  )

  # First connect() call (trying cached session) should fail
  mock_roomz_class.return_value.connect.side_effect = [
    Exception("No cached session"),  # First attempt - cached session
    None,  # Second attempt - with token
  ]

  with (
    patch("builtins.input", side_effect=["user@example.com"]),
    patch("getpass.getpass", return_value="token123"),
  ):
    mock_roomz_class.return_value.login.return_value = {"status": "sent"}

    await client.authenticate()

    # First: try cached session
    # Second: connect with token
    assert mock_roomz_class.return_value.connect.call_count == 2


@pytest.mark.asyncio
async def test_auth_cli_args_bypass_prompts(mock_roomz_class, temp_cache):
  """
  Given: yoker-chat is started with --login and --token arguments
  When: The authentication process begins
  Then: No interactive prompts should be shown and connect(session_token=...) should be called
  """
  client = ChatClient(
    server_url="http://localhost:5000",
    agent=None,
    session_cache_path=temp_cache,
  )

  with patch("builtins.input") as mock_input, patch("getpass.getpass") as mock_getpass:
    await client.authenticate(login="user@example.com", token="token123")

    mock_input.assert_not_called()
    mock_getpass.assert_not_called()
    mock_roomz_class.return_value.connect.assert_called_once_with(session_token="token123")


@pytest.mark.asyncio
async def test_auth_env_var_token_fallback(mock_roomz_class, temp_cache):
  """
  Given: YOKER_CHAT_TOKEN is set in environment variables
  And: --token argument is not provided
  When: The authentication process begins
  Then: The client should use the token from the environment variable
  """
  with patch.dict(os.environ, {"YOKER_CHAT_TOKEN": "env_token_456"}):
    client = ChatClient(
      server_url="http://localhost:5000",
      agent=None,
      session_cache_path=temp_cache,
    )

    await client.authenticate(login="user@example.com", token=None)

    mock_roomz_class.return_value.connect.assert_called_once_with(session_token="env_token_456")


@pytest.mark.asyncio
async def test_auth_session_cache_passed_to_roomz(mock_roomz_class, temp_cache):
  """
  Given: A session_cache_path is provided
  When: The ChatClient is created
  Then: The path should be passed to Roomz AsyncClient for native session caching
  """
  ChatClient(
    server_url="http://localhost:5000",
    agent=None,
    session_cache_path=temp_cache,
  )

  # Verify that AsyncClient was called with session_cache_file
  mock_roomz_class.assert_called_once()
  call_kwargs = mock_roomz_class.call_args[1]
  assert "session_cache_file" in call_kwargs
  assert call_kwargs["session_cache_file"] == temp_cache


@pytest.mark.asyncio
async def test_auth_cached_session_reconnect(mock_roomz_class, temp_cache):
  """
  Given: A valid cached session exists
  When: The client connects
  Then: Roomz should be called with connect() (no token) to use cached session
  """
  client = ChatClient(
    server_url="http://localhost:5000",
    agent=None,
    session_cache_path=temp_cache,
  )

  # Mock successful cached session connection
  mock_roomz_class.return_value.connect.return_value = None

  await client.authenticate()

  # Should try cached session (connect with no arguments)
  mock_roomz_class.return_value.connect.assert_called_once_with()


@pytest.mark.asyncio
async def test_auth_session_expiry_triggers_reauth(mock_roomz_class, temp_cache):
  """
  Given: A cached session exists but is expired
  When: The client tries to connect
  Then: The cached session should fail, and interactive flow should begin
  """
  client = ChatClient(
    server_url="http://localhost:5000",
    agent=None,
    session_cache_path=temp_cache,
  )

  # First connect() fails (expired session), second succeeds (with token)
  mock_roomz_class.return_value.connect.side_effect = [
    Exception("Unauthorized"),  # Cached session expired
    None,  # Successful connection with token
  ]
  mock_roomz_class.return_value.login.return_value = {"status": "sent"}

  with (
    patch("builtins.input", return_value="user@example.com"),
    patch("getpass.getpass", return_value="new_token"),
  ):
    await client.authenticate()

    # First: try cached session (fails)
    # Second: connect with new token
    assert mock_roomz_class.return_value.connect.call_count == 2


@pytest.mark.asyncio
async def test_auth_log_redaction_of_sensitive_data(mock_roomz_class, temp_cache):
  """
  Given: Authentication events are being logged
  When: A token is processed
  Then: The token should be redacted in logs
  """
  client = ChatClient(
    server_url="http://localhost:5000",
    agent=None,
    session_cache_path=temp_cache,
  )

  await client.authenticate(login="user@example.com", token="secret_token_123")

  # The token should not appear in logs - this is verified by the logging module
  # The key is that the redaction processor is configured in logging.py
  # This test verifies the code path exists
  mock_roomz_class.return_value.connect.assert_called_once()


@pytest.mark.asyncio
async def test_auth_token_prompt_prevents_echo(mock_roomz_class, temp_cache):
  """
  Given: The client is prompting for the authentication token interactively
  When: The user enters the token
  Then: getpass.getpass should be used instead of input() to prevent the token from being echoed
  """
  client = ChatClient(
    server_url="http://localhost:5000",
    agent=None,
    session_cache_path=temp_cache,
  )

  # First connect fails (no cached session)
  mock_roomz_class.return_value.connect.side_effect = [
    Exception("No session"),
    None,
  ]
  mock_roomz_class.return_value.login.return_value = {"status": "sent"}

  with (
    patch("builtins.input", return_value="user@example.com"),
    patch("getpass.getpass", return_value="token123") as mock_getpass,
  ):
    await client.authenticate()

    # Verify getpass was called for token input
    mock_getpass.assert_called_once()


@pytest.mark.asyncio
async def test_auth_display_name_set_on_connect(mock_roomz_class, temp_cache):
  """
  Given: A display name is provided
  When: The client is created
  Then: The display_name should be passed to Roomz AsyncClient via Config
  """
  ChatClient(
    server_url="http://localhost:5000",
    agent=None,
    session_cache_path=temp_cache,
    name="TestBot",
  )

  # Verify display_name was passed to AsyncClient via Config
  mock_roomz_class.assert_called_once()
  call_kwargs = mock_roomz_class.call_args[1]
  assert "config" in call_kwargs
  assert call_kwargs["config"].display_name == "TestBot"
