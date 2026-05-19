# Yoker Chat Client

A standalone client that bridges Roomz chat rooms to Yoker agents.

```{toctree}
:maxdepth: 2

installation
configuration
api
```

## Quick Start

```bash
# Install
uv tool install yoker-chat

# Run
yoker-chat --server-url http://localhost:5000 --agent agents/chat-bot.md
```

## Features

- **Authentication**: Interactive and non-interactive login flows
- **Session Management**: Automatic reconnection with session caching
- **Message Processing**: Filter by mentions, process through Yoker agent
- **Structured Logging**: Configurable output (text or JSON)
- **Context Resumption**: Resume previous conversation contexts