"""CLI entry point for yoker-chat."""

import argparse
import asyncio
import logging
from pathlib import Path

import structlog

from yoker_chat.client import ChatClient
from yoker_chat.logging import get_default_processors
from yoker_chat.validation import (
  ALLOWED_TOOLS,
  FORBIDDEN_TOOLS,
  validate_agent_path,
  validate_config_path,
  validate_tool_capabilities,
)

log = structlog.get_logger()


def parse_args() -> argparse.Namespace:
  """Parse command-line arguments."""
  parser = argparse.ArgumentParser(
    prog="yoker-chat",
    description="Chat client that bridges Roomz chat rooms to Yoker agents",
  )

  parser.add_argument(
    "--server-url",
    required=True,
    help="Roomz server URL (or set ROOMZ_SERVER_URL env var)",
  )

  parser.add_argument(
    "--agent",
    required=True,
    help="Path to agent definition file (Markdown with YAML frontmatter)",
  )

  parser.add_argument(
    "--config",
    default="yoker.toml",
    help="Path to Yoker config file (default: yoker.toml)",
  )

  parser.add_argument(
    "--session-cache",
    default="~/.cache/yoker-chat/session.json",
    help="Path to session cache file",
  )

  parser.add_argument(
    "--mention-trigger",
    action="append",
    default=["@bot"],
    help="Mention triggers that cause bot to respond (default: @bot)",
  )

  parser.add_argument(
    "--login",
    help="Email address for authentication (non-interactive mode)",
  )

  parser.add_argument(
    "--token",
    help="Magic link token for authentication (non-interactive mode). Note: Passing tokens via CLI is insecure; YOKER_CHAT_TOKEN env var is preferred.",
  )

  parser.add_argument(
    "--name",
    help="Display name in chat (default: agent name from definition)",
  )

  parser.add_argument(
    "--resume",
    action="store_true",
    help="Resume a previous session context",
  )

  parser.add_argument(
    "--log-file",
    help="Path to log file (default: stdout)",
  )

  parser.add_argument(
    "--log-format",
    choices=["text", "json"],
    default="text",
    help="Log format (default: text)",
  )

  return parser.parse_args()


def setup_logging(log_file: str | None, log_format: str) -> None:
  """Configure structured logging."""
  # Note: log_file is not yet used - will be implemented with file handler
  _ = log_file  # Suppress unused variable warning

  processors = get_default_processors(log_format)

  structlog.configure(
    processors=processors,  # type: ignore[arg-type]
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    cache_logger_on_first_use=True,
  )


def load_yoker_config(config_path: Path) -> object:
  """Load Yoker configuration from TOML file.

  Args:
    config_path: Path to configuration file.

  Returns:
    Config object.

  Raises:
    FileNotFoundError: If config file doesn't exist.
    ConfigurationError: If configuration is invalid.
  """
  from yoker import ConfigurationError, load_config

  validated_path = validate_config_path(config_path)

  try:
    config = load_config(validated_path)
    log.info("config_loaded", path=str(validated_path))
    return config
  except ConfigurationError as e:
    log.error("config_invalid", path=str(validated_path), error=str(e))
    raise


def load_yoker_agent_definition(agent_path: Path) -> object:
  """Load agent definition from Markdown file.

  Args:
    agent_path: Path to agent definition file.

  Returns:
    AgentDefinition object.

  Raises:
    FileNotFoundError: If agent file doesn't exist.
    ConfigurationError: If agent definition is invalid.
  """
  from yoker import ConfigurationError
  from yoker.agents import load_agent_definition

  validated_path = validate_agent_path(agent_path)

  try:
    agent_definition = load_agent_definition(validated_path)
    log.info(
      "agent_loaded",
      path=str(validated_path),
      name=getattr(agent_definition, "name", "unknown"),
      tools=getattr(agent_definition, "tools", []),
    )

    # Validate tool capabilities
    tools = getattr(agent_definition, "tools", None)
    if tools:
      validate_tool_capabilities(list(tools), log_warnings=True)

    return agent_definition
  except ConfigurationError as e:
    log.error("agent_invalid", path=str(validated_path), error=str(e))
    raise


def create_context_manager(
  resume: bool,
  config: object,
) -> object | None:
  """Create context manager for session persistence.

  Args:
    resume: Whether to resume previous session.
    config: Yoker configuration.

  Returns:
    ContextManager instance or None for new session.

  Raises:
    SessionNotFoundError: If resume requested but no sessions found.
  """
  from yoker import BasicPersistenceContextManager, SessionNotFoundError
  from yoker.context import list_sessions

  # Get storage path from config or use default
  storage_path = getattr(config, "context", None)
  if storage_path:
    storage_path = getattr(storage_path, "storage_path", None)
    if storage_path:
      storage_path = Path(storage_path).expanduser()

  if resume:
    # List available sessions
    sessions = list_sessions(storage_path=storage_path)

    if not sessions:
      log.warning("no_sessions_found", action="starting_new_session")
      return None

    # Let user select session
    print("\nAvailable sessions:")
    print("  [0] Start new session")
    for i, session in enumerate(sessions, start=1):
      print(f"  [{i}] {session.session_id}")
      print(f"      Messages: {session.message_count}")
      if hasattr(session, "last_turn_time") and session.last_turn_time:
        print(f"      Last turn: {session.last_turn_time}")

    while True:
      try:
        choice = input(f"\nSelect session [0-{len(sessions)}]: ")
        idx = int(choice)
        if idx == 0:
          return None
        if 1 <= idx <= len(sessions):
          session = sessions[idx - 1]
          log.info("resuming_session", session_id=session.session_id)
          print(f"Resuming session: {session.session_id}")
          return BasicPersistenceContextManager.resume(
            storage_path=storage_path,
            session_id=session.session_id,
          )
        print("Invalid choice. Please try again.")
      except ValueError:
        print("Please enter a number.")
      except SessionNotFoundError as e:
        log.error("session_not_found", session_id=str(choice), error=str(e))
        print(f"Session not found: {e}")
        return None
  else:
    # Create new context manager
    session_id = "auto"
    context_config = getattr(config, "context", None)
    if context_config:
      session_id = getattr(context_config, "session_id", "auto")

    return BasicPersistenceContextManager(
      storage_path=storage_path,
      session_id=session_id,
    )


