# Functional Analysis: Yoker Chat Client

**Document Version**: 1.0
**Date**: 2026-05-18
**Status**: Draft Analysis

## Overview

The Yoker Chat Client (`yoker-chat`) is a standalone client application that bridges Roomz chat rooms to Yoker agents. It enables AI agents to participate in chat rooms as bot participants, processing incoming messages and sending responses.

This is NOT a Yoker tool - it's a separate client application that uses Yoker as the agent engine.

## Architecture

### Component Relationship

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Yoker Chat Client                            │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Roomz AsyncClient                          │  │
│  │  - WebSocket connection to Roomz server                       │  │
│  │  - Event handling: message, user_joined, user_left, etc.     │  │
│  │  - Authentication via magic link token                       │  │
│  └────────────────────────────┬─────────────────────────────────┘  │
│                               │                                    │
│                               ▼                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Message Router                              │  │
│  │  - Filter messages (ignore own messages, handle mentions)     │  │
│  │  - Convert Roomz message events to Agent input               │  │
│  │  - Queue management for concurrent messages                   │  │
│  └────────────────────────────┬─────────────────────────────────┘  │
│                               │                                    │
│                               ▼                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Yoker Agent                                  │  │
│  │  - process(message) for each incoming chat message           │  │
│  │  - Event handlers capture response content                    │  │
│  │  - Agent definition defines bot personality and tools         │  │
│  └────────────────────────────┬─────────────────────────────────┘  │
│                               │                                    │
│                               ▼                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Response Handler                            │  │
│  │  - Capture Agent events (ContentChunk, ContentEnd)           │  │
│  │  - Buffer complete response                                   │  │
│  │  - Send response back to Roomz via AsyncClient               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Event Flow

```
Roomz Server                    Yoker Chat Client                    Yoker Agent
     │                                │                                    │
     │  'message' event               │                                    │
     │  {user, content, timestamp}     │                                    │
     ├───────────────────────────────>│                                    │
     │                                │                                    │
     │                                │  Filter & Queue                    │
     │                                │  (is mention? is own message?)     │
     │                                │                                    │
     │                                │  agent.process(content)            │
     │                                ├──────────────────────────────────->│
     │                                │                                    │
     │                                │  ContentChunk events               │
     │                                │<───────────────────────────────────┤
     │                                │                                    │
     │                                │  Buffer complete response          │
     │                                │                                    │
     │                                │  client.send(response)             │
     │                                │                                    │
     │  message broadcast             │                                    │
     │<───────────────────────────────┤                                    │
     │                                │                                    │
```

## Entry Point: yoker-chat CLI

### Command Line Interface

```bash
yoker-chat --server-url http://localhost:5000 \
           --agent examples/agents/chat-bot.md \
           --config yoker.toml \
           --session-cache ~/.cache/yoker-chat/session.json
```

**With login/token/name (non-interactive):**
```bash
yoker-chat --server-url http://localhost:5000 \
           --agent examples/agents/chat-bot.md \
           --login user@example.com \
           --token abc123def456 \
           --name "ChatBot"
```

### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--server-url` | Roomz server URL | Required (or ROOMZ_SERVER_URL env) |
| `--agent` | Path to agent definition file | Required |
| `--config` | Path to Yoker config file | yoker.toml |
| `--session-cache` | Path to session cache file | ~/.cache/yoker-chat/session.json |
| `--mention-trigger` | String that triggers bot response | `@bot` or agent name |
| `--login` | Email address for magic link auth (matches /login command) | Interactive prompt if not provided |
| `--token` | Magic link token | Interactive prompt if not provided |
| `--name` | Display name in chat (matches /name command) | Agent name from definition |
| `--resume` | Resume a previous session context | New session (no context) |
| `--log-file` | Path to log file | stdout |
| `--log-format` | Log format (text or json) | text |

### Authentication Flow

The client performs authentication on startup. It supports both interactive and non-interactive modes:

**Flow Decision:**

