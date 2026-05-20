# Yoker Agent Integration: API Analysis

**Date**: 2026-05-20
**Status**: Design Review
**Related Task**: 1.3.5 Yoker Agent Integration
**Priority**: HIGH

## 1. Integration Architecture

### 1.1 Component Overview

The integration replaces MockAgent with the actual Yoker Agent, establishing a production-ready bridge between Roomz chat rooms and Yoker's LLM-powered agent system.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              yoker-chat CLI                                      │
│                                                                                  │
│  ┌────────────────┐    ┌────────────────┐    ┌─────────────────────────────┐    │
│  │    Roomz       │    │  ChatClient    │    │      Yoker Agent            │    │
│  │  AsyncClient    │───▶│                │───▶│                             │    │
│  │                │    │  - Filter      │    │  - process(message)         │    │
│  │  (Transport)   │    │  - Queue       │    │  - emit(ContentChunk)       │    │
│  │                │◀───│  - Buffer      │◀───│  - emit(ContentEnd)         │    │
│  │                │    │                │    │  - emit(Error)              │    │
│  └────────────────┘    └────────────────┘    │                             │    │
│                                              │  Context Manager:             │    │
│                                              │  - Session persistence        │    │
│                                              │  - Conversation history       │    │
│                                              └─────────────────────────────┘    │
│                                                                                  │
│  Configuration:                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │ yoker.toml (TOML)        │ agent.md (Markdown + YAML frontmatter)       │    │
│  │                          │                                              │    │
│  │ [backend]                │ ---                                          │    │
│  │ provider = "ollama"      │ name: ChatBot                                │    │
│  │                          │ description: Helpful assistant               │    │
│  │ [backend.ollama]         │ tools: read, write, search                   │    │
│  │ base_url = "..."         │ ---                                          │    │
│  │ model = "llama3.2"       │ You are a helpful assistant...              │    │
│  │                          │                                              │    │
│  │ [context]                │ (Markdown body = system prompt)              │    │
│  │ storage_path = "~/.cache" │                                             │    │
│  │ session_id = "auto"      │                                              │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Data Flow

```
User Message in Roomz
        │
        ▼
┌──────────────────┐
│  Roomz Event     │
│  "message"       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  ChatClient      │
│  _on_roomz_message()
│                  │
│  1. Filter       │ ──── Own message? ──▶ Discard
│  2. Extract      │ ──── No mention? ──▶ Discard (unless respond_to_all)
│  3. Queue        │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Message Queue   │
│  (asyncio.Queue) │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Queue Worker    │
│  _process_queue()│
│                  │
│  Sequential      │
│  processing      │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Agent.process() │
│                  │
│  - Load context  │
│  - Call LLM      │
│  - Stream chunks │
│  - Handle tools  │
└────────┬─────────┘
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
         │                    Join buffer + send to Roomz
         │
         └───── emits ──────▶ ErrorEvent (if failure)
                                   │
                                   ▼
                              _on_agent_error()
                                   │
                                   ▼
                              Send error message to Roomz
```

---

## 2. Agent Initialization Sequence

### 2.1 Current Implementation (MockAgent)

```python
# src/yoker_chat/cli.py (current)

from yoker_chat.mock_agent import MockAgent

agent_name = args.name or "ChatBot"
agent = MockAgent(name=agent_name)
```

### 2.2 Target Implementation (Yoker Agent)

```python
# src/yoker_chat/cli.py (target)

from pathlib import Path
from yoker import Agent, load_config
from yoker.context import BasicPersistenceContextManager

# Load configuration
config = load_config(args.config) if args.config else None

# Load agent definition
agent_definition = None
if args.agent:
    from yoker.agents import load_agent_definition
    agent_definition = load_agent_definition(args.agent)

# Initialize context manager for session persistence
context_manager = None
if args.resume:
    from yoker.context import list_sessions, BasicPersistenceContextManager
    sessions = list_sessions()
    # Let user select session to resume
    # ...

# Create agent
agent = Agent(
    config=config,
    agent_definition=agent_definition,
    context_manager=context_manager,
    thinking_mode=ThinkingMode.SILENT,  # Don't show thinking in chat
)
```

