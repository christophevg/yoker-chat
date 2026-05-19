# Configuration

## Configuration File

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
show_thinking = false
show_tool_calls = false

[rate_limiting]
min_interval_ms = 1000
max_per_minute = 10
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ROOMZ_SERVER_URL` | Roomz server URL (alternative to --server-url) |

## Command-Line Arguments

See `yoker-chat --help` for all options.