```
                    ┌─────────────────────┐
                    │  Start yoker-chat   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Check session cache │
                    └──────────┬──────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
              Valid cache           No/invalid cache
                    │                     │
                    ▼                     ▼
           ┌───────────────┐    ┌─────────────────────┐
           │ Auto-connect  │    │ --login provided?   │
           │ (skip auth)   │    └──────────┬──────────┘
           └───────────────┘               │
                                  ┌────────┴────────┐
                                  │                 │
                               Yes               No
                                  │                 │
                                  ▼                 ▼
                        ┌─────────────────┐  ┌─────────────────┐
                        │ --token        │  │ Prompt:         │
                        │ provided?      │  │ "Enter email:"  │
                        └────────┬───────┘  └────────┬────────┘
                         ┌───────┴────┐            │
                         │            │            │
                      Yes          No             │
                         │            │            │
                         ▼            ▼            │
                    ┌──────────┐  ┌──────────┐    │
                    │ Connect  │  │ Request  │    │
                    │ directly │  │ magic    │    │
                    │ with     │  │ link     │    │
                    │ token    │  └────┬─────┘    │
                    └──────────┘       │          │
                                       ▼          │
                              ┌─────────────────┐ │
                              │ --token        │ │
                              │ provided?      │ │
                              └────────┬───────┘ │
                               ┌───────┴────┐    │
                               │            │    │
                            Yes          No      │
                               │            │    │
                               ▼            ▼    │
                          ┌────────┐  ┌─────────────────┐
                          │Connect │  │Prompt:          │
                          │with    │  │"Paste token:"   │
                          │token   │  └─────────────────┘
                          └────────┘
```

**Interactive Mode (no --login or --token):**

```
$ yoker-chat --server-url http://localhost:5000 --agent bot.md

Connecting to Roomz server...
No cached session found.

Enter your email address: user@example.com

Requesting magic link...
✓ Magic link sent to user@example.com

Check your email and paste the token (or click the magic link):
> abc123def456...

✓ Authenticated as user@example.com
✓ Connected to chat room
```

**Non-Interactive Mode (--login and --token provided):**

```
$ yoker-chat --server-url http://localhost:5000 --agent bot.md \
             --login user@example.com --token abc123def456 --name "ChatBot"

Connecting to Roomz server...
Authenticating as user@example.com...
✓ Authenticated as user@example.com
✓ Name set to "ChatBot"
✓ Connected to chat room
```

**Partial (--login only, need token interactively):**

```
$ yoker-chat --server-url http://localhost:5000 --agent bot.md \
             --login user@example.com --name "ChatBot"

Connecting to Roomz server...
Requesting magic link for user@example.com...
✓ Magic link sent to user@example.com

Check your email and paste the token:
> abc123def456...

✓ Authenticated as user@example.com
✓ Name set to "ChatBot"
✓ Connected to chat room
```

**Session Reuse (valid cached session):**

```
$ yoker-chat --server-url http://localhost:5000 --agent bot.md

Connecting to Roomz server...
Found cached session.
✓ Reconnected as user@example.com
✓ Connected to chat room
```

**Session Context Resume (--resume flag):**

```
$ yoker-chat --server-url http://localhost:5000 --agent bot.md --resume

Available session contexts:
  1. 2026-05-18 14:32:15 (42 messages, last: "Thanks for the help!")
  2. 2026-05-17 10:15:22 (18 messages, last: "See you tomorrow!")
  3. 2026-05-15 09:00:01 (5 messages, last: "Hello bot!")

Select session to resume (1-3, or 'n' for new): 1

Resuming session from 2026-05-18 14:32:15...
Connecting to Roomz server...
✓ Connected to chat room
```

### Logging

All events are logged using structured logging (configurable output):

```
# Default: console output with timestamps
2026-05-18 14:32:15 [INFO]  message_received sender=alice@example.com content="Hello bot!"
2026-05-18 14:32:16 [INFO]  response_sent content="Hello! How can I help?"
2026-05-18 14:32:20 [INFO]  user_joined email=bob@example.com
2026-05-18 14:32:25 [INFO]  connection_status status=connected

# Or redirect to file
$ yoker-chat --log-file /var/log/yoker-chat.log

# Or JSON format for log aggregation
$ yoker-chat --log-format json
```

**Log Events:**

| Event | Fields |
|-------|--------|
| `message_received` | sender, content |
| `response_sent` | content |
| `user_joined` | email |
| `user_left` | email |
| `connection_status` | status (connecting/connected/disconnected) |
| `auth_success` | email |
| `auth_failed` | email, error |

## Event Handling

### Roomz to Agent Bridge

The client registers handlers for Roomz events:

