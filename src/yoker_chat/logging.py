"""Logging configuration for yoker-chat."""

import structlog

def redaction_processor(_, __, event_dict: dict) -> dict:
  """Redact sensitive information from log events."""
  sensitive_keys = {"token", "session_cookie", "password"}
  for key in sensitive_keys:
    if key in event_dict:
      event_dict[key] = "[REDACTED]"
  return event_dict

def get_default_processors(log_format: str) -> list[object]:
  """Get default structlog processors based on format."""
  processors = [
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.add_log_level,
    redaction_processor,
  ]

  if log_format == "json":
    processors.append(structlog.processors.JSONRenderer())
  else:
    processors.append(structlog.dev.ConsoleRenderer())

  return processors