### 2.3 Initialization Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CLI Entry Point                                       │
│                                                                              │
│  parse_args()                                                                │
│       │                                                                      │
│       ▼                                                                      │
│  setup_logging()                                                             │
│       │                                                                      │
│       ▼                                                                      │
│  asyncio.run(_run_client(args))                                             │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │ _run_client(args)                                                        │ │
│  │                                                                          │ │
│  │  1. Load Yoker Config                                                    │ │
│  │     └─ load_config(args.config)                                          │ │
│  │                                                                          │ │
│  │  2. Load Agent Definition                                                │ │
│  │     └─ load_agent_definition(args.agent)                                  │ │
│  │                                                                          │ │
│  │  3. Initialize Context Manager (optional resume)                         │ │
│  │     ├─ args.resume = True  → BasicPersistenceContextManager.resume()     │ │
│  │     └─ args.resume = False → BasicPersistenceContextManager()            │ │
│  │                                                                          │ │
│  │  4. Create Agent                                                         │ │
│  │     └─ Agent(                                                            │ │
│  │          config=config,                                                  │ │
│  │          agent_definition=agent_definition,                               │ │
│  │          context_manager=context_manager,                                │ │
│  │          thinking_mode=ThinkingMode.SILENT                                │ │
│  │        )                                                                 │ │
│  │                                                                          │ │
│  │  5. Create ChatClient                                                    │ │
│  │     └─ ChatClient(server_url, agent, session_cache_path, ...)            │ │
│  │                                                                          │ │
│  │  6. Authenticate & Start                                                 │ │
│  │     ├─ await client.authenticate()                                       │ │
│  │     └─ await client.start()                                              │ │
│  │                                                                          │ │
│  │  7. Run Event Loop                                                       │ │
│  │     └─ await asyncio.Event().wait()                                      │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Event Flow Diagram

### 3.1 Complete Message Processing Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Message Processing Lifecycle                        │
│                                                                               │
│  User: "@bot What is the weather?"                                           │
│                                                                               │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Roomz AsyncClient                                                            │
│                                                                               │
│  WebSocket Message Event:                                                     │
│  {                                                                            │
│    "user": {"email": "user@example.com"},                                    │
│    "content": "@bot What is the weather?"                                    │
│  }                                                                            │
│                                                                               │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  ChatClient._on_roomz_message()                                              │
│                                                                               │
│  1. Extract sender: user@example.com                                         │
│  2. Filter: sender != bot email ✓                                            │
│  3. Check mention: "@bot" found ✓                                             │
│  4. Extract: "What is the weather?"                                          │
│  5. Queue: asyncio.Queue.put("What is the weather?")                         │
│                                                                               │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  ChatClient._process_queue()                                                  │
│                                                                               │
│  1. Get message from queue                                                     │
│  2. Acquire processing lock                                                    │
│  3. Call _process_single_message("What is the weather?")                     │
│                                                                               │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  ChatClient._process_single_message()                                         │
│                                                                               │
│  1. Clear response buffer: self._response_buffer = []                         │
│  2. Create completion future: self._response_complete = Future()              │
│  3. Call agent.process("What is the weather?")                                │
│                                                                               │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Yoker Agent.process()                                                        │
│                                                                               │
│  1. Load conversation context from ContextManager                             │
│  2. Call LLM with streaming enabled                                            │
│  3. For each response chunk:                                                   │
│     └─ emit ContentChunkEvent(text="...")                                     │
│  4. When done:                                                                 │
│     └─ emit ContentEndEvent(total_length=N)                                    │
│  5. If error:                                                                  │
│     └─ emit ErrorEvent(error_type="...", message="...")                        │
│                                                                               │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
                                 │ (for each ContentChunkEvent)
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  ChatClient._on_agent_content_chunk(event)                                    │
│                                                                               │
│  1. Extract text: chunk_text = event.text                                     │
│  2. Append to buffer: self._response_buffer.append(chunk_text)               │
│  3. Log: log.debug("chunk_received", chunk_preview=chunk_text[:20])           │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ (when ContentEndEvent)
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  ChatClient._on_agent_content_end(event)                                      │
│                                                                               │
│  1. Join buffer: response = "".join(self._response_buffer)                   │
│  2. Resolve future: self._response_complete.set_result(response)              │
│  3. Send to Roomz: asyncio.create_task(self._send_response(response))         │
│                                                                               │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  ChatClient._send_response(response)                                          │
│                                                                               │
│  1. Check empty: if not response.strip(): return                               │
│  2. Send to Roomz: await self.roomz_client.send(response)                     │
│  3. Log: log.info("response_sent", length=len(response))                       │
│                                                                               │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Roomz AsyncClient                                                            │
│                                                                               │
│  WebSocket Send:                                                               │
│  "Based on the current weather data, it's sunny with..."                     │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Roomz Chat Room                                                               │
│                                                                               │
│  Bot: "Based on the current weather data, it's sunny with..."                │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Configuration Loading

