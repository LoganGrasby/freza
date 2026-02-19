"""WebUI daemon lifecycle management -- daemonize, stop, status."""

from __future__ import annotations

import os
import signal
import sys
import time

from freza.config import Config


def is_running(config: Config) -> int | None:
    """Check if the webui daemon is running. Returns PID if alive, else None.

    Cleans up stale PID files.
    """
    pid_file = config.webui_pid_file
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
    except (ValueError, OSError):
        pid_file.unlink(missing_ok=True)
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return None
    except PermissionError:
        # Process exists but we can't signal it -- still alive
        return pid
    return pid


def stop_daemon(config: Config) -> bool:
    """Stop the webui daemon. Returns True if a process was stopped."""
    pid = is_running(config)
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        config.webui_pid_file.unlink(missing_ok=True)
        return False
    # Wait up to 2 seconds for graceful shutdown
    for _ in range(20):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        # Still alive -- force kill
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    config.webui_pid_file.unlink(missing_ok=True)
    return True


def daemonize(config: Config, host: str = "127.0.0.1", port: int = 7888) -> int:
    """Double-fork to start the webui as a background daemon.

    Returns the daemon PID. The caller continues normally.
    """
    # Stop any existing daemon first
    stop_daemon(config)

    pid_file = config.webui_pid_file
    log_file = config.webui_log_file

    # First fork
    pid = os.fork()
    if pid > 0:
        # Parent: wait briefly for grandchild PID file to appear
        for _ in range(30):
            if pid_file.exists():
                try:
                    return int(pid_file.read_text().strip())
                except (ValueError, OSError):
                    pass
            time.sleep(0.1)
        # Fallback: return child PID
        return pid

    # First child: create new session
    os.setsid()

    # Second fork
    pid = os.fork()
    if pid > 0:
        # First child exits immediately
        os._exit(0)

    # Grandchild: this is the daemon
    pid_file.write_text(str(os.getpid()))

    # Redirect stdio to log file
    log_fd = os.open(str(log_file), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(log_fd, sys.stdout.fileno())
    os.dup2(log_fd, sys.stderr.fileno())
    os.close(log_fd)

    # Redirect stdin from /dev/null
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, sys.stdin.fileno())
    os.close(devnull)

    # Run the server (blocks forever in the daemon)
    from freza.webui.server import run as run_webui
    try:
        run_webui(config, host=host, port=port)
    finally:
        pid_file.unlink(missing_ok=True)
    os._exit(0)