```python
# yoker_chat/client.py

import structlog

log = structlog.get_logger()

class ChatClient:
    def __init__(self, agent: Agent, roomz_client: AsyncClient):
        self.agent = agent
        self.client = roomz_client
        self._response_buffer: list[str] = []
        self._processing = False

    async def start(self):
        # Interactive authentication
        await self._authenticate_interactive()

        # Register event handlers
        self.client.on("message", self._on_message)
        self.client.on("authenticated", self._on_authenticated)
        self.client.on("disconnect", self._on_disconnect)

        # Register agent event handlers
        self.agent.add_event_handler(self._on_agent_content_chunk)
        self.agent.add_event_handler(self._on_agent_content_end)

        # Connect
        await self.client.connect()

    async def _authenticate_interactive(self, login: str | None, token: str | None, name: str | None):
        """Interactive login flow with optional login/token from command line."""
        # Check for cached session
        if await self._try_cached_session():
            log.info("auth_reconnected", source="cached_session")
            return

        # If both login and token provided, connect directly
        if login and token:
            log.info("authenticating", email=login)
            await self.client.connect(token=token)
            log.info("auth_success", email=login)
            if name:
                await self.client.set_name(name)
                log.info("name_set", name=name)
            self._cache_session()
            return

        # If login provided, skip login prompt
        if not login:
            login = input("Enter your email address: ")

        # Request magic link
        log.info("requesting_magic_link", email=login)
        result = await self.client.login(login)

        if "error" in result:
            log.error("magic_link_failed", error=result["error"])
            raise AuthenticationError(result["error"])

        log.info("magic_link_sent", email=login)

        # If token provided, use it; otherwise prompt
        if not token:
            print("Check your email and paste the token:")
            token = input("> ")

        # Connect with token
        await self.client.connect(token=token)
        log.info("auth_success", email=login)

        # Set display name if provided
        if name:
            await self.client.set_name(name)
            log.info("name_set", name=name)

        # Cache session
        self._cache_session()

    async def _on_message(self, data: dict):
        # Filter: Ignore own messages
        if data.get("user", {}).get("email") == self.client.user.get("email"):
            return

        # Log incoming message
        sender = data.get("user", {}).get("email", "Unknown")
        content = data.get("content", "")
        log.info("message_received", sender=sender, content=content)

        # Filter: Check for mention trigger
        if not self._is_mentioned(content):
            return

        # Queue message processing
        await self._process_message(content)

    def _is_mentioned(self, content: str) -> bool:
        # Check for @bot-name or @bot
        mention_triggers = [f"@{self._bot_name.lower()}", "@bot"]
        content_lower = content.lower()
        return any(trigger in content_lower for trigger in mention_triggers)

    async def _process_message(self, content: str):
        # Extract the actual message (remove mention)
        message = self._extract_message(content)

        # Process through agent
        self._response_buffer.clear()
        self._processing = True

        try:
            response = self.agent.process(message)
            # Response is also available via events
        finally:
            self._processing = False

    def _on_agent_content_chunk(self, event: ContentChunkEvent):
        # Buffer streaming content
        self._response_buffer.append(event.text)

    def _on_agent_content_end(self, event: ContentEndEvent):
        # Send complete response
        response = "".join(self._response_buffer)
        log.info("response_sent", content=response)
        asyncio.create_task(self.client.send(response))
```

### Concurrent Message Handling

The client must handle concurrent messages gracefully:

1. **Queue Processing**: Messages are queued and processed sequentially
2. **Busy Indicator**: If processing, bot indicates it's busy
3. **Context Isolation**: Each message processed in agent's conversation context

```python
class ChatClient:
    def __init__(self, ...):
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def start(self):
        # Start message processing worker
        self._worker_task = asyncio.create_task(self._process_queue())

        # Connect
        await self.client.connect()

    async def _process_queue(self):
        while True:
            message = await self._message_queue.get()

            try:
                response = self.agent.process(message)
                await self.client.send(response)
            except Exception as e:
                log.error("message_processing_failed", error=str(e))
                # Continue processing next message
            finally:
                self._message_queue.task_done()

    async def _on_message(self, data: dict):
        # Filter and queue
        if self._should_process(data):
            message = self._extract_message(data["content"])
            await self._message_queue.put(message)
```

## Response Routing

### Agent Events to Chat Messages

| Agent Event | Chat Client Action |
|-------------|-------------------|
| `ContentStartEvent` | Begin buffering response |
| `ContentChunkEvent` | Append text to buffer |
| `ContentEndEvent` | Send buffered response via `client.send()` |
| `ThinkingStartEvent` | (Optional) Send status: "Thinking..." |
| `ToolCallEvent` | (Optional) Send status: "Using tool: {name}" |
| `ErrorEvent` | Send error message to chat |

