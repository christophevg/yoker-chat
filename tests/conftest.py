"""Pytest configuration for yoker-chat tests."""

from pathlib import Path

import pytest


@pytest.fixture
def temp_session_cache(tmp_path: Path) -> Path:
  """Create a temporary session cache file for testing."""
  cache_dir = tmp_path / ".cache" / "yoker-chat"
  cache_dir.mkdir(parents=True)
  return cache_dir / "session.json"
