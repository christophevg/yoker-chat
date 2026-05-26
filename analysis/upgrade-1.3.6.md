# Analysis: Dependency Upgrade and Codebase Simplification (Task 1.3.6)

**Date**: 2026-05-26
**Task**: Upgrade yoker and roomz dependencies, simplify codebase using new features

---

## Overview

This task involves upgrading two dependencies to their latest versions and refactoring the codebase to take advantage of new auto-discovery features that simplify configuration and CLI usage.

### Dependencies to Upgrade

| Package | Current | Target | Breaking Changes |
|---------|---------|--------|------------------|
| yoker   | 0.3.1   | 0.4.0  | None - backward compatible |
| roomz   | 0.1.0   | 0.2.0  | None - backward compatible |

Both upgrades are backward compatible, so existing functionality will continue to work.

---

## New Features Available

### yoker 0.4.0 Features

#### 1. Config.discover() - Auto-Discovery

**Current approach** (requires explicit path):
```python
from yoker import load_config
config = load_config(validated_path)
```

**New approach** (auto-discovers from multiple sources):
```python
from yoker import Config
config = Config.discover()  # Searches in order:
                            # 1. Environment variables (YOKER_*)
                            # 2. ./yoker.toml (current directory)
                            # 3. ~/.yoker.toml (home directory)
```

**Benefits**:
- No longer need to specify `--config` explicitly
- Follows XDG-style discovery conventions
- Environment variables can override file config
- Reduces CLI arguments needed

#### 2. agents.definition in Config

**Current approach** (requires explicit path):
```python
agent_definition = load_agent_definition(agent_path)
```

**New approach** (can specify in yoker.toml):
```toml
[agents]
definition = "path/to/agent.md"
```

**Benefits**:
- Agent path can be configured, not just CLI argument
- Different environments can have different agents
- Reduces CLI arguments needed

### roomz 0.2.0 Features

#### 1. Server URL Auto-Discovery

**Current approach** (requires explicit path):
```python
AsyncClient(server_url="https://...")
```

**New approach** (auto-discovers):
```python
# Discovers from:
# 1. ROOMZ_SERVER_URL environment variable
# 2. ~/.roomz.toml
# 3. ./roomz.toml
AsyncClient()  # server_url auto-discovered
```

**Benefits**:
- No longer need to specify `--server-url` explicitly
- Environment-based configuration
- Matches yoker's discovery pattern

#### 2. Display Names

**Already implemented correctly** in client.py:
```python
self.roomz_client = AsyncClient(
  server_url=self.server_url,
  session_cache_file=session_cache_path,
  display_name=name,  # ✓ Already using this
)
```

No changes needed - client.py already uses the new display name feature.

---

## Implementation Plan

### Phase 1: Dependency Upgrade

**File**: pyproject.toml (lines 26-32)

**Changes**:
```toml
dependencies = [
  "yoker>=0.4.0",      # Upgrade from 0.3.1
  "roomz>=0.2.0",      # Upgrade from 0.1.0
  "structlog>=23.0.0",
  "aiohttp>=3.8.0",
  "python-dotenv>=1.2.2",
]
```

**Rationale**: Both upgrades are backward compatible, so this is a straightforward version bump.

---

### Phase 2: Simplify Configuration Loading

**File**: cli.py

**Current load_yoker_config() (lines 112-136)**:
```python
def load_yoker_config(config_path: Path) -> Any:
  from yoker import ConfigurationError, load_config
  
  validated_path = validate_config_path(config_path)
  
  try:
    config = load_config(validated_path)
    log.info("config_loaded", path=str(validated_path))
    return config
  except ConfigurationError as e:
    log.error("config_invalid", path=str(validated_path), error=str(e))
    raise
```

**Refactored approach**:
```python
def load_yoker_config(config_path: Path | None) -> Any:
  """Load Yoker configuration using auto-discovery.
  
  Discovery order:
  1. Explicit path (if provided via --config)
  2. Environment variables (YOKER_*)
  3. ./yoker.toml (current directory)
  4. ~/.yoker.toml (home directory)
  
  Args:
    config_path: Optional explicit path to config file.
    
  Returns:
    Config object.
    
  Raises:
    ConfigurationError: If configuration is invalid.
  """
  from yoker import ConfigurationError
  
  try:
    if config_path:
      # Explicit path provided - validate and load
      validated_path = validate_config_path(config_path)
      log.info("loading_config_from_path", path=str(validated_path))
      config = Config.from_file(validated_path)
    else:
      # Use auto-discovery
      log.info("auto_discovering_config")
      config = Config.discover()
    
    log.info("config_loaded", source=config._source if hasattr(config, '_source') else 'discovery')
    return config
  except ConfigurationError as e:
    log.error("config_invalid", path=str(config_path) if config_path else 'discovery', error=str(e))
    raise
```

