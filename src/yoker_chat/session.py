"""Session persistence for yoker-chat."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

class SessionCache:
  """Manages session persistence for yoker-chat."""

  def __init__(self, cache_path: str | Path):
    self.cache_path = Path(cache_path).expanduser()
    self._ensure_cache_dir()

  def _ensure_cache_dir(self) -> None:
    """Create the cache directory if it doesn't exist."""
    self.cache_path.parent.mkdir(parents=True, exist_ok=True)

  def save(self, session_cookie: str, server_url: str, email: str) -> None:
    """Save session data to the cache file with secure permissions."""
    data = {
      "version": "1.0",
      "session": {
        "cookie": session_cookie,
        "server_url": server_url,
        "email": email,
        "created_at": datetime.now().isoformat(),
      },
      "metadata": {
        "last_used": datetime.now().isoformat(),
      }
    }

    content = json.dumps(data, indent=2).encode("utf-8")

    # Use os.open to ensure 0600 permissions from creation
    # O_WRONLY: open for writing
    # O_CREAT: create if it doesn't exist
    # O_TRUNC: truncate if it exists
    fd = os.open(
      str(self.cache_path),
      os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
      0o600
    )

    try:
      with os.fdopen(fd, "wb") as f:
        f.write(content)
    except Exception:
      os.close(fd)
      raise

  def load(self) -> dict[str, Any] | None:
    """Load session data from the cache file."""
    if not self.cache_path.exists():
      return None

    try:
      with open(self.cache_path, "r") as f:
        return json.load(f)
    except (json.JSONDecodeError, IOError):
      return None

  def clear(self) -> None:
    """Delete the session cache file."""
    if self.cache_path.exists():
      self.cache_path.unlink()
