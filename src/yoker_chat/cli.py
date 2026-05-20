"""CLI entry point for yoker-chat."""

import argparse
import asyncio
import logging

import structlog

from yoker_chat.client import ChatClient
from yoker_chat.logging import get_default_processors


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


async def _run_client(args: argparse.Namespace) -> None:
  """Initialize and run the chat client."""
  # In a real implementation, we would load the agent here.
  # For now, we use a mock agent or just pass None.
  agent = None

  client = ChatClient(
    server_url=args.server_url,
    agent=agent,
    session_cache_path=args.session_cache,
    name=args.name,
  )

  try:
    await client.authenticate(login=args.login, token=args.token)
    print("✓ Authenticated and connected to chat room")

    # Keep the client running (in a real app, this would be the event loop for messages)
    # For Task 1.2, we just need to verify authentication.
    # await client.start() # This would be implemented in Task 1.3
  finally:
    await client.disconnect()


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
