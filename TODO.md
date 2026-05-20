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

- [ ] **1.2 Authentication Module**
  - Implement interactive login flow (prompt for email → request magic link → prompt for token)
  - Support --login and --token arguments for non-interactive authentication
  - Support --name argument to set display name (matches /name command)
  - Support session caching for automatic reconnection
  - Implement session cache file with restrictive permissions (0600)
  - Handle cached session validation and expiry
  - **Satisfies**: R1-R8

- [ ] **1.3 ChatClient Class**
  - Create ChatClient class to bridge Roomz AsyncClient to Yoker Agent
  - Implement message filtering (ignore own messages, check mentions)
  - Implement message queuing for sequential processing
  - Implement agent response capture and buffering
  - Implement response sending to chat room
  - **Satisfies**: R12-R20

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