### 4.1 Yoker Configuration (yoker.toml)

The Yoker configuration file controls the LLM backend, context management, and tool settings.

**Location**: `args.config` (default: `yoker.toml`)

**Structure**:

```toml
# yoker.toml - Yoker Agent Configuration

[harness]
name = "yoker-chat"
version = "1.0"
log_level = "INFO"

[backend]
provider = "ollama"

[backend.ollama]
base_url = "http://localhost:11434"
model = "llama3.2:latest"
timeout_seconds = 120

[backend.ollama.parameters]
temperature = 0.7
top_p = 0.9
num_ctx = 4096

[context]
manager = "basic_persistence"
storage_path = "~/.cache/yoker/sessions"
session_id = "auto"  # Auto-generate session ID
persist_after_turn = true

[permissions]
filesystem_paths = [".", "/tmp"]
network_access = "limited"
max_file_size_kb = 500
max_recursion_depth = 3

[tools.read]
enabled = true
allowed_extensions = [".md", ".txt", ".py", ".json", ".yaml", ".toml"]
blocked_patterns = [".env", ".env.local", "*.key", "*.pem"]

[tools.write]
enabled = true
allow_overwrite = false
max_size_kb = 100
blocked_extensions = [".exe", ".sh", ".bat"]

[tools.search]
enabled = true
max_regex_complexity = "medium"
max_results = 500

[tools.git]
enabled = true
allowed_commands = ["status", "log", "diff"]

[logging]
format = "json"
include_tool_calls = true
include_permission_checks = true
```

### 4.2 Loading Configuration

```python
from pathlib import Path
from yoker.config import load_config, Config, ConfigurationError

def load_yoker_config(config_path: Path | str | None) -> Config:
    """
    Load Yoker configuration from TOML file.

    Args:
        config_path: Path to yoker.toml, or None for defaults.

    Returns:
        Config object.

    Raises:
        ConfigurationError: If configuration is invalid.
        FileNotFoundError: If config file doesn't exist.
    """
    if config_path is None:
        # Use defaults
        return Config()

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(
            str(config_file),
            "configuration",
            f"Configuration file not found: {config_file}",
        )

    return load_config(config_file)
```

---

## 5. Agent Definition Loading

### 5.1 Agent Definition File Format

Agent definitions are Markdown files with YAML frontmatter.

**Location**: `args.agent` (required)

**Structure**:

```markdown
---
name: ChatBot
description: A helpful assistant for chat rooms
tools: read, write, search, list
model: llama3.2:latest
color: blue
---

You are a helpful assistant in a chat room. Your role is to:

1. Answer questions clearly and concisely
2. Help users with tasks using your available tools
3. Be friendly and professional
4. Admit when you don't know something

When responding:
- Keep responses brief and to the point
- Use markdown formatting for clarity
- If you need to use a tool, explain what you're doing
- Always ask for clarification if the request is ambiguous

Available tools:
- **read**: Read files from the filesystem
- **write**: Write files to the filesystem
- **search**: Search for patterns in files
- **list**: List directory contents

Remember: You are an assistant, not a human. Be helpful, not conversational.
```

### 5.2 Frontmatter Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `name` | Yes | string | Agent identifier (unique within a configuration) |
| `description` | Yes | string | Short description for LLM tool definition |
| `tools` | Yes | string or list | Comma-separated string or list of tool names |
| `model` | No | string | Model override for this agent |
| `color` | No | string | Display color for UI integrations |

### 5.3 Loading Agent Definition

```python
from pathlib import Path
from yoker.agents import load_agent_definition, AgentDefinition, ConfigurationError

def load_agent_def(agent_path: Path | str) -> AgentDefinition:
    """
    Load agent definition from Markdown file.

    Args:
        agent_path: Path to agent definition file.

    Returns:
        AgentDefinition object.

    Raises:
        ConfigurationError: If agent definition is invalid.
        FileNotFoundError: If agent file doesn't exist.
    """
    agent_file = Path(agent_path)

    if not agent_file.exists():
        raise FileNotFoundError(
            str(agent_file),
            "agent definition",
            f"Agent definition file not found: {agent_file}",
        )

    return load_agent_definition(agent_file)
```

### 5.4 Agent Definition Validation

The loader validates:

1. **Required fields**: `name`, `description`, `tools` must be present and non-empty
2. **Tools format**: Must be comma-separated string or list
3. **YAML syntax**: Frontmatter must be valid YAML
4. **Markdown body**: System prompt must be present (can be empty)

