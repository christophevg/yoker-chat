# Yoker Chat Client

[![PyPI](https://img.shields.io/pypi/v/yoker-chat.svg)][pypi]
[![Python](https://img.shields.io/pypi/pyversions/yoker-chat.svg)][pypi]
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)][uv]
[![CI](https://img.shields.io/github/actions/workflow/status/christophevg/yoker-chat/test.yml.svg)][ci]
[![Coverage](https://img.shields.io/coveralls/github/christophevg/yoker-chat.svg)][coveralls]
[![License](https://img.shields.io/github/license/christophevg/yoker-chat.svg)][license]
[![Agentic](https://img.shields.io/badge/workflow-agentic-blueviolet?style=flat-square)](https://christophe.vg/about/Agentic-Workflow)

A standalone client that bridges Roomz chat rooms to Yoker agents, enabling AI agents to participate in chat rooms as bot participants.

## Installation

```bash
uv tool install yoker-chat
```

Or with pip:

```bash
pip install yoker-chat
```

## Quick Start

Create two configuration files:

**yoker.toml** - Agent configuration:
```toml
[backend]
provider = "ollama"

[backend.ollama]
model = "llama3.2:latest"

[context]
storage_path = "~/.cache/yoker-chat/sessions"
```

**agents/chat-bot.md** - Agent definition:
```markdown
---
name: ChatBot
description: A helpful assistant for chat rooms
tools: read, search, web_search
---

You are a helpful assistant in a chat room.
```

Run the client:
```bash
# Auto-discovery: place yoker.toml in current directory or ~/.yoker.toml
yoker-chat

# Or specify config explicitly
yoker-chat --config yoker.toml --agent agents/chat-bot.md
```

## Usage

### Interactive Login

```bash
yoker-chat --server-url http://localhost:5000 --agent agents/chat-bot.md

# Prompts for email and token
Enter your email address: user@example.com
✓ Magic link sent to user@example.com

Check your email and paste the token:
> abc123def456...

✓ Authenticated as user@example.com
✓ Connected to chat room
```

# Non-Interactive Mode

```bash
yoker-chat --server-url http://localhost:5000 \
           --agent agents/chat-bot.md \
           --login bot@example.com \
           --token $MAGIC_TOKEN \
           --name "Assistant"
```

Alternatively, use the `YOKER_CHAT_TOKEN` environment variable for better security:

```bash
export YOKER_CHAT_TOKEN=abc123def456
yoker-chat --server-url http://localhost:5000 \
           --agent agents/chat-bot.md \
           --login bot@example.com \
           --name "Assistant"
```

### Session Resumption

```bash
# Resume previous session context
yoker-chat --server-url http://localhost:5000 --agent agents/chat-bot.md --resume

Available session contexts:
  1. 2026-05-18 14:32:15 (42 messages)
  2. 2026-05-17 10:15:22 (18 messages)

Select session to resume (1-2, or 'n' for new): 1
```

## Configuration

### Configuration File

Create `yoker-chat.toml`:

```toml
[roomz]
server_url = "http://localhost:5000"
session_cache = "~/.cache/yoker-chat/session.json"

[agent]
definition = "agents/chat-bot.md"
config = "yoker.toml"
display_name = "Assistant"
mention_triggers = ["@assistant", "@bot"]

[behavior]
respond_to_all = false
max_response_length = 2000
```

### Command-Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--server-url` | Roomz server URL | Required (or env) |
| `--agent` | Path to agent definition file | Required |
| `--config` | Path to Yoker config file | `yoker.toml` |
| `--session-cache` | Session cache path | `~/.cache/yoker-chat/session.json` |
| `--mention-trigger` | Mention triggers | `@bot` |
| `--login` | Email for authentication | Interactive prompt |
| `--token` | Magic link token | Interactive prompt |
| `--name` | Display name in chat | Agent definition name |
| `--resume` | Resume session context | New session |
| `--log-file` | Log file path | stdout |
| `--log-format` | Log format (text/json) | text |

## Development

```bash
# Clone repository
git clone https://github.com/christophevg/yoker-chat.git
cd yoker-chat

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run linters
uv run ruff check src tests

# Type check
uv run mypy src

# Run all checks
make check
```

## Documentation

Full documentation available at [yoker-chat.readthedocs.io](https://yoker-chat.readthedocs.io/)

## License

MIT License - see [LICENSE](LICENSE) for details.

[pypi]: https://pypi.org/project/yoker-chat/
[uv]: https://docs.astral.sh/uv/
[ci]: https://github.com/christophevg/yoker-chat/actions
[coveralls]: https://coveralls.io/github/christophevg/yoker-chat
[license]: https://github.com/christophevg/yoker-chat/blob/main/LICENSE