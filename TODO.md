# TODO

## Backlog

### Phase 1: Core Implementation

- [x] **1.1 Project Setup**
  - Create Python package structure (src/yoker_chat/)
  - Set up pyproject.toml with dependencies (yoker, roomz)
  - Configure development environment (ruff, mypy, pytest, tox)
  - Create CLI entry point (yoker-chat)
  - Set up Sphinx documentation structure
  - **Satisfies**: R50-R53 (usability requirements)

- [x] **1.2 Authentication Module**
  - Implement interactive login flow (prompt for email → request magic link → prompt for token)
  - Support --login and --token arguments for non-interactive authentication
  - Support --name argument to set display name (matches /name command)
  - Support session caching for automatic reconnection
  - Implement session cache file with restrictive permissions (0600)
  - Handle cached session validation and expiry
  - **Satisfies**: R1-R8

- [x] **1.3 ChatClient Class**
  - Create ChatClient class to bridge Roomz AsyncClient to Yoker Agent
  - Implement message filtering (ignore own messages, check mentions)
  - Implement message queuing for sequential processing
  - Implement agent response capture and buffering
  - Implement response sending to chat room
  - **Design**: See [analysis/api-chatclient.md](analysis/api-chatclient.md)
  - **Satisfies**: R12-R20

- [ ] **1.3.6 Dependency Upgrade and Codebase Simplification**
  - Upgrade yoker package to latest release
  - Upgrade roomz package to latest release
  - Review new features from upstream releases
  - Remove code that's now handled by upstream
  - Evaluate what more could be delegated to upstream projects
  - Goal: Make yoker-chat a minimal bridge between yoker.Agent and roomz.AsyncClient
  - **Analysis**: See [analysis/upgrade-1.3.6.md](analysis/upgrade-1.3.6.md)
  - **Satisfies**: R12-R20
  
  - [ ] **1.3.6.1: Upgrade Dependencies**
    - Update pyproject.toml: yoker>=0.4.0, roomz>=0.2.0
    - Verify imports still work after upgrade
    - Run test suite to ensure backward compatibility
    - **Acceptance**: Dependencies upgraded, all imports work, tests pass
  
  - [ ] **1.3.6.2: Implement Config Auto-Discovery**
    - Refactor load_yoker_config() to use Config.discover()
    - Support explicit --config path (backward compatible)
    - Support environment variable discovery (YOKER_*)
    - Support file discovery (./yoker.toml, ~/.yoker.toml)
    - Update cli.py to pass None to load_yoker_config() when --config not provided
    - **Acceptance**: Config auto-discovers from env/files, explicit path still works
  
  - [ ] **1.3.6.3: Make CLI Arguments Optional**
    - Make --server-url optional (use roomz auto-discovery)
    - Make --agent optional (use config [agents].definition)
    - Make --config optional (use yoker auto-discovery)
    - Update argument parsing in cli.py parse_args()
    - **Acceptance**: All three args optional, discovery fallback works, CLI still accepts explicit values
  
  - [ ] **1.3.6.4: Support Agent Definition from Config**
    - Update load_yoker_agent_definition() to accept optional agent_path
    - Fall back to config.agents.definition when --agent not provided
    - Provide helpful error when neither provided
    - Update cli.py to pass agent_path=None when not specified
    - **Acceptance**: Agent definition discovered from config, explicit --agent still works
  
  - [ ] **1.3.6.5: Update Client for Optional server_url**
    - Update ChatClient.__init__() type hint: server_url: str | None
    - Pass server_url=None to AsyncClient() for auto-discovery
    - Verify client.py handles missing server_url gracefully
    - **Acceptance**: ChatClient works with auto-discovered server URL
  
  - [ ] **1.3.6.6: Update _run_client() Flow**
    - Handle optional --config (pass None if not provided)
    - Handle optional --agent (pass None if not provided)
    - Handle optional --server-url (pass None if not provided)
    - Update error messages to mention auto-discovery options
    - **Acceptance**: _run_client() works with all optional args
  
  - [ ] **1.3.6.7: Test and Document**
    - Test all CLI combinations (explicit, discovery, mixed)
    - Test backward compatibility with old CLI invocations
    - Update README with auto-discovery examples
    - Document environment variables (YOKER_*, ROOMZ_SERVER_URL)
    - Document config file locations (./yoker.toml, ~/.yoker.toml)
    - **Acceptance**: All tests pass, README updated, migration guide provided