---

## 6. Context Manager Integration

### 6.1 Context Manager Role

The Context Manager maintains conversation history across multiple messages:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Context Manager                                      │
│                                                                              │
│  Responsibilities:                                                           │
│  - Store conversation history (user messages, assistant responses)           │
│  - Provide context for LLM calls (get_context())                             │
│  - Persist session to disk (save())                                          │
│  - Resume previous sessions (load())                                         │
│                                                                              │
│  Storage:                                                                    │
│  ~/.cache/yoker/sessions/<session_id>.jsonl                                   │
│                                                                              │
│  Record Types:                                                               │
│  - session_start: Session metadata                                           │
│  - message: User/assistant/system message                                    │
│  - tool_result: Tool execution result                                         │
│  - turn: Turn boundary marker                                                 │
│  - session_end: Session termination                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Session Lifecycle

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Session Lifecycle                                   │
│                                                                               │
│  New Session                                                                  │
│  ──────────────────────────────────────────────────────────────────────────── │
│  1. agent = Agent(context_manager=BasicPersistenceContextManager())          │
│  2. agent.begin_session()                                                     │
│     └─ Writes session_start record                                            │
│  3. User messages → agent.process(message)                                    │
│     └─ Appends to context                                                      │
│     └─ Persists after turn (if config.context.persist_after_turn)             │
│  4. agent.end_session(reason="quit")                                          │
│     └─ Writes session_end record                                              │
│     └─ Closes context                                                          │
│                                                                               │
│  Resume Session (--resume flag)                                               │
│  ──────────────────────────────────────────────────────────────────────────── │
│  1. sessions = list_sessions()                                                │
│  2. Show available sessions to user                                           │
│  3. User selects session_id                                                    │
│  4. cm = BasicPersistenceContextManager.resume(session_id)                    │
│     └─ Loads session from ~/.cache/yoker/sessions/<session_id>.jsonl          │
│     └─ Reconstructs conversation history                                       │
│  5. agent = Agent(context_manager=cm)                                         │
│     └─ Context already loaded                                                 │
│  6. agent.begin_session()                                                      │
│     └─ Appends new session_start record (same file)                           │
│  7. Continue processing messages...                                            │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 6.3 Session Selection Flow

```python
# src/yoker_chat/cli.py

async def _select_session() -> BasicPersistenceContextManager | None:
    """
    Let user select a session to resume or start new.

    Returns:
        ContextManager with loaded session, or None for new session.
    """
    from yoker.context import list_sessions, SessionNotFoundError

    sessions = list_sessions()

    if not sessions:
        print("No previous sessions found. Starting new session.")
        return None

    print("\nAvailable sessions:")
    print("  [0] Start new session")
    for i, session in enumerate(sessions, start=1):
        print(f"  [{i}] {session.session_id}")
        print(f"      Messages: {session.message_count}")
        print(f"      Last turn: {session.last_turn_time}")

    while True:
        choice = input("\nSelect session [0-{}]: ".format(len(sessions)))
        try:
            idx = int(choice)
            if idx == 0:
                return None
            if 1 <= idx <= len(sessions):
                session = sessions[idx - 1]
                print(f"Resuming session: {session.session_id}")
                return BasicPersistenceContextManager.resume(session.session_id)
            print("Invalid choice. Please try again.")
        except ValueError:
            print("Please enter a number.")
```

### 6.4 Context Manager API

```python
from yoker.context import BasicPersistenceContextManager, list_sessions

# Create new session
cm = BasicPersistenceContextManager(
    storage_path="~/.cache/yoker/sessions",
    session_id="auto"  # Auto-generate ID
)

# Get context for LLM
context = cm.get_context()
# Returns: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, ...]

# Add message to context
cm.add_message("user", "What is the weather?")

# Save context to disk
cm.save()

# Close context (writes session_end record)
cm.close()

# Resume existing session
cm = BasicPersistenceContextManager.resume("session-abc123")

# List available sessions
sessions = list_sessions()
for session in sessions:
    print(f"{session.session_id}: {session.message_count} messages")
```

---

## 7. Error Handling

### 7.1 Error Categories

| Error Category | Source | Recovery Strategy |
|----------------|--------|-------------------|
| **Configuration Error** | Yoker Config/Agent Definition | Log error, exit with helpful message |
| **File Not Found** | Agent Definition File | Log error, exit with path suggestion |
| **Agent Processing Error** | Yoker Agent | Send user-friendly error message to chat, continue |
| **Network Error** | Roomz AsyncClient | Retry connection, log error |
| **Timeout Error** | Agent Processing | Send timeout message to chat, continue |
| **Context Corruption** | Context Manager | Log error, start fresh session |

