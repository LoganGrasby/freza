"""Freza web UI -- stdlib HTTP server with streaming chat and diagnostics."""

from __future__ import annotations

import hmac
import json
import mimetypes
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import urlparse, parse_qs, unquote

from freza.agents import DEFAULT_AGENT_NAME, is_valid_agent_name
from freza.config import Config

STATIC_DIR = Path(__file__).resolve().parent
DIST_DIR = STATIC_DIR / "dist"

_FRONTEND_BUILD_MISSING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>freza web ui</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #0a0a0b;
      color: #f0f0f2;
      font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .card {
      max-width: 680px;
      padding: 24px;
      border: 1px solid #2a2a32;
      border-radius: 12px;
      background: #111113;
    }
    code {
      background: #1a1a1e;
      border-radius: 6px;
      padding: 2px 6px;
    }
  </style>
</head>
<body>
  <div class="card">
    <h2>Frontend build not found</h2>
    <p>Build the Vue UI before using the web interface:</p>
    <p><code>cd webui/frontend && npm install && npm run build</code></p>
  </div>
</body>
</html>
"""

_config: Config | None = None
_auth_required: bool = False
_auth_token: str | None = None


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


def _list_threads():
    cfg = _cfg()
    if not cfg.logs_dir.exists():
        return []
    threads = {}
    for f in cfg.logs_dir.glob("*.log"):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        tid = data.get("thread_id") or data.get("instance_id", f.stem)
        trigger = (data.get("trigger_message") or "")[:200]
        ts = data.get("timestamp", 0)
        if tid not in threads:
            threads[tid] = {
                "thread_id": tid,
                "title": trigger or "(no message)",
                "agent": data.get("agent_name", "default"),
                "channel": data.get("channel_name", ""),
                "mode": data.get("mode", ""),
                "last_timestamp": ts,
                "message_count": 0,
            }
        threads[tid]["message_count"] += 1
        if ts > threads[tid]["last_timestamp"]:
            threads[tid]["last_timestamp"] = ts
    return sorted(threads.values(), key=lambda t: t["last_timestamp"], reverse=True)


def _get_thread(thread_id: str):
    cfg = _cfg()
    entries = []
    for f in cfg.logs_dir.glob("*.log"):
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        tid = data.get("thread_id") or data.get("instance_id", f.stem)
        if tid == thread_id:
            entries.append({
                "trigger_message": data.get("trigger_message", ""),
                "response": data.get("response", ""),
                "timestamp": data.get("timestamp", 0),
                "agent": data.get("agent_name", "default"),
                "channel": data.get("channel_name", ""),
                "cost_usd": data.get("cost_usd", 0),
                "duration_seconds": data.get("duration_seconds", 0),
                "turns": data.get("turns", 0),
                "tools_used": data.get("tools_used", []),
            })
    entries.sort(key=lambda e: e["timestamp"])
    return entries


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


_LOG_LINE_RE = re.compile(r"^\[[\da-f]+\] ")
_EVENT_PREFIX = "\x1e"


class AgentProcess:

    def __init__(self, message: str, thread_id: str | None = None, agent_name: str = "default"):
        self.message = message
        self.thread_id = thread_id
        self.agent_name = agent_name
        self.process: subprocess.Popen | None = None
        self.output_chunks: list[dict] = []
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
                    if _LOG_LINE_RE.match(line):
                        continue
                    if line.startswith(_EVENT_PREFIX):
                        try:
                            event = json.loads(line[1:])
                            event["kind"] = "event"
                            self.output_chunks.append(event)
                        except json.JSONDecodeError:
                            self.output_chunks.append({"kind": "text", "text": line})
                    else:
                        self.output_chunks.append({"kind": "text", "text": line})
            except Exception:
                pass

        def _stderr_reader():
            try:
                while True:
                    line = self.process.stderr.readline()
                    if not line:
                        break
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

    def get_new_chunks(self, from_idx=0):
        return self.output_chunks[from_idx:], len(self.output_chunks)


_active_procs: dict[str, AgentProcess] = {}
_proc_lock = Lock()
_proc_counter = 0


class WebUIHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _check_auth(self) -> bool:
        if not _auth_required or not _auth_token:
            return True
        token = None
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        if not token:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            token = params.get("token", [None])[0]
        if token and hmac.compare_digest(token, _auth_token):
            return True
        self._json_response({"error": "unauthorized"}, 401)
        return False

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json_response(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self._bytes_response(body, "application/json", status=status)

    def _html_response(self, html: str):
        self._bytes_response(html.encode("utf-8"), "text/html; charset=utf-8")

    def _bytes_response(self, body: bytes, content_type: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self._cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_dist_file(self, rel_path: str) -> bool:
        try:
            dist_root = DIST_DIR.resolve()
            target = (DIST_DIR / rel_path).resolve()
            target.relative_to(dist_root)
        except Exception:
            return False

        if not target.exists() or not target.is_file():
            return False

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._bytes_response(target.read_bytes(), content_type)
        return True

    def _serve_frontend(self, path: str):
        index_path = DIST_DIR / "index.html"
        if not index_path.exists():
            self._html_response(_FRONTEND_BUILD_MISSING_HTML)
            return

        if path == "/" or path == "":
            self._html_response(index_path.read_text(encoding="utf-8"))
            return

        rel_path = unquote(path.lstrip("/"))
        if rel_path and self._serve_dist_file(rel_path):
            return

        # SPA fallback for client-side routes like /logs or /settings.
        if "." not in Path(rel_path).name:
            self._html_response(index_path.read_text(encoding="utf-8"))
            return

        self._json_response({"error": "not found"}, 404)

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

        if not path.startswith("/api/"):
            self._serve_frontend(path)
            return

        if not self._check_auth():
            return

        if path == "/api/ping":
            self._json_response({"status": "ok"})
        elif path == "/api/stats":
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
        elif path == "/api/threads":
            self._json_response(_list_threads())
        elif path.startswith("/api/threads/"):
            tid = path.split("/api/threads/")[1]
            entries = _get_thread(tid)
            self._json_response(entries)
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
                    chunks, new_idx = proc.get_new_chunks(idx)
                    if chunks:
                        for chunk in chunks:
                            if chunk["kind"] == "text":
                                payload = {"text": chunk["text"]}
                            else:
                                payload = {k: v for k, v in chunk.items() if k != "kind"}
                            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
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

        if not self._check_auth():
            return

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


def run(config: Config, host: str = "127.0.0.1", port: int = 7888, token: str | None = None):
    global _config, _auth_required, _auth_token
    _config = config
    _auth_token = token
    _auth_required = bool(token) and host != "127.0.0.1"

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
