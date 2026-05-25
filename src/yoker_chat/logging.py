"""Logging configuration for yoker-chat."""

import structlog


def redaction_processor(
  _logger: object, _name: str, event_dict: dict[str, object]
) -> dict[str, object]:
  """
  Redact sensitive information from log events.

  Sensitive keys:
  - Authentication: token, session_cookie, password
  - PII: email, sender, content, response
  """
  sensitive_keys = {
    # Authentication secrets
    "token",
    "session_cookie",
    "password",
    # PII - message content
    "content",
    "content_preview",
    "chunk_preview",
    "message_preview",
    # PII - user identifiers
    "email",
    "sender",
    "user",
    # PII - responses
    "response",
    "preview",
  }
  for key in sensitive_keys:
    if key in event_dict:
      event_dict[key] = "[REDACTED]"
  return event_dict


def component_processor(
  _logger: object, _name: str, event_dict: dict[str, object]
) -> dict[str, object]:
  """Add component name to log events if not present."""
  if "component" not in event_dict:
    event_dict["component"] = "yoker-chat"
  return event_dict


def get_default_processors(log_format: str) -> list[object]:
  """Get default structlog processors based on format."""
  processors = [
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.add_log_level,
    component_processor,
    redaction_processor,
  ]

  if log_format == "json":
    processors.append(structlog.processors.JSONRenderer())
  else:
    processors.append(structlog.dev.ConsoleRenderer())

  return processors