### 7.2 Error Handling Implementation

```python
# src/yoker_chat/cli.py

async def _run_client(args: argparse.Namespace) -> None:
    """Initialize and run the chat client with error handling."""

    # Phase 1: Configuration Loading
    # ─────────────────────────────────────────────────────────────────────────
    try:
        from yoker.config import load_config, ConfigurationError

        if args.config:
            config = load_config(args.config)
        else:
            config = Config()  # Use defaults

    except FileNotFoundError as e:
        print(f"Error: Configuration file not found: {args.config}")
        print(f"Create a yoker.toml file or specify --config path")
        exit(1)

    except ConfigurationError as e:
        print(f"Error: Invalid configuration: {e.message}")
        print(f"Check {args.config} for errors")
        exit(1)

    # Phase 2: Agent Definition Loading
    # ─────────────────────────────────────────────────────────────────────────
    try:
        from yoker.agents import load_agent_definition

        agent_definition = load_agent_definition(args.agent)

    except FileNotFoundError as e:
        print(f"Error: Agent definition not found: {args.agent}")
        print(f"Create an agent definition file (Markdown with frontmatter)")
        exit(1)

    except ConfigurationError as e:
        print(f"Error: Invalid agent definition: {e.message}")
        print(f"Check {args.agent} for required fields (name, description, tools)")
        exit(1)

    # Phase 3: Context Manager (Session Resume)
    # ─────────────────────────────────────────────────────────────────────────
    try:
        context_manager = None

        if args.resume:
            context_manager = await _select_session()

    except Exception as e:
        log.error("session_resume_failed", error=str(e))
        print(f"Warning: Failed to resume session. Starting new session.")
        context_manager = None

    # Phase 4: Agent Initialization
    # ─────────────────────────────────────────────────────────────────────────
    try:
        from yoker import Agent
        from yoker.thinking import ThinkingMode

        agent = Agent(
            config=config,
            agent_definition=agent_definition,
            context_manager=context_manager,
            thinking_mode=ThinkingMode.SILENT,  # Don't show thinking in chat
        )

        # Begin session (writes session_start record)
        agent.begin_session()

    except Exception as e:
        log.error("agent_initialization_failed", error=str(e))
        print(f"Error: Failed to initialize agent: {e}")
        exit(1)

    # Phase 5: ChatClient Creation
    # ─────────────────────────────────────────────────────────────────────────
    try:
        client = ChatClient(
            server_url=args.server_url,
            agent=agent,
            session_cache_path=args.session_cache,
            name=args.name or agent_definition.name,
            mention_triggers=args.mention_trigger,
        )

    except Exception as e:
        log.error("client_creation_failed", error=str(e))
        print(f"Error: Failed to create chat client: {e}")
        exit(1)

    # Phase 6: Authentication & Run
    # ─────────────────────────────────────────────────────────────────────────
    try:
        await client.authenticate(login=args.login, token=args.token)
        print("✓ Authenticated and connected to chat room")

        await client.start()
        print("✓ Listening for messages... (Press Ctrl+C to exit)")

        # Run until interrupted
        await asyncio.Event().wait()

    except AuthenticationError as e:
        log.error("authentication_failed", error=str(e))
        print(f"Error: Authentication failed: {e}")
        exit(1)

    except KeyboardInterrupt:
        print("\nShutting down...")

    except Exception as e:
        log.exception("unexpected_error", error=str(e))
        print(f"Error: {e}")
        exit(1)

    finally:
        # Ensure cleanup
        await client.disconnect()

        # End agent session
        if hasattr(agent, 'end_session'):
            agent.end_session(reason="quit")
```

### 7.3 Agent Error Events

```python
# src/yoker_chat/client.py

def _on_agent_error(self, event: Any) -> None:
    """
    Handle Error events from the agent.

    Error events contain:
    - error_type: Type of error (e.g., "NetworkError", "ToolError")
    - message: Human-readable error message
    - details: Additional context (dict)
    """
    error_type = event.error_type if hasattr(event, 'error_type') else "Unknown"
    error_message = event.message if hasattr(event, 'message') else str(event)

    log.error(
        "agent_error",
        error_type=error_type,
        error_message=error_message,
        details=event.details if hasattr(event, 'details') else {},
    )

    # Signal completion with error
    if self._response_complete and not self._response_complete.done():
        self._response_complete.set_exception(AgentError(error_message))

    # Send user-friendly message to chat
    asyncio.create_task(self._send_error_response(
        "I encountered an error processing your message. Please try again."
    ))
```

