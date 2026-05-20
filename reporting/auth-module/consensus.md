# Consensus Report: Authentication Module (Task 1.2)

## Overview
This report documents the agreement between the API Architect, Security Engineer, and Testing Engineer on the implementation of the authentication module for the Yoker Chat Client.

## Agreed Implementation Plan

### 1. Authentication Flow
- The client will support three modes of credential gathering:
  - **Interactive**: `input()` for email, then `getpass.getpass()` for the token.
  - **CLI Arguments**: `--login` and `--token`.
  - **Environment Variables**: `YOKER_CHAT_TOKEN` as a fallback for `--token`.
- **State Machine**: Following the transition model defined in `analysis/api-auth.md`.

### 2. Session Persistence
- **Cache File**: `~/.cache/yoker-chat/session.json`
- **Secure Storage**:
  - Files must be created with **0600 permissions** (read/write only by owner).
  - Implementation will use `os.open` with `os.O_CREAT | os.O_WRONLY` and mode `0o600` to ensure the file is never created with loose permissions.
- **Lifecycle**:
  - Save session cookie and server URL upon successful authentication.
  - Automatically attempt reconnection using the cached cookie on startup.
  - Clear the cache file if a session is found to be expired or invalid.

### 3. Security Guardrails
- **Log Redaction**: A custom `structlog` processor will be implemented to redact keys: `token`, `session_cookie`, `password`.
- **CLI Security**: Users will be warned in the help text that passing secrets via `--token` is insecure and that `YOKER_CHAT_TOKEN` is preferred.
- **Echo Prevention**: Interactive token entry will use `getpass.getpass()` to prevent shoulder-surfing.

### 4. Testing Strategy
- **TDD Approach**: Implementation will be driven by the stubs in `tests/test_auth.py`.
- **Verification**:
  - Mock `Roomz.AsyncClient` to verify the sequence of auth calls.
  - Use a temporary directory for session cache tests to verify file permissions.
  - Verify log output for redaction.

## Approval
- [x] API Architect
- [x] Security Engineer
- [x] Testing Engineer