**Note**: Need to verify the exact API of yoker 0.4.0's Config.discover() - it may return a Config object or still use load_config semantics.

---

### Phase 3: Make CLI Arguments Optional

**File**: cli.py (lines 24-95)

#### Change 1: --server-url (currently required)

**Current**:
```python
parser.add_argument(
  "--server-url",
  required=True,
  help="Roomz server URL (or set ROOMZ_SERVER_URL env var)",
)
```

**New**:
```python
parser.add_argument(
  "--server-url",
  help="Roomz server URL (auto-discovered from ROOMZ_SERVER_URL env, ~/.roomz.toml, ./roomz.toml)",
)
```

**Implementation**: Pass `server_url=args.server_url` to `AsyncClient()` - it will handle None by using auto-discovery.

#### Change 2: --agent (currently required)

**Current**:
```python
parser.add_argument(
  "--agent",
  required=True,
  help="Path to agent definition file (Markdown with YAML frontmatter)",
)
```

**New**:
```python
parser.add_argument(
  "--agent",
  help="Path to agent definition file (auto-discovered from yoker.toml [agents].definition)",
)
```

**Implementation**:
- Try explicit `--agent` path first
- Fall back to `config.agents.definition` if available
- Error if neither provided

#### Change 3: --config (already optional)

**Current**:
```python
parser.add_argument(
  "--config",
  default="yoker.toml",
  help="Path to Yoker config file (default: yoker.toml)",
)
```

**New**:
```python
parser.add_argument(
  "--config",
  help="Path to Yoker config file (auto-discovered from YOKER_* env vars, ./yoker.toml, ~/.yoker.toml)",
)
```

**Implementation**: Remove default, pass None to `load_yoker_config()` if not provided.

---

### Phase 4: Update Agent Definition Loading

**File**: cli.py (lines 138-174)

**Current approach**:
```python
def load_yoker_agent_definition(agent_path: Path) -> Any:
  from yoker import ConfigurationError
  from yoker.agents import load_agent_definition
  
  validated_path = validate_agent_path(agent_path)
  
  try:
    agent_definition = load_agent_definition(validated_path)
    ...
```

**New approach** (support both explicit and configured paths):
```python
def load_yoker_agent_definition(agent_path: Path | None, config: Any) -> Any:
  """Load agent definition from explicit path or config.
  
  Args:
    agent_path: Optional explicit path to agent definition.
    config: Yoker configuration (may contain agents.definition).
    
  Returns:
    AgentDefinition object.
    
  Raises:
    FileNotFoundError: If agent file doesn't exist and not in config.
    ConfigurationError: If agent definition is invalid.
  """
  from yoker import ConfigurationError
  from yoker.agents import load_agent_definition
  
  # Determine path to use
  path_to_use = None
  if agent_path:
    path_to_use = validate_agent_path(agent_path)
    log.info("agent_path_from_cli", path=str(path_to_use))
  elif config and hasattr(config, 'agents') and hasattr(config.agents, 'definition'):
    config_path = Path(config.agents.definition).expanduser()
    path_to_use = validate_agent_path(config_path)
    log.info("agent_path_from_config", path=str(path_to_use))
  else:
    raise FileNotFoundError(
      "No agent definition provided. Use --agent or configure [agents].definition in yoker.toml"
    )
  
  try:
    agent_definition = load_agent_definition(path_to_use)
    log.info(
      "agent_loaded",
      path=str(path_to_use),
      name=getattr(agent_definition, "name", "unknown"),
      tools=getattr(agent_definition, "tools", []),
    )
    
    # Validate tool capabilities
    tools = getattr(agent_definition, "tools", None)
    if tools:
      validate_tool_capabilities(list(tools), log_warnings=True)
    
    return agent_definition
  except ConfigurationError as e:
    log.error("agent_invalid", path=str(path_to_use), error=str(e))
    raise
```

---

### Phase 5: Update _run_client() Flow

**File**: cli.py (lines 253-362)

**Changes needed**:

