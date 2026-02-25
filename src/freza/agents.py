"""Agent management -- named agents with their own directories, memory, and prompts."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from freza.config import Config, MEMORY_TEMPLATE

_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


class AgentManager:
    def __init__(self, config: Config):
        self.config = config

    def _read(self) -> list[dict[str, Any]]:
        if not self.config.agents_meta.exists():
            return []
        try:
            return json.loads(self.config.agents_meta.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, data: list[dict[str, Any]]):
        tmp = self.config.agents_meta.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(self.config.agents_meta)

    def list_agents(self) -> list[dict[str, Any]]:
        return self._read()

    def get_agent(self, name: str) -> dict[str, Any] | None:
        for agent in self._read():
            if agent.get("name") == name:
                return agent
        return None

    def get_agent_config(self, name: str) -> dict[str, Any] | None:
        config_file = self.config.agent_config_file(name)
        if not config_file.exists():
            return None
        try:
            return json.loads(config_file.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def register(self, name: str, description: str, **extra):
        if not _NAME_RE.match(name):
            raise ValueError(
                f"Invalid agent name '{name}': must be alphanumeric with hyphens/underscores only, "
                f"starting with an alphanumeric character."
            )

        agents = self._read()
        found = False
        for agent in agents:
            if agent.get("name") == name:
                agent["description"] = description
                agent["updated_at"] = time.time()
                agent.update(extra)
                found = True
                break
        if not found:
            agents.append({
                "name": name,
                "description": description,
                "created_at": time.time(),
                "updated_at": time.time(),
                **extra,
            })
        self._write(agents)

        # Create agent directory and files
        agent_dir = self.config.agent_dir(name)
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Write agent.json config
        config_file = self.config.agent_config_file(name)
        config_data = {"name": name, "description": description, **extra}
        config_file.write_text(json.dumps(config_data, indent=2))

        # Seed memory if it doesn't exist
        memory_file = self.config.agent_memory_file(name)
        if not memory_file.exists():
            desc_line = f"\n{description}" if description else ""
            memory_file.write_text(
                MEMORY_TEMPLATE.format(agent_name=name, description_line=desc_line)
            )

    def unregister(self, name: str):
        agents = self._read()
        agents = [a for a in agents if a.get("name") != name]
        self._write(agents)
