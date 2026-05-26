"""CLI entry point for yoker-chat."""

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Any

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

log = structlog.get_logger().bind(component="cli")


def parse_args() -> argparse.Namespace:
  """Parse command-line arguments."""
  parser = argparse.ArgumentParser(
    prog="yoker-chat",
    description="Chat client that bridges Roomz chat rooms to Yoker agents",
  )

  parser.add_argument(
    "--server-url",
    help="Roomz server URL (auto-discovered from ROOMZ_SERVER_URL env, ~/.roomz.toml, ./roomz.toml)",
  )

  parser.add_argument(
    "--agent",
    help="Path to agent definition file (auto-discovered from yoker.toml [agents].definition)",
  )

  parser.add_argument(
    "--config",
    help="Path to Yoker config file (auto-discovered from YOKER_* env vars, ./yoker.toml, ~/.yoker.toml)",
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


def load_yoker_agent_definition(agent_path: Path | None, config: Any = None) -> Any:
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
  elif config and hasattr(config, "agents") and hasattr(config.agents, "definition"):
    config_definition = config.agents.definition
    # Only use config definition if it's non-empty
    if config_definition and config_definition.strip():
      config_path = Path(config_definition).expanduser()
      path_to_use = validate_agent_path(config_path)
      log.info("agent_path_from_config", path=str(path_to_use))
    else:
      raise FileNotFoundError(
        "No agent definition provided. Use --agent or configure [agents].definition in yoker.toml"
      )
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


def create_context_manager(
  resume: bool,
  config: Any,
) -> Any:
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
  from yoker import Agent, ConfigurationError, ThinkingMode, load_config

  # Phase 1: Load configuration
  # ─────────────────────────────────────────────────────────────────────────
  try:
    if args.config:
      # Explicit config path provided - validate and use it
      config_path = validate_config_path(Path(args.config))
      log.info("loading_config_from_path", path=str(config_path))
      config = load_config(config_path)
      log.info("config_loaded", path=str(config_path))
    else:
      # Use auto-discovery from yoker library
      log.info("auto_discovering_config")
      from yoker import Config

      config = Config.discover()
      log.info("config_loaded", source="discovery")
  except FileNotFoundError as e:
    print(f"Error: Configuration file not found: {e}")
    if args.config:
      print(f"Check if {args.config} exists")
    else:
      print("Use --config path or set YOKER_* environment variables")
    exit(1)
  except ConfigurationError as e:
    print(f"Error: Invalid configuration: {e}")
    if args.config:
      print(f"Check {args.config} for errors")
    else:
      print("Check configuration for errors")
    exit(1)

  # Phase 2: Load agent definition
  # ─────────────────────────────────────────────────────────────────────────
  try:
    agent_path = Path(args.agent) if args.agent else None
    agent_definition = load_yoker_agent_definition(agent_path, config)
  except FileNotFoundError as e:
    print(f"Error: Agent definition not found: {e}")
    if args.agent:
      print(f"Check if {args.agent} exists")
    else:
      print("Use --agent path or configure [agents].definition in yoker.toml")
    exit(1)
  except Exception as e:
    print(f"Error: Invalid agent definition: {e}")
    if args.agent:
      print(f"Check {args.agent} for required fields (name, description, tools)")
    else:
      print("Check agent definition for required fields (name, description, tools)")
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

  # Expand ~ in session cache path
  session_cache_path = str(Path(args.session_cache).expanduser())

  client = ChatClient(
    server_url=args.server_url,
    agent=agent,
    session_cache_path=session_cache_path,
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
        await agent.end_session(reason="quit")
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
