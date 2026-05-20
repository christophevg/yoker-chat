# Consensus Report: Yoker Agent Integration (Task 1.3.5)

**Date**: 2026-05-20
**Task**: 1.3.5 Yoker Agent Integration
**Status**: Approved for Implementation

---

## Summary

Both the API Architect and Security Engineer have reviewed the Yoker Agent Integration requirements. The consensus is that:

1. **The integration is straightforward** - The current ChatClient implementation is already compatible with the Yoker Agent API
2. **Security mitigations are required** - Critical findings from security analysis must be addressed
3. **Implementation is primarily in cli.py** - Minimal changes needed in client.py

---

## API Architect Findings

### Integration Architecture

```
Roomz AsyncClient → ChatClient → Yoker Agent
      ↑                  ↓            ↓
   WebSocket        Buffer/Queue  Events
```

### Key Points

1. **Event Handler Compatibility**: Current ChatClient handlers (`_on_agent_content_chunk`, `_on_agent_content_end`, `_on_agent_error`) work directly with Yoker Agent events
2. **Agent Initialization**: Requires config loading, agent definition loading, and context manager setup
3. **Context Management**: Yoker's `BasicPersistenceContextManager` handles session persistence

### Implementation Requirements

```python
from yoker import Agent
from yoker.config import load_config
from yoker.agents import load_agent_definition
from yoker.context import BasicPersistenceContextManager
from yoker.thinking import ThinkingMode

# In cli.py:
config = load_config(args.config)
agent_definition = load_agent_definition(args.agent)
context_manager = BasicPersistenceContextManager(
    storage_path=Path(config.context.storage_path),
    session_id=config.context.session_id,
)
agent = Agent(
    config=config,
    agent_definition=agent_definition,
    context_manager=context_manager,
    thinking_mode=ThinkingMode.SILENT,  # For chat context
)
```

---

## Security Engineer Findings

### Critical Findings (Must Mitigate)

| ID | Finding | CVSS | Mitigation |
|----|---------|------|------------|
| CRITICAL-01 | Malicious agent definition file loading | 9.0 | Path validation, extension check, tool whitelist |
| CRITICAL-02 | Configuration file injection | 9.0 | Config path validation, security constraint enforcement |
| CRITICAL-03 | Tool capability escalation | 10.0 | Static capability model, runtime tool filtering |

### High Findings (Should Mitigate)

| ID | Finding | CVSS | Mitigation |
|----|---------|------|------------|
| HIGH-01 | Context/session data exposure | 8.0 | Secure context path, permission audit |
| HIGH-02 | Resume session attack surface | 7.5 | Session ownership verification, integrity checks |
| HIGH-03 | Path traversal in agent definition loading | 7.0 | Path validation, allowed directory whitelist |

### Approved Tool Capabilities for ChatClient

For a chat bot, the agent should have **read-only tools**:
- ✅ `read` - Read files
- ✅ `list` - List directories
- ✅ `search` - Search files
- ✅ `web_search` - Search the web (with guardrails)
- ❌ `write` - Write files (blocked)
- ❌ `update` - Update files (blocked)
- ❌ `git` - Git operations (blocked)
- ❌ `agent` - Spawn sub-agents (blocked)

---

## Consensus on Implementation Approach

### Phase 1: Core Integration (cli.py)

1. **Replace MockAgent with Yoker Agent initialization**
   - Load config from `--config` argument
   - Load agent definition from `--agent` argument
   - Create context manager for session persistence
   - Pass agent to ChatClient

2. **Add path validation**
   - Validate `--config` path exists and is readable
   - Validate `--agent` path exists and is readable
   - Block path traversal attempts (`../`, `..\\`)
   - Check file extension (.toml for config, .md for agent)

3. **Add security logging**
   - Log loaded config path
   - Log loaded agent definition path
   - Log available tools

### Phase 2: Security Enhancements

1. **Tool capability enforcement**
   - Define allowed tools for chat context
   - Validate agent definition tools against allowlist
   - Warn if agent requests forbidden tools
   - Log capability violations

2. **Context security**
   - Use secure default for context storage path
   - Set file permissions (0600) for session files
   - Set directory permissions (0700) for session directory

### Phase 3: Error Handling

1. **Configuration errors**
   - Handle missing config file gracefully
   - Handle invalid TOML syntax
   - Exit with helpful error message

2. **Agent definition errors**
   - Handle missing agent definition file gracefully
   - Handle invalid YAML frontmatter
   - Handle missing required fields

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/yoker_chat/cli.py` | Replace MockAgent, add config/agent loading, add path validation |
| `src/yoker_chat/client.py` | Verify compatibility (minimal changes) |

---

## Test Coverage

53 tests in `tests/test_yoker_integration.py` covering:
- Agent initialization (9 tests)
- Event handler compatibility (7 tests)
- Message flow (5 tests)
- Error handling (5 tests)
- Context management (8 tests)
- Security validation (11 tests)
- Integration with real agent (4 tests)
- CLI argument handling (8 tests)

---

## Dependencies

Add to `pyproject.toml`:
```toml
[project]
dependencies = [
    "yoker>=0.1.0",  # From sibling directory or PyPI
    # ... existing dependencies
]
```

---

## Approval

| Reviewer | Status | Notes |
|----------|--------|-------|
| API Architect | ✅ Approved | Architecture sound, minimal changes needed |
| Security Engineer | ✅ Approved with conditions | Critical findings must be mitigated |

---

## Implementation Order

1. Add `yoker` dependency to `pyproject.toml`
2. Modify `cli.py` to load config and agent definition
3. Add path validation for `--config` and `--agent` arguments
4. Add tool capability validation
5. Replace MockAgent with Yoker Agent
6. Test with real Yoker Agent
7. Remove MockAgent (optional: keep for unit tests)

---

## Next Steps

Proceed to **Phase 4: Implementation** with the python-developer agent.