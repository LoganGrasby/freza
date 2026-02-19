"""Agent system configuration."""

import os
import platform
import sys
from pathlib import Path


def default_base_dir() -> Path:
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "freza"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "freza"


MEMORY_TEMPLATE = """\
# Agent Memory

## Identity
I am an autonomous agent. I persist across invocations and maintain this memory.

## Core Knowledge


## Active Projects


## Registered Channels


## Notes

"""


class Config:
    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(
            base_dir or os.environ.get("AGENT_BASE_DIR", str(default_base_dir()))
        ).resolve()

        self.state_dir = self.base_dir / "state"
        self.memory_file = self.state_dir / "memory.md"
        self.registry_file = self.state_dir / "registry.json"
        self.short_term_dir = self.state_dir / "short_term"
        self.channels_dir = self.base_dir / "channels"
        self.channels_meta = self.state_dir / "channels.json"
        self.logs_dir = self.state_dir / "logs"
        self.tools_dir = self.base_dir / "tools"
        self.webui_pid_file = self.state_dir / "webui.pid"
        self.webui_log_file = self.state_dir / "webui.log"

        self.heartbeat_interval = int(os.environ.get("AGENT_HEARTBEAT_SEC", "30"))
        self.stale_threshold = int(os.environ.get("AGENT_STALE_SEC", "300"))
        self.cron_schedule = os.environ.get("AGENT_CRON_SCHEDULE", "*/15 * * * *")

        self.model = os.environ.get("AGENT_MODEL", "claude-opus-4-6")
        self.max_turns = int(os.environ.get("AGENT_MAX_TURNS", "25"))
        self.timeout = int(os.environ.get("AGENT_TIMEOUT_SEC", "600"))

    @property
    def agent_cmd(self) -> str:
        return f"{sys.executable} -m freza --base-dir {self.base_dir}"

    @property
    def agent_cmd_argv(self) -> list[str]:
        return [sys.executable, "-m", "freza", "--base-dir", str(self.base_dir)]

    def ensure_dirs(self):
        for d in (
            self.state_dir,
            self.short_term_dir,
            self.channels_dir,
            self.logs_dir,
            self.tools_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def ensure_memory(self):
        if not self.memory_file.exists():
            self.memory_file.write_text(MEMORY_TEMPLATE)

    def initialize(self):
        self.ensure_dirs()
        self.ensure_memory()
        if not self.channels_meta.exists():
            self.channels_meta.write_text("[]")