### Response Formatting

- **Complete responses**: Send after `ContentEndEvent`
- **Streaming responses**: Send chunks as they arrive (optional)
- **Long responses**: Split into multiple messages (chat platform limits)
- **Code blocks**: Format with markdown if supported

## Authentication

### Magic Link Flow for Bot Accounts

1. **Bot Account Creation**:
   - Create dedicated email for bot (e.g., `bot@company.com`)
   - Add to Roomz `ALLOWED_EMAILS`

2. **Magic Link Generation**:
   ```bash
   # Request magic link via API
   curl -X POST http://localhost:5000/auth/request-magic-link \
        -H "Content-Type: application/json" \
        -d '{"email": "bot@company.com"}'

   # Magic link logged to server console (development mode)
   # Link format: http://localhost:5000/auth/verify?token=<TOKEN>
   ```

3. **Token Extraction**:
   ```bash
   # Extract token from magic link
   TOKEN="abc123def456"  # From magic link URL
   ```

4. **Client Startup**:
   ```bash
   yoker-chat --server-url http://localhost:5000 \
              --token $TOKEN \
              --agent agents/assistant.md
   ```

5. **Session Persistence**:
   - Client caches session cookie to `~/.cache/yoker-chat/session.json`
   - Subsequent runs use cached session (no token needed)
   - Session auto-reconnects on disconnect

## Configuration

### Yoker Chat Configuration File

```toml
# yoker-chat.toml

[roomz]
server_url = "http://localhost:5000"
session_cache = "~/.cache/yoker-chat/session.json"

[agent]
definition = "agents/chat-bot.md"
config = "yoker.toml"
display_name = "Assistant"
mention_triggers = ["@assistant", "@bot", "@help"]

[behavior]
respond_to_all = false  # Only respond when mentioned
max_response_length = 2000  # Split longer responses
show_thinking = false  # Don't show thinking in chat
show_tool_calls = false  # Don't show tool calls in chat

[rate_limiting]
min_interval_ms = 1000  # Minimum time between responses
max_per_minute = 10  # Maximum responses per minute
```

### Agent Definition for Chat Bot

```markdown
---
name: chat-bot
description: AI assistant for chat room
tools: Read, Search, WebFetch, WebSearch
---

# Chat Bot Agent

You are an AI assistant participating in a chat room. Your role is to:

1. Answer questions when mentioned (@bot)
2. Help with research and information lookup
3. Be concise and helpful

## Behavior Guidelines

- Respond only when mentioned with @bot or your name
- Keep responses under 500 words unless explaining complex topics
- Use markdown formatting for code and lists
- Acknowledge when you don't know something
- Don't make up information

## Available Tools

You have access to:
- Read: Read files
- Search: Search for patterns in files
- WebFetch: Fetch web content
- WebSearch: Search the web (requires OLLAMA_API_KEY)
```

## Session Caching

### Authentication Session vs Agent Context

The client maintains two types of persistence:

1. **Authentication Session** (automatic):
   - Roomz session cookie cached in `~/.cache/yoker-chat/session.json`
   - Enables automatic reconnection without re-authenticating
   - Separate from agent context

2. **Agent Context** (optional, via `--resume`):
   - Yoker agent conversation history persisted to JSONL files
   - Enables resuming previous conversations
   - Listed and selected via `--resume` flag

### Session Persistence

The client maintains session state across restarts:

```python
class SessionCache:
    """Manages session persistence for yoker-chat."""

    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self._ensure_cache_dir()

    def _ensure_cache_dir(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, session_cookie: str, server_url: str):
        data = {
            "session_cookie": session_cookie,
            "server_url": server_url,
            "saved_at": datetime.now().isoformat(),
        }
        with open(self.cache_path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self) -> dict | None:
        if not self.cache_path.exists():
            return None
        try:
            with open(self.cache_path) as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, KeyError):
            return None

    def clear(self):
        if self.cache_path.exists():
            self.cache_path.unlink()
```

### Agent Context Persistence

The Yoker agent maintains its own context (optional, requires `--resume` flag):

- `ContextManager` persists conversation history to JSONL
- Each session has separate context file
- Context resumes when user selects session via `--resume`