1. **Config loading** (lines 258-269):
```python
# Phase 1: Load configuration
# ─────────────────────────────────────────────────────────────────────────
try:
  config_path = Path(args.config) if args.config else None
  config = load_yoker_config(config_path)
except FileNotFoundError as e:
  print(f"Error: Configuration file not found: {e}")
  print("Use --config path or set YOKER_* environment variables")
  exit(1)
except Exception as e:
  print(f"Error: Invalid configuration: {e}")
  print(f"Check {args.config} for errors" if args.config else "Check configuration")
  exit(1)
```

2. **Agent definition loading** (lines 271-283):
```python
# Phase 2: Load agent definition
# ─────────────────────────────────────────────────────────────────────────
try:
  agent_path = Path(args.agent) if args.agent else None
  agent_definition = load_yoker_agent_definition(agent_path, config)
except FileNotFoundError as e:
  print(f"Error: Agent definition not found: {e}")
  print("Use --agent path or configure [agents].definition in yoker.toml")
  exit(1)
except Exception as e:
  print(f"Error: Invalid agent definition: {e}")
  exit(1)
```

3. **ChatClient initialization** (lines 326-339):
```python
# Phase 5: Create ChatClient
# ─────────────────────────────────────────────────────────────────────────
agent_name = args.name or getattr(agent_definition, "name", "ChatBot")

# Expand ~ in session cache path
session_cache_path = str(Path(args.session_cache).expanduser())

client = ChatClient(
  server_url=args.server_url,  # None triggers auto-discovery in roomz
  agent=agent,
  session_cache_path=session_cache_path,
  name=agent_name,
  mention_triggers=args.mention_trigger,
)
```

**Note**: The `ChatClient` constructor needs to handle `server_url=None` properly, letting the `AsyncClient` use its auto-discovery.

---

### Phase 6: Update ChatClient for Optional server_url

**File**: client.py (lines 80-122)

**Current constructor**:
```python
def __init__(
  self,
  server_url: str,
  agent: Any,
  session_cache_path: str,
  ...
) -> None:
  ...
  self.server_url = server_url
  ...
  self.roomz_client = AsyncClient(
    server_url=self.server_url,
    session_cache_file=session_cache_path,
    display_name=name,
  )
```

**Updated constructor**:
```python
def __init__(
  self,
  server_url: str | None,
  agent: Any,
  session_cache_path: str,
  ...
) -> None:
  ...
  self.server_url = server_url
  ...
  self.roomz_client = AsyncClient(
    server_url=self.server_url,  # None triggers auto-discovery
    session_cache_file=session_cache_path,
    display_name=name,
  )
```

**Type hints**: Change `server_url: str` to `server_url: str | None`.

---

### Phase 7: Update validation.py

**File**: validation.py

**No changes needed** - the validation functions already handle optional paths correctly:
- `validate_config_path()` expects a path (called only when explicit path provided)
- `validate_agent_path()` expects a path (called only when explicit path provided)

The new pattern is:
- If explicit path → validate it
- If auto-discovery → let the library handle it

---

## Testing Considerations

### Test Cases

1. **Dependency Upgrade Tests**:
   ```bash
   # Verify imports still work
   python -c "from yoker import Config; print('yoker OK')"
   python -c "from roomz import AsyncClient; print('roomz OK')"
   ```

2. **Config Discovery Tests**:
   - No config file, no env vars → should error gracefully
   - Only env vars (YOKER_*) → should work
   - Only ./yoker.toml → should work
   - Only ~/.yoker.toml → should work
   - Explicit --config → should override discovery

3. **Agent Definition Discovery Tests**:
   - Explicit --agent → should use it
   - No --agent but config has [agents].definition → should use it
   - Neither → should error with helpful message

4. **Server URL Discovery Tests**:
   - Explicit --server-url → should use it
   - No --server-url but ROOMZ_SERVER_URL env → should use it
   - No --server-url but ~/.roomz.toml → should use it
   - Neither → should error with helpful message

5. **Backward Compatibility Tests**:
   - Old CLI with --config and --agent → should still work
   - Old CLI with --server-url → should still work

### Integration Testing

```bash
# Test with explicit config
yoker-chat --config yoker.toml --agent agent.md --server-url https://...

# Test with auto-discovery (new)
yoker-chat  # Discovers everything from env/files

# Test with partial discovery
yoker-chat --agent custom.md  # Config and server from discovery
```

---

## Migration Guide for Users

### Before (0.3.1/0.1.0)

```bash
# Required to specify everything
yoker-chat \
  --server-url https://chat.example.com \
  --agent ./agent.md \
  --config ./yoker.toml
```

### After (0.4.0/0.2.0)

