"""Freza web UI -- stdlib HTTP server with streaming chat and diagnostics."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import urlparse, parse_qs

from freza.agents import DEFAULT_AGENT_NAME, is_valid_agent_name
from freza.config import Config

STATIC_DIR = Path(__file__).resolve().parent

_config: Config | None = None


def _cfg() -> Config:
    assert _config is not None
    return _config


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _list_logs(limit=50, offset=0):
    cfg = _cfg()
    files = sorted(cfg.logs_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    results = []
    for f in files[offset:offset + limit]:
        try:
            data = json.loads(f.read_text())
            results.append({
                "id": data.get("instance_id", f.stem),
                "mode": data.get("mode"),
                "agent": data.get("agent_name"),
                "channel": data.get("channel_name"),
                "trigger": (data.get("trigger_message") or "")[:200],
                "response": (data.get("response") or "")[:300],
                "duration": data.get("duration_seconds"),
                "cost": data.get("cost_usd"),
                "tools": data.get("tools_used", []),
                "turns": data.get("turns"),
                "timestamp": data.get("timestamp"),
                "file": f.name,
            })
        except Exception:
            continue
    return results


def _get_log_detail(filename: str):
    path = _cfg().logs_dir / filename
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _get_instances():
    data = _read_json(_cfg().registry_file)
    if isinstance(data, list):
        return data
    return []


def _get_short_term():
    results = []
    for f in _cfg().short_term_dir.glob("*.json"):
        try:
            results.append(json.loads(f.read_text()))
        except Exception:
            continue
    return results


def _get_memory(agent_name: str = "default"):
    try:
        mem_file = _cfg().agent_memory_file(agent_name)
        if mem_file.exists():
            return mem_file.read_text()
        return ""
    except Exception:
        return ""


def _get_channels():
    data = _read_json(_cfg().channels_meta)
    if isinstance(data, list):
        return data
    return []


def _get_agents():
    data = _read_json(_cfg().agents_meta)
    if isinstance(data, list):
        return data
    return []


def _parse_agent_name(raw: str | None) -> str:
    name = raw if isinstance(raw, str) else DEFAULT_AGENT_NAME
    name = name.strip() or DEFAULT_AGENT_NAME
    if not is_valid_agent_name(name):
        raise ValueError(
            f"Invalid agent name '{name}': must be alphanumeric with hyphens/underscores only, "
            "starting with an alphanumeric character."
        )
    return name


def _is_registered_agent(name: str) -> bool:
    return any(a.get("name") == name for a in _get_agents())


def _get_system_stats():
    cfg = _cfg()
    files = list(cfg.logs_dir.glob("*.log"))
    total_runs = len(files)
    total_cost = 0.0
    total_duration = 0.0
    channel_counts: dict[str, int] = {}

    for f in sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)[:200]:
        try:
            data = json.loads(f.read_text())
            total_cost += data.get("cost_usd") or 0.0
            total_duration += data.get("duration_seconds") or 0.0
            ch = data.get("channel_name") or "unknown"
            channel_counts[ch] = channel_counts.get(ch, 0) + 1
        except Exception:
            continue

    return {
        "total_runs": total_runs,
        "total_cost_usd": round(total_cost, 4),
        "total_duration_s": round(total_duration, 1),
        "channel_counts": channel_counts,
    }


class AgentProcess:

    def __init__(self, message: str, thread_id: str | None = None, agent_name: str = "default"):
        self.message = message
        self.thread_id = thread_id
        self.agent_name = agent_name
        self.process: subprocess.Popen | None = None
        self.output_chunks: list[str] = []
        self.done = False

    def start(self):
        cfg = _cfg()
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)

        cmd = cfg.agent_cmd_argv + ["channel", "webui", self.message, "--agent", self.agent_name]
        if self.thread_id:
            cmd += ["--thread-id", self.thread_id]
        self.process = subprocess.Popen(
            cmd,
            cwd=str(cfg.base_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

        def _stdout_reader():
            try:
                while True:
                    line = self.process.stdout.readline()
                    if not line:
                        break
                    self.output_chunks.append(line)
            except Exception:
                pass

        def _stderr_reader():
            try:
                while True:
                    line = self.process.stderr.readline()
                    if not line:
                        break
                    self.output_chunks.append(f"\n[stderr] {line}")
            except Exception:
                pass

        def _waiter():
            t_out = Thread(target=_stdout_reader, daemon=True)
            t_err = Thread(target=_stderr_reader, daemon=True)
            t_out.start()
            t_err.start()
            self.process.wait()
            t_out.join(timeout=2)
            t_err.join(timeout=2)
            self.done = True

        Thread(target=_waiter, daemon=True).start()

    def get_new_output(self, from_idx=0):
        return "".join(self.output_chunks[from_idx:]), len(self.output_chunks)


_active_procs: dict[str, AgentProcess] = {}
_proc_lock = Lock()
_proc_counter = 0


class WebUIHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors_headers()
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query)

        if path == "/" or path == "":
            html_path = STATIC_DIR / "index.html"
            if html_path.exists():
                self._html_response(html_path.read_text())
            else:
                self._json_response({"error": "index.html not found"}, 404)
            return

        if path == "/api/stats":
            self._json_response(_get_system_stats())
        elif path == "/api/logs":
            limit = int(params.get("limit", [50])[0])
            offset = int(params.get("offset", [0])[0])
            self._json_response(_list_logs(limit, offset))
        elif path.startswith("/api/logs/"):
            filename = path.split("/api/logs/")[1]
            detail = _get_log_detail(filename)
            if detail:
                self._json_response(detail)
            else:
                self._json_response({"error": "not found"}, 404)
        elif path == "/api/instances":
            self._json_response(_get_instances())
        elif path == "/api/short-term":
            self._json_response(_get_short_term())
        elif path == "/api/memory":
            try:
                agent_name = _parse_agent_name(params.get("agent", [DEFAULT_AGENT_NAME])[0])
            except ValueError as e:
                self._json_response({"error": str(e)}, 400)
                return
            if not _is_registered_agent(agent_name):
                self._json_response({"error": f"unknown agent '{agent_name}'"}, 404)
                return
            self._json_response({"content": _get_memory(agent_name), "agent": agent_name})
        elif path == "/api/channels":
            self._json_response(_get_channels())
        elif path == "/api/agents":
            self._json_response(_get_agents())

        elif path.startswith("/api/stream/"):
            proc_id = path.split("/api/stream/")[1]
            proc = _active_procs.get(proc_id)
            if not proc:
                self._json_response({"error": "process not found"}, 404)
                return

            self._sse_headers()
            idx = 0
            try:
                while True:
                    text, new_idx = proc.get_new_output(idx)
                    if text:
                        for line in f"data: {json.dumps({'text': text})}\n\n".encode().splitlines(True):
                            self.wfile.write(line)
                        self.wfile.flush()
                        idx = new_idx
                    elif proc.done:
                        self.wfile.write(f"data: {json.dumps({'done': True})}\n\n".encode())
                        self.wfile.flush()
                        _active_procs.pop(proc_id, None)
                        break
                    else:
                        time.sleep(0.15)
            except (BrokenPipeError, ConnectionResetError):
                pass

        else:
            self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/chat":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except Exception:
                self._json_response({"error": "invalid json"}, 400)
                return

            message = data.get("message", "").strip()
            if not message:
                self._json_response({"error": "empty message"}, 400)
                return

            thread_id = data.get("thread_id") or uuid.uuid4().hex
            try:
                agent_name = _parse_agent_name(data.get("agent", DEFAULT_AGENT_NAME))
            except ValueError as e:
                self._json_response({"error": str(e)}, 400)
                return
            if not _is_registered_agent(agent_name):
                self._json_response({"error": f"unknown agent '{agent_name}'"}, 404)
                return

            global _proc_counter
            with _proc_lock:
                _proc_counter += 1
                proc_id = f"proc_{_proc_counter}_{int(time.time())}"

            proc = AgentProcess(message, thread_id=thread_id, agent_name=agent_name)
            try:
                proc.start()
            except FileNotFoundError as e:
                self._json_response(
                    {"error": f"Failed to start agent: {e}. Is freza installed and on PATH?"},
                    500,
                )
                return
            _active_procs[proc_id] = proc

            self._json_response({"proc_id": proc_id, "thread_id": thread_id, "agent": agent_name, "status": "started"})

        else:
            self._json_response({"error": "not found"}, 404)


class ReusableHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def run(config: Config, host: str = "127.0.0.1", port: int = 7888):
    global _config
    _config = config

    server = ReusableHTTPServer((host, port), WebUIHandler)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [PID {os.getpid()}] Freza Web UI running at http://{host}:{port}")
    print(f"  Base dir: {config.base_dir}")

    def _shutdown(sig, frame):
        print("\nShutting down...")
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
