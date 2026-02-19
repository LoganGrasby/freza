"""Channel management -- external communication triggers."""

from __future__ import annotations

import json
import time
from typing import Any

from freza.config import Config


class ChannelManager:
    def __init__(self, config: Config):
        self.config = config

    def _read(self) -> list[dict[str, Any]]:
        if not self.config.channels_meta.exists():
            return []
        try:
            return json.loads(self.config.channels_meta.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, data: list[dict[str, Any]]):
        tmp = self.config.channels_meta.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(self.config.channels_meta)

    def list_channels(self) -> list[dict[str, Any]]:
        return self._read()

    def get_channel(self, name: str) -> dict[str, Any] | None:
        for ch in self._read():
            if ch.get("name") == name:
                return ch
        return None

    def register(self, name: str, description: str, **extra):
        channels = self._read()
        found = False
        for ch in channels:
            if ch.get("name") == name:
                ch["description"] = description
                ch["updated_at"] = time.time()
                ch.update(extra)
                found = True
                break
        if not found:
            channels.append({
                "name": name,
                "description": description,
                "created_at": time.time(),
                "updated_at": time.time(),
                **extra,
            })
        self._write(channels)
        (self.config.channels_dir / name).mkdir(parents=True, exist_ok=True)

    def unregister(self, name: str):
        channels = self._read()
        channels = [ch for ch in channels if ch.get("name") != name]
        self._write(channels)
