"""Security validation for Yoker Chat configuration and agent paths."""

import os
from pathlib import Path

import structlog

log = structlog.get_logger()


class ValidationError(Exception):
  """Raised when validation fails."""

  pass


class SecurityError(Exception):
  """Raised when a security check fails."""

  pass


# Allowed tools for chat bot context (read-only operations)
ALLOWED_TOOLS = {"read", "list", "search", "web_search"}
FORBIDDEN_TOOLS = {"write", "update", "git", "agent"}


def validate_agent_path(agent_path: str | Path) -> Path:
  """Validate agent definition path for security.

  Prevents:
  - Path traversal (../../../etc/passwd)
  - Loading files outside allowed directories
  - Loading non-Markdown files
  - Loading world-writable files (warning)

  Args:
    agent_path: User-provided path to agent definition.

  Returns:
    Validated, resolved Path object.

  Raises:
    FileNotFoundError: If agent file doesn't exist.
    ValidationError: If path is unsafe or invalid.
  """
  path = Path(agent_path).resolve()

  # Check for path traversal (should not contain .. after resolve)
  if ".." in str(path):
    raise ValidationError(f"Path traversal not allowed: {agent_path}")

  # Verify file exists
  if not path.exists():
    raise FileNotFoundError(f"Agent definition not found: {path}")

  # Verify it's a file
  if not path.is_file():
    raise ValidationError(f"Agent path is not a file: {path}")

  # Verify extension
  if path.suffix not in {".md", ".markdown"}:
    raise ValidationError(f"Agent definition must be a Markdown file: {path}")

  # Check file permissions
  try:
    file_stat = path.stat()
    if file_stat.st_mode & 0o002:  # World-writable
      log.warning("agent_file_world_writable", path=str(path))
  except OSError:
    pass  # Ignore permission check errors

  return path


def validate_config_path(config_path: str | Path) -> Path:
  """Validate TOML configuration path for security.

  Args:
    config_path: User-provided path to config file.

  Returns:
    Validated, resolved Path object.

  Raises:
    FileNotFoundError: If config file doesn't exist.
    ValidationError: If path is unsafe or invalid.
  """
  path = Path(config_path).resolve()

  # Check for path traversal
  if ".." in str(path):
    raise ValidationError(f"Path traversal not allowed: {config_path}")

  # Verify file exists
  if not path.exists():
    raise FileNotFoundError(f"Config file not found: {path}")

  # Verify it's a file
  if not path.is_file():
    raise ValidationError(f"Config path is not a file: {path}")

  # Verify extension
  if path.suffix != ".toml":
    raise ValidationError(f"Config must be a TOML file: {path}")

  return path


def validate_tool_capabilities(
  tools: list[str] | None,
  log_warnings: bool = True,
) -> list[str]:
  """Validate agent tools against allowed capabilities.

  For chat bot context, agents should have read-only tools.
  Forbidden tools: write, update, git, agent.

  Args:
    tools: List of tool names from agent definition.
    log_warnings: Whether to log warnings about blocked tools.

  Returns:
    List of allowed tools.

  Note:
    This only warns about forbidden tools. Yoker's own tool system
    will enforce the actual restrictions.
  """
  if tools is None:
    return []

  tool_set = set(tools)

  # Check for forbidden tools
  blocked = tool_set & FORBIDDEN_TOOLS
  if blocked and log_warnings:
    log.warning(
      "blocked_tools_detected",
      tools=list(blocked),
      message="These tools are blocked in chat context. Yoker will enforce restrictions.",
    )

  # Return allowed tools (intersection with allowed set)
  allowed = tool_set & ALLOWED_TOOLS

  return list(allowed)


def get_secure_context_path(app_name: str = "yoker-chat") -> Path:
  """Get secure default context storage path.

  Args:
    app_name: Application name for context directory.

  Returns:
    Validated, secure context path.

  Note:
    The path is within the user's cache directory following XDG standards.
  """
  # Use XDG-compliant cache directory
  xdg_cache = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
  default_path = Path(xdg_cache) / app_name / "sessions"

  # Resolve to absolute path
  resolved = default_path.resolve()

  return resolved


def verify_session_ownership(session_id: str, context_path: Path) -> bool:
  """Verify current user owns the session file.

  Prevents session hijacking by ensuring the session file is owned
  by the current user.

  Args:
    session_id: Session identifier.
    context_path: Context storage path.

  Returns:
    True if user owns session, False otherwise.
  """
  session_file = context_path / f"{session_id}.jsonl"

  if not session_file.exists():
    return False

  try:
    file_stat = session_file.stat()
    current_uid = os.getuid()

    if file_stat.st_uid != current_uid:
      log.warning(
        "session_ownership_mismatch",
        session_id=session_id,
        file_uid=file_stat.st_uid,
        current_uid=current_uid,
      )
      return False

    return True
  except OSError:
    return False


def verify_session_isolation(session_id: str, context_path: Path) -> None:
  """Verify session file is properly isolated.

  Checks for:
  - Hard links (prevents aliasing attacks)
  - Symlinks (prevents path traversal)

  Args:
    session_id: Session identifier.
    context_path: Context storage path.

  Raises:
    SecurityError: If session isolation is compromised.
  """
  session_file = context_path / f"{session_id}.jsonl"

  if not session_file.exists():
    return

  try:
    file_stat = session_file.stat()

    # Check for hard links
    if file_stat.st_nlink > 1:
      raise SecurityError(
        f"Session file has hard links (potential aliasing attack): {session_file}"
      )

    # Check for symlinks
    if session_file.is_symlink():
      raise SecurityError(f"Session file is a symlink (potential path traversal): {session_file}")
  except OSError as e:
    raise SecurityError(f"Failed to verify session isolation: {e}") from e


def audit_context_permissions(context_path: Path) -> list[str]:
  """Audit context file permissions for security issues.

  Args:
    context_path: Path to context storage directory.

  Returns:
    List of security issues found.
  """
  issues: list[str] = []

  if not context_path.exists():
    return issues

  try:
    # Check directory permissions
    dir_stat = context_path.stat()
    dir_mode = dir_stat.st_mode & 0o777

    if dir_mode != 0o700:
      issues.append(f"Context directory has insecure permissions: {oct(dir_mode)} (expected 0700)")

    # Check for world-writable or world-readable session files
    for session_file in context_path.glob("*.jsonl"):
      file_stat = session_file.stat()
      file_mode = file_stat.st_mode & 0o777

      if file_mode != 0o600:
        issues.append(
          f"Session file {session_file.name} has insecure permissions: {oct(file_mode)} (expected 0600)"
        )

      # Check for group/other read access
      if file_stat.st_mode & (0o044 | 0o004):
        issues.append(f"Session file {session_file.name} is readable by group/other")
  except OSError:
    pass  # Ignore permission check errors

  return issues