---

## 8. Testing Strategy

### 8.1 Test Categories

| Test Type | Purpose | Scope |
|-----------|---------|-------|
| **Unit Tests** | Test individual functions in isolation | Mock all dependencies |
| **Integration Tests** | Test component interactions | Use real Yoker Agent with mock Roomz |
| **End-to-End Tests** | Test complete message flow | Real Yoker Agent + Mock Roomz server |
| **Manual Tests** | Test with real services | Real Roomz server + Real Yoker Agent |

### 8.2 Unit Tests

```python
# tests/unit/test_cli.py

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from yoker_chat.cli import parse_args, load_yoker_config, load_agent_def


def test_parse_args_defaults():
    """Test CLI argument parsing with defaults."""
    with patch('sys.argv', ['yoker-chat', '--server-url', 'http://localhost:5000', '--agent', 'agent.md']):
        args = parse_args()
        assert args.server_url == 'http://localhost:5000'
        assert args.agent == 'agent.md'
        assert args.config == 'yoker.toml'
        assert args.session_cache == '~/.cache/yoker-chat/session.json'
        assert args.mention_trigger == ['@bot']


def test_load_yoker_config_file_not_found():
    """Test configuration loading with missing file."""
    with pytest.raises(FileNotFoundError):
        load_yoker_config(Path('/nonexistent/config.toml'))


def test_load_yoker_config_defaults():
    """Test configuration loading with defaults."""
    config = load_yoker_config(None)
    assert config is not None
    assert config.backend.provider == 'ollama'


def test_load_agent_def_file_not_found():
    """Test agent definition loading with missing file."""
    with pytest.raises(FileNotFoundError):
        load_agent_def(Path('/nonexistent/agent.md'))


def test_load_agent_def_valid(tmp_path):
    """Test agent definition loading with valid file."""
    agent_file = tmp_path / 'agent.md'
    agent_file.write_text('''
---
name: TestBot
description: Test agent
tools: read, write
---
You are a test agent.
''')

    agent_def = load_agent_def(agent_file)
    assert agent_def.name == 'TestBot'
    assert agent_def.description == 'Test agent'
    assert agent_def.tools == ('read', 'write')
    assert 'You are a test agent.' in agent_def.system_prompt
```

### 8.3 Integration Tests

```python
# tests/integration/test_agent_integration.py

import pytest
from pathlib import Path
import asyncio

from yoker import Agent
from yoker.agents import load_agent_definition
from yoker.config import Config
from yoker.context import BasicPersistenceContextManager


@pytest.fixture
def agent_definition(tmp_path):
    """Create a test agent definition."""
    agent_file = tmp_path / 'agent.md'
    agent_file.write_text('''
---
name: TestBot
description: Test agent for integration tests
tools: read
---
You are a test assistant. Respond briefly.
''')
    return load_agent_definition(agent_file)


@pytest.fixture
def test_config():
    """Create a test configuration."""
    return Config()  # Use defaults


@pytest.fixture
async def agent(agent_definition, test_config):
    """Create a test agent."""
    agent = Agent(
        config=test_config,
        agent_definition=agent_definition,
        thinking_mode=ThinkingMode.SILENT,
    )
    agent.begin_session()
    yield agent
    agent.end_session(reason="test_complete")


class TestAgentIntegration:
    """Test Yoker Agent integration."""

    async def test_agent_initialization(self, agent):
        """Test agent initializes correctly."""
        assert agent is not None
        assert agent.agent_definition is not None
        assert agent.agent_definition.name == 'TestBot'

    async def test_agent_event_handlers(self, agent):
        """Test agent emits expected events."""
        events = []

        def capture_event(event):
            events.append(event)

        agent.add_event_handler(capture_event)

        # Process a message
        response = await asyncio.to_thread(agent.process, "Hello")

        # Check events were emitted
        event_types = [e.type.value for e in events]
        assert 'ContentStart' in event_types or 'ContentChunk' in event_types
        assert 'ContentEnd' in event_types
        assert 'TurnStart' in event_types
        assert 'TurnEnd' in event_types

    async def test_agent_response(self, agent):
        """Test agent produces a response."""
        response = await asyncio.to_thread(agent.process, "Hello")
        assert len(response) > 0

    async def test_agent_context_persistence(self, agent, tmp_path):
        """Test context is persisted."""
        # Create context manager with storage
        storage_path = tmp_path / 'sessions'
        cm = BasicPersistenceContextManager(
            storage_path=storage_path,
            session_id='test-session',
        )

        agent.context = cm
        agent.begin_session()

        # Process a message
        await asyncio.to_thread(agent.process, "Hello")

        # Check context file was created
        session_file = storage_path / 'test-session.jsonl'
        assert session_file.exists()

        agent.end_session(reason="test_complete")
```

