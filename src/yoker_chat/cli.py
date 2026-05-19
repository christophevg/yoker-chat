"""CLI entry point for yoker-chat."""

import argparse
import logging

import structlog


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
    help="Path to agent definition file",
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
    help="Magic link token for authentication (non-interactive mode)",
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

  if log_format == "json":
    processors: list[object] = [
      structlog.processors.TimeStamper(fmt="iso"),
      structlog.processors.add_log_level,
      structlog.processors.JSONRenderer(),
    ]
  else:
    processors = [
      structlog.processors.TimeStamper(fmt="iso"),
      structlog.processors.add_log_level,
      structlog.dev.ConsoleRenderer(),
    ]

  structlog.configure(
    processors=processors,  # type: ignore[arg-type]
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    cache_logger_on_first_use=True,
  )


def main() -> None:
  """Main entry point for yoker-chat CLI."""
  args = parse_args()
  setup_logging(args.log_file, args.log_format)

  # TODO: Implement client startup
  print(f"yoker-chat v{__import__('yoker_chat').__version__}")
  print(f"Server: {args.server_url}")
  print(f"Agent: {args.agent}")
  print("Not yet implemented - project setup in progress")


if __name__ == "__main__":
  main()
