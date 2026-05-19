"""Yoker Chat Client - Bridges Roomz chat rooms to Yoker agents."""

__version__ = "0.1.0"


def run() -> None:
  """Run the yoker-chat CLI."""
  from yoker_chat.cli import main

  main()


__all__ = ["run", "__version__"]