### 8.4 End-to-End Tests

```python
# tests/e2e/test_message_flow.py

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from yoker_chat.client import ChatClient
from yoker import Agent


@pytest.fixture
def mock_roomz_client():
    """Create a mock Roomz AsyncClient."""
    client = AsyncMock()
    client.user = {"email": "bot@example.com"}
    client.send = AsyncMock()
    return client


@pytest.fixture
async def real_agent():
    """Create a real Yoker Agent for testing."""
    from yoker.config import Config
    from yoker.thinking import ThinkingMode

    agent = Agent(
        config=Config(),
        thinking_mode=ThinkingMode.SILENT,
    )
    agent.begin_session()
    yield agent
    agent.end_session(reason="test_complete")


class TestMessageFlow:
    """End-to-end message flow tests."""

    async def test_message_processing_pipeline(
        self, mock_roomz_client, real_agent, tmp_path
    ):
        """Test complete message flow from Roomz to Agent and back."""
        # Create ChatClient with real agent
        client = ChatClient(
            server_url="http://localhost:5000",
            agent=real_agent,
            session_cache_path=str(tmp_path / "session.json"),
            name="TestBot",
            mention_triggers=["@bot"],
        )
        client.roomz_client = mock_roomz_client

        # Start client
        await client.start()

        # Simulate incoming message
        message_data = {
            "user": {"email": "user@example.com"},
            "content": "@bot What is 2+2?",
        }

        # Trigger message handler
        await client._on_roomz_message(message_data)

        # Wait for processing
        await asyncio.sleep(2)

        # Check that response was sent
        assert mock_roomz_client.send.called

        # Stop client
        await client.stop()
```

### 8.5 Manual Testing

```bash
# Manual testing with real services

# 1. Start Roomz server
cd /path/to/roomz
python -m roomz.server

# 2. Create test agent definition
cat > test-agent.md << 'EOF'
---
name: TestBot
description: Test agent for manual testing
tools: read, search
---
You are a test assistant. Be helpful and concise.
EOF

# 3. Create test configuration
cat > yoker.toml << 'EOF'
[backend]
provider = "ollama"

[backend.ollama]
base_url = "http://localhost:11434"
model = "llama3.2:latest"

[context]
storage_path = "~/.cache/yoker-chat/sessions"
EOF

# 4. Run yoker-chat
uv run yoker-chat \
    --server-url http://localhost:5000 \
    --agent test-agent.md \
    --config yoker.toml \
    --name TestBot \
    --mention-trigger @bot

# 5. In another terminal, connect to Roomz and send messages
# User: @bot What is 2+2?
# Expected: Bot responds with answer

# 6. Test session resume
# Ctrl+C to stop, then:
uv run yoker-chat \
    --server-url http://localhost:5000 \
    --agent test-agent.md \
    --config yoker.toml \
    --resume

# Expected: Bot remembers previous conversation
```

---

## 9. Implementation Checklist

### Phase 1: Agent Initialization

- [ ] Replace MockAgent import with Yoker Agent import
- [ ] Add configuration loading (`load_config`)
- [ ] Add agent definition loading (`load_agent_definition`)
- [ ] Add context manager initialization
- [ ] Add session resume logic
- [ ] Add error handling for configuration/agent loading
- [ ] Add `--resume` flag support
- [ ] Test agent initialization with real Yoker Agent

### Phase 2: Event Handler Integration

- [ ] Verify `add_event_handler` compatibility
- [ ] Verify `ContentChunkEvent` handling
- [ ] Verify `ContentEndEvent` handling
- [ ] Verify `ErrorEvent` handling
- [ ] Add optional event handlers (ThinkingStart, ThinkingEnd, ToolCall)
- [ ] Test event flow with real Yoker Agent

### Phase 3: Context Management

- [ ] Implement session selection for `--resume`
- [ ] Test session persistence across restarts
- [ ] Test session resume with multiple sessions
- [ ] Add session listing command
- [ ] Document session management

### Phase 4: Error Handling

