# Freza

Autonomous agent system built on the Claude Code SDK. Freza runs persistent agents that maintain long-term memory, respond to messages via channels (web UI, email, or custom integrations), and can be managed from anywhere through a native desktop app.

## Install

```bash
curl -fsSL https://freza.ai/install.sh | sh
```

Or manually:

```bash
pip install .
```

Requires Python 3.10+ and the Claude Code CLI.

## Quick Start

```bash
freza init
```

This creates a workspace, registers the default agent, and starts the web UI daemon at `http://localhost:7888`.

The workspace lives at `~/Library/Application Support/freza/` on macOS or `~/.local/share/freza/` on Linux. Override with `--base-dir`:

```bash
freza init --base-dir /path/to/workspace
```

## Desktop App

A native desktop app (macOS, Windows, Linux) for connecting to local or remote freza instances. Download from [GitHub Releases](https://github.com/LoganGrasby/freza/releases) or build from source:

```bash
cd desktop
npm install
npx tauri build --bundles app
```

The app includes a connection manager for saving and switching between multiple freza servers.

## Remote Access

To expose a freza instance for remote connections:

```bash
freza webui --generate-token    # generate an API token
freza webui --host 0.0.0.0     # start listening on all interfaces
```

Then connect from the desktop app using the server's IP/hostname and the generated token.

## Usage

```bash
# Agents
freza invoke <agent> "<message>"                   # invoke an agent directly
freza register-agent <name> "<desc>"               # register a new agent

# Channels
freza channel <name> "<message>"                   # send a message via a channel
freza channel <name> "<msg>" --thread-id <id>      # continue a conversation
freza register-channel <name> "<desc>"             # register a new channel

# Web UI
freza webui                                        # start in foreground
freza webui --daemon                               # start as background daemon
freza webui --status                               # check daemon status
freza webui --stop                                 # stop the daemon
freza webui --host 0.0.0.0 --port 8080             # custom bind address

# System
freza status                                       # show instances, memory, logs
freza cleanup                                      # prune stale state files
```

## Agents

Each agent has its own directory, memory file, and optional custom invocation logic:

```
agents/
  default/
    agent.json     # name, description, system prompt
    memory.md      # persistent long-term memory
    invoke.py      # optional custom Claude SDK script
  researcher/
    ...
```

Create agents:

```bash
freza register-agent researcher "Research agent" --system-prompt "You are a research specialist."
```

Agents can invoke other agents and create new ones autonomously.

## Channels

Channels are external programs that route messages to agents:

```bash
freza register-channel slack "Slack integration" --default-agent default
freza register-channel email "Email handler" --system-prompt @prompts/email.txt
```

Multi-turn conversations are supported via `--thread-id`.

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `AGENT_BASE_DIR` | platform default | Workspace directory |
| `AGENT_MODEL` | `claude-opus-4-6` | Claude model to use |
| `AGENT_MAX_TURNS` | `100` | Max agentic turns per invocation |
| `AGENT_TIMEOUT_SEC` | `600` | Invocation timeout |
| `AGENT_HEARTBEAT_SEC` | `30` | Heartbeat interval for instance registry |
| `AGENT_STALE_SEC` | `300` | Threshold before an instance is considered stale |