async def _run_client(args: argparse.Namespace) -> None:
  """Initialize and run the chat client."""
  from yoker import Agent, ThinkingMode

  # Phase 1: Load configuration
  # ─────────────────────────────────────────────────────────────────────────
  try:
    config_path = Path(args.config)
    config = load_yoker_config(config_path)
  except FileNotFoundError as e:
    print(f"Error: Configuration file not found: {e}")
    print("Create a yoker.toml file or specify --config path")
    exit(1)
  except Exception as e:
    print(f"Error: Invalid configuration: {e}")
    print(f"Check {args.config} for errors")
    exit(1)

  # Phase 2: Load agent definition
  # ─────────────────────────────────────────────────────────────────────────
  try:
    agent_path = Path(args.agent)
    agent_definition = load_yoker_agent_definition(agent_path)
  except FileNotFoundError as e:
    print(f"Error: Agent definition not found: {e}")
    print("Create an agent definition file (Markdown with YAML frontmatter)")
    exit(1)
  except Exception as e:
    print(f"Error: Invalid agent definition: {e}")
    print(f"Check {args.agent} for required fields (name, description, tools)")
    exit(1)

  # Phase 3: Context manager (session resume)
  # ─────────────────────────────────────────────────────────────────────────
  context_manager = None
  try:
    context_manager = create_context_manager(args.resume, config)
  except Exception as e:
    log.warning("session_resume_failed", error=str(e))
    print("Warning: Failed to resume session. Starting new session.")

  # Phase 4: Initialize agent
  # ─────────────────────────────────────────────────────────────────────────
  try:
    agent = Agent(
      config=config,
      agent_definition=agent_definition,
      context_manager=context_manager,
      thinking_mode=ThinkingMode.SILENT,  # Don't show thinking in chat
    )

    # Log tool capabilities
    tools = getattr(agent_definition, "tools", [])
    blocked = set(tools) & FORBIDDEN_TOOLS if tools else set()
    if blocked:
      log.warning(
        "tools_restricted",
        requested=list(tools),
        allowed=list(ALLOWED_TOOLS),
        blocked=list(blocked),
        message="Forbidden tools in chat context. Only read-only operations allowed.",
      )

    log.info(
      "agent_initialized",
      name=getattr(agent_definition, "name", "unknown"),
      tools=list(set(tools) & ALLOWED_TOOLS) if tools else [],
    )
  except Exception as e:
    log.error("agent_initialization_failed", error=str(e))
    print(f"Error: Failed to initialize agent: {e}")
    exit(1)

  # Phase 5: Create ChatClient
  # ─────────────────────────────────────────────────────────────────────────
  agent_name = args.name or getattr(agent_definition, "name", "ChatBot")

  client = ChatClient(
    server_url=args.server_url,
    agent=agent,
    session_cache_path=args.session_cache,
    name=agent_name,
    mention_triggers=args.mention_trigger,
  )

  # Phase 6: Authenticate and run
  # ─────────────────────────────────────────────────────────────────────────
  try:
    await client.authenticate(login=args.login, token=args.token)
    print("✓ Authenticated and connected to chat room")

    # Start listening for messages
    await client.start()
    print("✓ Listening for messages... (Press Ctrl+C to exit)")

    # Keep running until interrupted
    await asyncio.Event().wait()

  except KeyboardInterrupt:
    print("\nShutting down...")
  except Exception as e:
    print(f"Error: {e}")
    exit(1)
  finally:
    # Ensure cleanup
    await client.disconnect()

    # End agent session if supported
    if hasattr(agent, "end_session"):
      try:
        agent.end_session(reason="quit")
        log.info("session_ended")
      except Exception as e:
        log.warning("session_end_failed", error=str(e))


def main() -> None:
  """Main entry point for yoker-chat CLI."""
  args = parse_args()
  setup_logging(args.log_file, args.log_format)

  print(f"yoker-chat v{__import__('yoker_chat').__version__}")

  try:
    asyncio.run(_run_client(args))
  except KeyboardInterrupt:
    print("\nShutting down...")
  except Exception as e:
    print(f"Error: {e}")
    exit(1)


if __name__ == "__main__":
  main()
