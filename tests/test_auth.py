import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
from yoker_chat.client import ChatClient, AuthenticationError
from yoker_chat.session import SessionCache

@pytest.fixture
def mock_roomz():
    with patch("yoker_chat.client.AsyncClient") as mock:
        instance = mock.return_value
        instance.login = AsyncMock()
        instance.connect = AsyncMock()
        instance.set_name = AsyncMock()
        instance.user = {"email": "test@example.com"}
        instance.session_cookie = "mock_cookie_123"
        yield instance

@pytest.fixture
def temp_cache(tmp_path):
    return tmp_path / "session.json"

@pytest.mark.asyncio
async def test_auth_interactive_flow_sequence(mock_roomz, temp_cache):
    """
    Given: A user starts yoker-chat without arguments
    When: The user is prompted for email and then token
    Then: The client should follow the sequence: prompt email -> call login() -> prompt token -> call connect(token=...)
    """
    client = ChatClient(
        server_url="http://localhost:5000",
        agent=None,
        session_cache_path=str(temp_cache),
    )

    with patch("builtins.input", side_effect=["user@example.com"]), \
         patch("getpass.getpass", return_value="token123"):

        mock_roomz.login.return_value = {"status": "sent"}

        await client.authenticate()

        mock_roomz.login.assert_called_once_with("user@example.com")
        mock_roomz.connect.assert_called_once_with(token="token123")

@pytest.mark.asyncio
async def test_auth_cli_args_bypass_prompts(mock_roomz, temp_cache):
    """
    Given: yoker-chat is started with --login and --token arguments
    When: The authentication process begins
    Then: No interactive prompts should be shown and connect() should be called with the provided token
    """
    client = ChatClient(
        server_url="http://localhost:5000",
        agent=None,
        session_cache_path=str(temp_cache),
    )

    with patch("builtins.input") as mock_input, \
         patch("getpass.getpass") as mock_getpass:

        await client.authenticate(login="user@example.com", token="token123")

        mock_input.assert_not_called()
        mock_getpass.assert_not_called()
        mock_roomz.connect.assert_called_once_with(token="token123")

@pytest.mark.asyncio
async def test_auth_env_var_token_fallback(mock_roomz, temp_cache):
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
            session_cache_path=str(temp_cache),
        )

        # Provide login but not token
        await client.authenticate(login="user@example.com", token=None)

        mock_roomz.connect.assert_called_once_with(token="env_token_456")

@pytest.mark.asyncio
async def test_auth_session_cache_creation_on_success(mock_roomz, temp_cache):
    """
    Given: A successful authentication via token
    When: The connection is established and session cookie is received
    Then: The session cookie should be saved to the session cache file
    """
    client = ChatClient(
        server_url="http://localhost:5000",
        agent=None,
        session_cache_path=str(temp_cache),
    )

    await client.authenticate(login="user@example.com", token="token123")

    assert temp_cache.exists()
    with open(temp_cache, "r") as f:
        import json
        data = json.load(f)
        assert data["session"]["cookie"] == "mock_cookie_123"
        assert data["session"]["email"] == "test@example.com"

def test_auth_session_cache_secure_permissions(tmp_path):
    """
    Given: A session cache file is being created
    When: The file is written to disk
    Then: The file permissions must be set to 0600 (read/write for owner only)
    """
    cache_path = tmp_path / "session.json"
    cache = SessionCache(cache_path)
    cache.save(session_cookie="cookie", server_url="http://localhost:5000", email="test@example.com")

    mode = os.stat(cache_path).st_mode & 0o777
    assert mode == 0o600

@pytest.mark.asyncio
async def test_auth_session_reuse_auto_connect(mock_roomz, temp_cache):
    """
    Given: A valid session cache file exists on disk
    When: yoker-chat starts
    Then: The client should automatically attempt to connect using the cached session cookie without prompting for auth
    """
    # Pre-populate cache
    cache = SessionCache(temp_cache)
    cache.save(session_cookie="cached_cookie_789", server_url="http://localhost:5000", email="cached@example.com")

    client = ChatClient(
        server_url="http://localhost:5000",
        agent=None,
        session_cache_path=str(temp_cache),
    )

    with patch("builtins.input") as mock_input:
        await client.authenticate()

        mock_input.assert_not_called()
        mock_roomz.connect.assert_called_once_with(cookie="cached_cookie_789")

@pytest.mark.asyncio
async def test_auth_session_expiry_triggers_reauth(mock_roomz, temp_cache):
    """
    Given: A cached session exists but the server returns a 401/403 or disconnects
    When: The client attempts to use the cached session
    Then: The session cache should be cleared and the interactive authentication flow should be triggered
    """
    # Pre-populate cache
    cache = SessionCache(temp_cache)
    cache.save(session_cookie="expired_cookie", server_url="http://localhost:5000", email="expired@example.com")

    client = ChatClient(
        server_url="http://localhost:5000",
        agent=None,
        session_cache_path=str(temp_cache),
    )

    # Mock connect to fail first time (session expired) then succeed (token auth)
    mock_roomz.connect.side_effect = [Exception("Unauthorized"), None]
    mock_roomz.login.return_value = {"status": "sent"}

    with patch("builtins.input", side_effect=["user@example.com"]), \
         patch("getpass.getpass", return_value="new_token"):

        await client.authenticate()

        # First call was with cookie, second with token
        assert mock_roomz.connect.call_count == 2
        assert mock_roomz.connect.call_args_list[0][1].get("cookie") == "expired_cookie"
        assert mock_roomz.connect.call_args_list[1][1].get("token") == "new_token"

@pytest.mark.asyncio
async def test_auth_log_redaction_of_sensitive_data(caplog):
    """
    Given: Authentication events are being logged
    When: A token or session cookie is processed
    Then: These sensitive values should be redacted in the logs (e.g., replaced with [REDACTED] or masked)
    """
    import structlog
    from yoker_chat.logging import redaction_processor

    # We can test the processor directly
    event_dict = {"message": "Connecting", "token": "secret_token_123", "session_cookie": "secret_cookie_456", "other": "safe"}
    redacted = redaction_processor(None, None, event_dict.copy())

    assert redacted["token"] == "[REDACTED]"
    assert redacted["session_cookie"] == "[REDACTED]"
    assert redacted["other"] == "safe"

@pytest.mark.asyncio
async def test_auth_token_prompt_prevents_echo(mock_roomz, temp_cache):
    """
    Given: The client is prompting for the authentication token interactively
    When: The user enters the token
    Then: getpass.getpass should be used instead of input() to prevent the token from being echoed to the terminal
    """
    client = ChatClient(
        server_url="http://localhost:5000",
        agent=None,
        session_cache_path=str(temp_cache),
    )

    with patch("builtins.input", side_effect=["user@example.com"]), \
         patch("getpass.getpass", return_value="secure_token") as mock_getpass, \
         patch("builtins.input", side_effect=["user@example.com"]): # Just in case

        mock_roomz.login.return_value = {"status": "sent"}

        await client.authenticate()

        mock_getpass.assert_called_once()
