# Freza

Autonomous agent system built on the Claude Code SDK. Freza runs as a persistent background agent that reflects on a schedule, maintains long-term memory, and responds to messages via channels (gmail, web UI, or custom integrations).

## Requirements

- Python 3.10+
- Claude Code CLI (auto-installed on first run if missing)

## Install

```bash
pip install .
```

## Quick Start

Initialize a workspace (creates data directories and installs a cron job for periodic reflection):

```bash
freza init
```

By default the workspace lives at `~/Library/Application Support/freza/` on macOS or `~/.local/share/freza/` on Linux. Override with `--base-dir`:

```bash
freza init --base-dir /path/to/workspace
```

## Usage

```bash
freza status                          # show instances, memory, recent logs
freza reflect                         # trigger a reflection manually
freza channel <name> "<message>"      # send a message via a channel
freza webui                           # start the web UI (default: localhost:7888)
freza webui --host 0.0.0.0 --port 80  # bind to a different address
freza register-channel <name> "<desc>" # register a new channel
freza cleanup                         # prune stale state files
```

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `AGENT_BASE_DIR` | platform default | Workspace directory |
| `AGENT_MODEL` | `claude-opus-4-6` | Claude model to use |
| `AGENT_MAX_TURNS` | `25` | Max agentic turns per invocation |
| `AGENT_TIMEOUT_SEC` | `600` | Invocation timeout |
| `AGENT_CRON_SCHEDULE` | `*/15 * * * *` | Cron schedule for reflection |
| `AGENT_HEARTBEAT_SEC` | `30` | Heartbeat interval for instance registry |
| `AGENT_STALE_SEC` | `300` | Threshold before an instance is considered stale |
