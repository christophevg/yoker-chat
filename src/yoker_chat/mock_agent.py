"""Mock agent for testing the Yoker Chat Client."""

import asyncio
from typing import Any


class MockAgent:
  """
  A simple mock agent that echoes messages back.

  This is used for testing the ChatClient when the Yoker package
  is not yet available.
  """

  def __init__(self, name: str = "MockBot"):
    self.name = name
    self._event_handlers: dict[str, list[Any]] = {}

  def add_event_handler(self, event_type: str, handler: Any) -> None:
    """Register an event handler."""
    if event_type not in self._event_handlers:
      self._event_handlers[event_type] = []
    self._event_handlers[event_type].append(handler)

  async def process(self, message: str) -> str:
    """
    Process a message and emit events.

    This simulates how a Yoker agent would process a message:
    1. Emit ContentChunk events as it "generates" a response
    2. Emit ContentEnd event when done

    Args:
      message: The message to process

    Returns:
      The complete response
    """
    # Simulate some processing delay
    await asyncio.sleep(0.1)

    # Generate a simple echo response
    response = f"[{self.name}] You said: {message}"

    # Emit ContentChunk events
    if "ContentChunk" in self._event_handlers:
      # Split into chunks to simulate streaming
      chunk_size = 20
      for i in range(0, len(response), chunk_size):
        chunk = response[i : i + chunk_size]
        for handler in self._event_handlers["ContentChunk"]:
          if asyncio.iscoroutinefunction(handler):
            await handler(type("Event", (), {"text": chunk}))
          else:
            handler(type("Event", (), {"text": chunk}))
          await asyncio.sleep(0.01)  # Small delay between chunks

    # Emit ContentEnd event
    if "ContentEnd" in self._event_handlers:
      for handler in self._event_handlers["ContentEnd"]:
        if asyncio.iscoroutinefunction(handler):
          await handler(type("Event", (), {}))
        else:
          handler(type("Event", (), {}))

    return response