- [ ] **1.4 Session Context Management**
  - Implement --resume flag for session context resumption
  - List available session contexts with metadata
  - Allow user selection of session to resume
  - Support starting new session
  - **Satisfies**: R43-R45

- [ ] **1.5 Logging System**
  - Configure structured logging (stdout, stderr, file configurable)
  - Log incoming messages with timestamp and sender
  - Log outgoing responses with timestamp
  - Log system events (join/leave/auth/connection status)
  - Support JSON format for log aggregation
  - **Satisfies**: R50-R53

- [ ] **1.6 Configuration**
  - Support configuration via TOML file
  - Support configuration via command-line arguments
  - Support configuration via environment variables
  - Configuration options: server URL, agent definition, session cache path, mention triggers
  - **Satisfies**: R29-R34

- [ ] **1.7 Error Handling**
  - Implement structured logging for errors
  - Handle connection errors with retry
  - Handle agent errors gracefully (send error message, continue)
  - Handle malformed messages without crashing
  - Handle rate limiting from chat platform
  - **Satisfies**: R35-R39

- [ ] **1.8 Graceful Shutdown**
  - Handle SIGINT/SIGTERM for graceful shutdown
  - Complete current message processing before exit
  - Save session state on exit
  - Close connection cleanly
  - **Satisfies**: R55

### Phase 2: Polish and Testing

- [ ] **2.1 Unit Tests**
  - Test authentication flows (interactive, non-interactive, cached)
  - Test message filtering and queuing
  - Test agent response capture
  - Test session context management
  - Test error handling

- [ ] **2.2 Integration Tests**
  - Test with mock Roomz server
  - Test with mock Yoker Agent
  - Test end-to-end message flow

- [ ] **2.3 Documentation**
  - Write README with quick start guide
  - Document all configuration options
  - Create usage examples

## Done

- [x] **1.1 Project Setup** (2026-05-19)
  - Python package structure with src/ layout
  - pyproject.toml with dependencies (yoker, roomz, structlog, aiohttp)
  - Development tooling (ruff, mypy, pytest, tox)
  - CLI entry point (yoker-chat)
  - Sphinx documentation with ReadTheDocs config
  - Makefile with uv-based targets
  - GitHub Actions CI for Python 3.10, 3.11, 3.12
- [x] **1.2 Authentication Module** (2026-05-20)
  - Implement interactive login flow (prompt for email $\rightarrow$ request magic link $\rightarrow$ prompt for token)
  - Support --login and --token arguments for non-interactive authentication
  - Support --name argument to set display name (matches /name command)
  - Support session caching for automatic reconnection
  - Implement session cache file with restrictive permissions (0600)
  - Handle cached session validation and expiry
  - **Satisfies**: R1-R8
- [x] **1.3 ChatClient Class** (2026-05-20)
  - Create ChatClient class to bridge Roomz AsyncClient to Yoker Agent
  - Implement message filtering (ignore own messages, check mentions)
  - Implement message queuing for sequential processing
  - Implement agent response capture and buffering
  - Implement response sending to chat room
  - Security: Input sanitization, rate limiting, message size limits, log redaction
  - Graceful shutdown: Wait for current message before disconnecting
  - **Design**: See [analysis/api-chatclient.md](analysis/api-chatclient.md)
  - **Satisfies**: R12-R20

- [x] **1.3.5 Yoker Agent Integration** (2026-05-20)
  - Replace MockAgent with actual Yoker Agent
  - Load agent definition from file (Markdown with frontmatter)
  - Load Yoker configuration (TOML)
  - Wire up agent event handlers (ContentChunk, ContentEnd, Error)
  - Pass messages from Roomz → ChatClient → Yoker Agent
  - Send agent responses back to Roomz
  - Test end-to-end message flow with real Yoker agent
  - Filter messages by display name (not email) to support shared accounts
  - Run agent.process() in thread pool for sync-to-async compatibility
  - **Satisfies**: R12-R20