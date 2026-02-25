"""Instance registry -- tracks all running agent instances."""

from __future__ import annotations

import fcntl
import json
import os
import time
import threading
import uuid
from dataclasses import dataclass, asdict
from typing import Any

from freza.config import Config


@dataclass
class InstanceInfo:
    instance_id: str
    pid: int
    mode: str
    channel_name: str | None
    trigger_message: str | None
    started_at: float
    last_heartbeat: float
    status: str = "running"
    agent_name: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> InstanceInfo:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _lock_path(config: Config) -> str:
    return str(config.registry_file) + ".lock"


def _locked_update(config: Config, fn):
    lock = _lock_path(config)
    fd = os.open(lock, os.O_CREAT | os.O_WRONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        entries: list[dict] = []
        if config.registry_file.exists():
            try:
                entries = json.loads(config.registry_file.read_text())
            except (json.JSONDecodeError, OSError):
                entries = []
        entries = fn(entries)
        tmp = config.registry_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries, indent=2))
        tmp.rename(config.registry_file)
        return entries
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


class InstanceRegistry:
    def __init__(self, config: Config):
        self.config = config
        self._heartbeat_stop: threading.Event | None = None
        self._heartbeat_thread: threading.Thread | None = None

    def register(
        self,
        mode: str,
        channel_name: str | None = None,
        trigger_message: str | None = None,
        agent_name: str = "default",
    ) -> InstanceInfo:
        now = time.time()
        info = InstanceInfo(
            instance_id=uuid.uuid4().hex[:16],
            pid=os.getpid(),
            mode=mode,
            channel_name=channel_name,
            trigger_message=trigger_message[:500] if trigger_message else None,
            started_at=now,
            last_heartbeat=now,
            agent_name=agent_name,
        )

        def _add(entries):
            entries.append(info.to_dict())
            return entries

        _locked_update(self.config, _add)
        return info

    def deregister(self, instance_id: str, status: str = "finished"):
        if status == "finished":
            _locked_update(self.config, lambda es: [
                e for e in es if e.get("instance_id") != instance_id
            ])
        else:
            def _mark_failed(entries):
                return [
                    {**e, "status": status}
                    if e.get("instance_id") == instance_id
                    else e
                    for e in entries
                ]
            _locked_update(self.config, _mark_failed)

    def heartbeat(self, instance_id: str):
        now = time.time()

        def _update(entries):
            for e in entries:
                if e.get("instance_id") == instance_id:
                    e["last_heartbeat"] = now
            return entries

        _locked_update(self.config, _update)

    def get_active(self) -> list[InstanceInfo]:
        now = time.time()
        threshold = self.config.stale_threshold

        def _prune(entries):
            return [
                e for e in entries
                if now - e.get("last_heartbeat", 0) < threshold
            ]

        entries = _locked_update(self.config, _prune)
        return [InstanceInfo.from_dict(e) for e in entries]

    def start_heartbeat(self, instance_id: str):
        self._heartbeat_stop = threading.Event()
        interval = self.config.heartbeat_interval

        def _loop():
            while not self._heartbeat_stop.wait(interval):
                try:
                    self.heartbeat(instance_id)
                except Exception:
                    pass

        self._heartbeat_thread = threading.Thread(target=_loop, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self):
        if self._heartbeat_stop:
            self._heartbeat_stop.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