**Without `--resume` flag:**
- New session starts with fresh context
- No conversation history from previous sessions

**With `--resume` flag:**
- Lists available sessions with metadata (date, message count, last message)
- User selects session to resume
- Agent continues from previous conversation context

## Implementation Components

### 1. ChatClient Class

**Location**: `src/yoker_chat/client.py`

**Responsibilities**:
- Bridge Roomz AsyncClient to Yoker Agent
- Register event handlers for both systems
- Manage message queue and processing
- Handle authentication and session caching

### 2. CLI Entry Point

**Location**: `src/yoker_chat/__main__.py`

**Responsibilities**:
- Parse command-line arguments
- Load configuration
- Create Agent instance
- Create ChatClient instance
- Handle graceful shutdown

### 3. Configuration Module

**Location**: `src/yoker_chat/config.py`

**Responsibilities**:
- Load TOML configuration
- Validate configuration
- Provide typed config access

### 4. Package Structure

```
src/yoker_chat/
  __init__.py           # Package exports
  __main__.py           # CLI entry point
  client.py             # ChatClient implementation
  config.py             # Configuration loading
  session.py            # Session caching
```

## Error Handling

### Connection Errors

- **Disconnect**: Auto-reconnect with exponential backoff
- **Auth Failure**: Clear session cache, prompt for new token
- **Network Error**: Retry with backoff, log errors

### Processing Errors

- **Agent Error**: Send error message to chat, continue processing
- **Tool Error**: Log error, agent handles error in context
- **Rate Limit**: Queue messages, process when limit expires

### Graceful Shutdown

1. Stop accepting new messages
2. Complete processing current message
3. Save session state
4. Close WebSocket connection
5. Exit cleanly

## Testing Strategy

### Unit Tests

- Message filtering logic
- Mention detection
- Response buffering
- Configuration parsing

### Integration Tests

- Mock Roomz server
- Mock Agent responses
- End-to-end message flow

### Live Tests

- Connect to running Roomz server
- Use real Agent with test definition
- Verify responses in chat

## Dependencies

### Required Packages

| Package | Purpose | Version |
|---------|---------|---------|
| `yoker` | Agent engine | `>=0.1.0` |
| `roomz` | Chat client | `>=0.1.0` |
| `asyncio` | Async runtime | stdlib |
| `aiohttp` | HTTP client | `>=3.8.0` |
| `structlog` | Structured logging | `>=23.0.0` |

### Optional Packages

| Package | Purpose | Version |
|---------|---------|---------|
| `rich` | Console output | `>=14.0.0` |

## Security Considerations

### Authentication

- Session cookies are stored in user's home directory (`~/.cache/yoker-chat/`)
- File permissions should be restrictive (0600)
- Session cache should be cleared on explicit logout

### Message Filtering

- Always ignore own messages to prevent feedback loops
- Validate mention triggers to avoid responding to malicious patterns
- Rate limit responses to prevent spam

### Agent Capabilities

- Agent has limited tools (defined in agent definition)
- Path guardrails prevent file system access outside allowed paths
- Web guardrails prevent SSRF attacks

## Future Enhancements

### Phase 2 Features

1. **Multi-room Support**: Connect to multiple rooms simultaneously
2. **Direct Messages**: Respond to private messages
3. **Commands**: Handle `/command` messages specially
4. **Streaming Responses**: Send response chunks as they arrive
5. **Rate Limiting**: Respect chat platform rate limits
6. **Admin Commands**: Special commands for bot administrators

### Phase 3 Features

1. **Bot Management**: Start/stop bots remotely
2. **Metrics Collection**: Track bot usage and performance
3. **Multi-bot Coordination**: Multiple bots in same room with coordination
4. **Context Sharing**: Share context between multiple bot instances

## Acceptance Criteria

### Minimal Viable Chat Client

- [ ] Connect to Roomz server with authentication
- [ ] Receive messages from chat room
- [ ] Filter messages by mention trigger
- [ ] Process message through Yoker agent
- [ ] Send agent response back to chat room
- [ ] Handle graceful shutdown
- [ ] Cache session for reconnection
- [ ] Log events for debugging

### Production Ready

- [ ] Handle concurrent messages with queue
- [ ] Implement rate limiting
- [ ] Handle connection errors with retry
- [ ] Support configuration file
- [ ] Support command-line arguments
- [ ] Split long responses
- [ ] Show status indicators (typing, thinking)
- [ ] Comprehensive test coverage