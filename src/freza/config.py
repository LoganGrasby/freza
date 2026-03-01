"""Agent system configuration."""

import os
import platform
import secrets
import sys
from pathlib import Path


def default_base_dir() -> Path:
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "freza"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "freza"


MEMORY_TEMPLATE = """\
# Agent Memory — {agent_name}

## Identity
I am "{agent_name}", an autonomous agent. I persist across invocations and maintain this memory.
{description_line}

## Core Knowledge


## Active Projects


## Notes

"""


class Config:
    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(
            base_dir or os.environ.get("AGENT_BASE_DIR", str(default_base_dir()))
        ).resolve()

        self.state_dir = self.base_dir / "state"
        self.registry_file = self.state_dir / "registry.json"
        self.short_term_dir = self.state_dir / "short_term"
        self.channels_dir = self.base_dir / "channels"
        self.channels_meta = self.state_dir / "channels.json"
        self.agents_dir = self.base_dir / "agents"
        self.agents_meta = self.state_dir / "agents.json"
        self.logs_dir = self.state_dir / "logs"
        self.tools_dir = self.base_dir / "tools"
        self.webui_pid_file = self.state_dir / "webui.pid"
        self.webui_log_file = self.state_dir / "webui.log"
        self.webui_token_file = self.state_dir / "webui.token"

        self.heartbeat_interval = int(os.environ.get("AGENT_HEARTBEAT_SEC", "30"))
        self.stale_threshold = int(os.environ.get("AGENT_STALE_SEC", "300"))

        self.model = os.environ.get("AGENT_MODEL", "claude-opus-4-6")
        self.max_turns = int(os.environ.get("AGENT_MAX_TURNS", "100"))
        self.timeout = int(os.environ.get("AGENT_TIMEOUT_SEC", "600"))

    def agent_dir(self, name: str) -> Path:
        return self.agents_dir / name

    def agent_config_file(self, name: str) -> Path:
        return self.agents_dir / name / "agent.json"

    def agent_memory_file(self, name: str) -> Path:
        return self.agents_dir / name / "memory.md"

    def agent_invoke_file(self, name: str) -> Path:
        return self.agents_dir / name / "invoke.py"

    def webui_token(self, generate: bool = False) -> str | None:
        if generate and not self.webui_token_file.exists():
            token = secrets.token_urlsafe(32)
            self.webui_token_file.write_text(token)
            self.webui_token_file.chmod(0o600)
            return token
        if self.webui_token_file.exists():
            return self.webui_token_file.read_text().strip()
        return None

    @property
    def agent_cmd(self) -> str:
        return f'{sys.executable} -m freza --base-dir "{self.base_dir}"'

    @property
    def agent_cmd_argv(self) -> list[str]:
        return [sys.executable, "-m", "freza", "--base-dir", str(self.base_dir)]

    def ensure_dirs(self):
        for d in (
            self.state_dir,
            self.short_term_dir,
            self.channels_dir,
            self.agents_dir,
            self.logs_dir,
            self.tools_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def initialize(self):
        self.ensure_dirs()
        if not self.channels_meta.exists():
            self.channels_meta.write_text("[]")
        if not self.agents_meta.exists():
            self.agents_meta.write_text("[]")

        # Ensure the default agent always exists in initialize-only workspaces.
        from freza.agents import AgentManager
        AgentManager(self).ensure_default_agent()
