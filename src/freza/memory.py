"""Long-term and short-term memory management with file locking."""

from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from freza.config import Config


@contextmanager
def _flock(path: Path, exclusive: bool = True):
    lock_path = path.parent / (path.name + ".lock")
    fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY)
    try:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        fcntl.flock(fd, mode)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _atomic_write(path: Path, content: str):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    tmp.rename(path)


class MemoryManager:
    def __init__(self, config: Config):
        self.config = config

    def read(self) -> str:
        with _flock(self.config.memory_file, exclusive=False):
            if self.config.memory_file.exists():
                return self.config.memory_file.read_text()
            return ""

    def write(self, content: str):
        with _flock(self.config.memory_file, exclusive=True):
            _atomic_write(self.config.memory_file, content)

    def append(self, content: str):
        with _flock(self.config.memory_file, exclusive=True):
            existing = ""
            if self.config.memory_file.exists():
                existing = self.config.memory_file.read_text()
            _atomic_write(self.config.memory_file, existing + "\n" + content + "\n")

    def _short_term_path(self, instance_id: str) -> Path:
        return self.config.short_term_dir / f"{instance_id}.json"

    def read_short_term(self, instance_id: str) -> dict[str, Any] | None:
        p = self._short_term_path(instance_id)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def write_short_term(self, instance_id: str, data: dict[str, Any]):
        _atomic_write(self._short_term_path(instance_id), json.dumps(data, indent=2))

    def update_short_term(self, instance_id: str, **fields):
        existing = self.read_short_term(instance_id) or {}
        existing.update(fields)
        existing["updated_at"] = time.time()
        self.write_short_term(instance_id, existing)

    def remove_short_term(self, instance_id: str):
        self._short_term_path(instance_id).unlink(missing_ok=True)

    def get_all_short_term(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        if not self.config.short_term_dir.exists():
            return result
        for f in self.config.short_term_dir.glob("*.json"):
            data = self.read_short_term(f.stem)
            if data:
                result[f.stem] = data
        return result