**Option 1: Full auto-discovery** (recommended for production)
```bash
# Set environment variables
export YOKER_API_KEY=sk-...
export ROOMZ_SERVER_URL=https://chat.example.com

# Create config files
cat > ~/.yoker.toml << EOF
[agents]
definition = "~/agents/chat-bot.md"

[llm]
model = "claude-3-5-sonnet-20241022"
EOF

# Run with no arguments
yoker-chat
```

**Option 2: Mix of discovery and CLI** (recommended for development)
```bash
# Config from file, server from env, agent from CLI
export ROOMZ_SERVER_URL=https://chat.example.com
yoker-chat --agent ./dev-agent.md
```

**Option 3: All CLI** (backward compatible)
```bash
# Old CLI still works
yoker-chat \
  --server-url https://chat.example.com \
  --agent ./agent.md \
  --config ./yoker.toml
```

---

## Files to Modify

### Summary

| File | Lines | Changes |
|------|-------|---------|
| pyproject.toml | 26-32 | Update dependency versions |
| cli.py | 24-95 | Make --server-url, --agent, --config optional |
| cli.py | 112-136 | Refactor load_yoker_config() to use Config.discover() |
| cli.py | 138-174 | Update load_yoker_agent_definition() to support config fallback |
| cli.py | 253-362 | Update _run_client() to handle optional args |
| client.py | 80-122 | Update type hint for server_url |
| validation.py | - | No changes needed |

---

## Acceptance Criteria

### Must Have

1. **Dependencies upgraded**:
   - [ ] yoker>=0.4.0 in pyproject.toml
   - [ ] roomz>=0.2.0 in pyproject.toml
   - [ ] All imports still work after upgrade

2. **Config auto-discovery works**:
   - [ ] `Config.discover()` used when no --config provided
   - [ ] Explicit --config still works (backward compatible)
   - [ ] Environment variables (YOKER_*) are discovered
   - [ ] ~/.yoker.toml is discovered

3. **Agent definition discovery works**:
   - [ ] Explicit --agent still works (backward compatible)
   - [ ] Config [agents].definition is used when --agent not provided
   - [ ] Error message is helpful when neither provided

4. **Server URL discovery works**:
   - [ ] Explicit --server-url still works (backward compatible)
   - [ ] ROOMZ_SERVER_URL environment variable is discovered
   - [ ] ~/.roomz.toml is discovered
   - [ ] Error message is helpful when neither provided

5. **Backward compatibility**:
   - [ ] Old CLI invocations still work
   - [ ] No breaking changes to existing users

### Should Have

6. **Documentation updated**:
   - [ ] README documents auto-discovery
   - [ ] Migration guide provided for users
   - [ ] Environment variables documented

7. **Tests pass**:
   - [ ] Existing tests still pass
   - [ ] New discovery scenarios tested

### Nice to Have

8. **Error messages improved**:
   - [ ] Clear message when no config found
   - [ ] Clear message when no agent definition found
   - [ ] Clear message when no server URL found

---

## Risks and Mitigations

### Risk 1: yoker 0.4.0 API Differences

**Risk**: The `Config.discover()` API might be different from assumed.

**Mitigation**: 
- Check yoker 0.4.0 documentation after release
- Use `pkg-info:find` skill to get actual API
- Test with actual package before committing

### Risk 2: roomz 0.2.0 Discovery Implementation

**Risk**: roomz auto-discovery might require explicit initialization.

**Mitigation**:
- Verify AsyncClient() works with server_url=None
- Test discovery fallback chain
- Document expected behavior

### Risk 3: Breaking Changes in Upstream

**Risk**: Despite backward compatibility claims, there might be edge cases.

**Mitigation**:
- Run full test suite after upgrade
- Test all CLI combinations
- Verify with real Yoker agent and Roomz server

---

## Implementation Order

1. **Upgrade dependencies first** (allows testing)
2. **Refactor load_yoker_config()** (foundation for other changes)
3. **Update CLI argument parsing** (make args optional)
4. **Update agent definition loading** (support config fallback)
5. **Update _run_client() flow** (wire everything together)
6. **Update ChatClient type hints** (support optional server_url)
7. **Test all scenarios** (backward compatibility + new discovery)
8. **Update documentation** (README + migration guide)

---

## Next Steps

1. Use `pkg-info:find` to verify yoker 0.4.0 and roomz 0.2.0 APIs
2. Create sub-tasks in TODO.md
3. Implement changes in order
4. Test thoroughly
5. Update documentation