- [ ] Add configuration validation
- [ ] Add agent definition validation
- [ ] Add context corruption recovery
- [ ] Add network error handling
- [ ] Add timeout handling
- [ ] Test all error scenarios

### Phase 5: Testing

- [ ] Write unit tests for configuration loading
- [ ] Write unit tests for agent definition loading
- [ ] Write integration tests for agent initialization
- [ ] Write integration tests for event flow
- [ ] Write end-to-end tests for message flow
- [ ] Perform manual testing

---

## 10. Dependencies

### Required Packages

| Package | Version | Purpose |
|---------|---------|---------|
| `yoker` | `>=0.1.0` | Yoker Agent engine |
| `roomz` | `>=0.1.0` | Roomz AsyncClient |
| `structlog` | `>=23.0.0` | Structured logging |
| `asyncio` | stdlib | Async runtime |

### Yoker Package Structure

```
yoker/
├── agent.py              # Agent class
├── agents/
│   ├── __init__.py       # Exports load_agent_definition
│   ├── loader.py         # Agent definition loader
│   ├── schema.py         # AgentDefinition dataclass
│   └── validator.py      # Agent definition validator
├── config/
│   ├── __init__.py       # Exports load_config, Config
│   ├── loader.py         # TOML config loader
│   ├── schema.py         # Config dataclasses
│   └── validator.py      # Config validator
├── context/
│   ├── __init__.py       # Exports BasicPersistenceContextManager, list_sessions
│   ├── basic.py          # BasicPersistenceContextManager implementation
│   ├── interface.py      # ContextManager protocol
│   └── session.py        # Session metadata utilities
├── events/
│   ├── __init__.py       # Exports all event types
│   └── types.py          # Event dataclasses
└── exceptions.py         # Custom exceptions
```

---

## 11. Security Considerations

### 11.1 Configuration Security

- **File Permissions**: Configuration files should be readable only by owner (0600)
- **Environment Variables**: Sensitive settings (API keys) should use environment variables
- **Path Validation**: Agent definition paths are validated to prevent traversal

### 11.2 Session Security

- **Session Files**: Stored in `~/.cache/yoker/sessions/` with 0600 permissions
- **Session IDs**: Auto-generated or user-specified (validated for safety)
- **Session Cleanup**: Sessions persist until manually deleted

### 11.3 Agent Capabilities

Agent capabilities are limited by:

1. **Tool Restrictions**: Only tools listed in agent definition are available
2. **Path Guardrails**: Filesystem access is restricted to allowed paths
3. **Network Guardrails**: Web access is controlled by domain allowlists/blocklists
4. **Permission Handlers**: Sensitive operations require explicit permissions

---

## 12. Migration Path

### Current State (MockAgent)

```python
# MockAgent provides:
# - add_event_handler(event_type, handler)
# - process(message) -> str
# - Simple echo response for testing
```

### Target State (Yoker Agent)

```python
# Yoker Agent provides:
# - add_event_handler(handler)  # Note: different signature
# - process(message) -> str
# - begin_session()
# - end_session(reason)
# - context: ContextManager
# - agent_definition: AgentDefinition
# - config: Config
```

### Migration Steps

1. **Update Import**: Replace `from yoker_chat.mock_agent import MockAgent` with `from yoker import Agent`
2. **Update Initialization**: Load config and agent definition, pass to Agent constructor
3. **Update Event Handlers**: Verify event handler registration matches Yoker API
4. **Add Session Management**: Add `begin_session()` and `end_session()` calls
5. **Add Context Management**: Initialize context manager with storage path
6. **Test Thoroughly**: Run all tests with real Yoker Agent

---

## 13. Action Items

### Immediate (Task 1.3.5)

1. **Update `cli.py`**:
   - Replace MockAgent with Yoker Agent
   - Add configuration loading
   - Add agent definition loading
   - Add context manager initialization
   - Add session resume support
   - Add error handling

2. **Verify `client.py`**:
   - Ensure event handler registration matches Yoker API
   - Test with real Yoker Agent
   - Add integration tests

3. **Documentation**:
   - Update README with agent definition format
   - Document configuration options
   - Document session management

### Future Enhancements

1. **Session Management CLI**:
   - `--list-sessions`: List available sessions
   - `--delete-session <id>`: Delete a session

2. **Multi-Agent Support**:
   - Load multiple agent definitions
   - Switch between agents dynamically

3. **Advanced Features**:
   - Streaming responses (send chunks as they arrive)
   - Typing indicators
   - Message editing/deletion support