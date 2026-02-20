"""Autonomous agent -- main entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Prevent "nested Claude Code session" detection when spawned
# from within a Claude Code context (e.g. WebUI channel).
os.environ.pop("CLAUDECODE", None)

from freza.config import Config
from freza.memory import MemoryManager
from freza.registry import InstanceRegistry, InstanceInfo
from freza.channels import ChannelManager
from freza.llm import invoke_claude, LLMError


def _system_prompt(config: Config, instance: InstanceInfo) -> str:
    return f"""\
You are an autonomous agent running in a persistent environment.
You may be one of several simultaneous instances of yourself.
All instances share a single long-term memory file.

## Environment
- Working directory: {config.base_dir}
- Long-term memory: {config.memory_file}
- Short-term state:  {config.short_term_dir}/{instance.instance_id}.json
- Channels dir:      {config.channels_dir}/
- Your instance ID:  {instance.instance_id}

## Memory Rules
- Edit {config.memory_file} directly for persistent knowledge.
  Prefer the locked helper for appends:
    {config.tools_dir}/update_memory.sh "text to append"
- Keep memory concise: identity, core knowledge, active projects, channels.
- Update your short-term state file's "current_task" field so other
  instances know what you are doing.

## Channel System
You can build external integrations that trigger new agent invocations.
1. Create a program in {config.channels_dir}/<name>/
2. That program should call back:
     {config.agent_cmd} channel <name> "<message>"
3. Register the channel:
     {config.agent_cmd} register-channel <name> "<description>"
4. To start/manage it as a background service, use systemd, supervisord,
   screen, or any method you prefer.
5. Document it in your long-term memory.

## Behaviour
- Check what other instances are doing before starting work.
- Do not duplicate work another instance is already handling.
- During cron reflection you are free to do nothing if there is nothing useful.
- During reflection you should be proactive, especially when it comes to fixing known issues.
- You have full bash, file-editing, and network access.
"""


def _user_prompt(
    config: Config,
    memory: MemoryManager,
    registry: InstanceRegistry,
    channels: ChannelManager,
    instance: InstanceInfo,
    mode: str,
    channel_name: str | None,
    trigger_message: str | None,
) -> str:
    parts: list[str] = []

    mem_content = memory.read()
    parts.append("## Your Long-Term Memory\n")
    if mem_content.strip():
        parts.append(mem_content)
    else:
        parts.append(
            "(Memory is empty -- this may be your first run. "
            "Consider initialising it.)"
        )
    parts.append("")

    instances = registry.get_active()
    others = [i for i in instances if i.instance_id != instance.instance_id]

    parts.append("## Active Instances\n")
    parts.append(f"**You**: `{instance.instance_id}` (mode={instance.mode}, "
                 f"pid={instance.pid})")
    if others:
        parts.append(f"\n{len(others)} other instance(s):\n")
        for o in others:
            st = memory.read_short_term(o.instance_id)
            task = st.get("current_task", "unknown") if st else "unknown"
            age = time.time() - o.started_at
            parts.append(
                f"- `{o.instance_id}` mode={o.mode} "
                f"task=\"{task}\" uptime={age:.0f}s"
            )
    else:
        parts.append("\nYou are the only running instance.")
    parts.append("")

    chans = channels.list_channels()
    parts.append("## Registered Channels\n")
    if chans:
        for ch in chans:
            parts.append(f"- **{ch['name']}**: {ch.get('description', '')}")
    else:
        parts.append("(none)")
    parts.append("")

    parts.append("## Trigger\n")
    if mode == "reflect":
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        parts.append(
            f"**Cron reflection** at {now}.\n"
            "Review your memory, check ongoing projects, and take action "
            "only if something is genuinely useful. It is perfectly fine "
            "to do nothing."
        )
    elif mode == "channel":
        parts.append(f"**Incoming message** on channel `{channel_name}`:\n")
        parts.append(f"```\n{trigger_message}\n```\n")
        parts.append("Respond to this message and take any appropriate actions.")
    parts.append("")

    return "\n".join(parts)


def _ensure_claude_cli():
    if shutil.which("claude"):
        return
    known_paths = [Path.home() / ".local" / "bin" / "claude"]
    if platform.system() != "Windows":
        known_paths.append(Path("/usr/local/bin/claude"))
    for p in known_paths:
        if p.exists():
            os.environ["PATH"] = f"{p.parent}:{os.environ.get('PATH', '')}"
            return
    print("Claude Code CLI not found. Installing...")
    try:
        subprocess.run(
            ["bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"],
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(
            "Failed to install Claude Code CLI. "
            "Install it manually: https://docs.anthropic.com/en/docs/claude-code"
        ) from e
    # Add the newly installed binary to PATH
    for p in known_paths:
        if p.exists():
            os.environ["PATH"] = f"{p.parent}:{os.environ.get('PATH', '')}"
            return


def _atomic_write_log(path: Path, data: dict):
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.rename(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _find_session_for_thread(config: Config, thread_id: str) -> str | None:
    """Find the session_id from the most recent log for a given thread."""
    log_files = sorted(
        config.logs_dir.glob("*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for lf in log_files:
        try:
            data = json.loads(lf.read_text())
            if data.get("thread_id") == thread_id and data.get("session_id"):
                return data["session_id"]
        except Exception:
            continue
    return None


async def do_invoke(
    config: Config,
    mode: str,
    channel_name: str | None = None,
    trigger_message: str | None = None,
    thread_id: str | None = None,
):
    _ensure_claude_cli()
    memory = MemoryManager(config)
    registry = InstanceRegistry(config)
    channels = ChannelManager(config)

    instance = registry.register(
        mode=mode,
        channel_name=channel_name,
        trigger_message=trigger_message,
    )
    print(f"[{instance.instance_id}] registered (mode={mode}, pid={instance.pid})")

    memory.write_short_term(instance.instance_id, {
        "instance_id": instance.instance_id,
        "mode": mode,
        "channel_name": channel_name,
        "started_at": instance.started_at,
        "current_task": "initializing",
        "status": "running",
    })

    registry.start_heartbeat(instance.instance_id)

    log_file = config.logs_dir / f"{instance.instance_id}.log"
    final_status = "finished"

    try:
        system = _system_prompt(config, instance)
        user = _user_prompt(
            config, memory, registry, channels,
            instance, mode, channel_name, trigger_message,
        )

        memory.update_short_term(instance.instance_id, current_task="thinking")

        # Look up prior session for multi-turn threads
        resume_session = None
        if thread_id:
            resume_session = _find_session_for_thread(config, thread_id)
            if resume_session:
                print(f"[{instance.instance_id}] resuming thread {thread_id} "
                      f"(session={resume_session[:12]}...)")

        print(f"[{instance.instance_id}] invoking claude (model={config.model}, "
              f"max_turns={config.max_turns})...")

        stream_text = None
        if mode == "channel":
            def stream_text(text: str) -> None:
                print(text, end="", flush=True)

        result = await invoke_claude(
            prompt=user,
            system_prompt=system,
            cwd=str(config.base_dir),
            model=config.model,
            max_turns=config.max_turns,
            on_text=stream_text,
            resume=resume_session,
        )

        if stream_text:
            print()

        log_entry = {
            "instance_id": instance.instance_id,
            "mode": mode,
            "channel_name": channel_name,
            "trigger_message": (trigger_message or "")[:500],
            "response": result.response[:5000],
            "duration_seconds": result.duration_seconds,
            "cost_usd": result.cost_usd,
            "tools_used": result.tools_used,
            "turns": result.turns,
            "timestamp": time.time(),
            "session_id": result.session_id,
            "thread_id": thread_id,
            "conversation": result.conversation,
        }
        _atomic_write_log(log_file, log_entry)

        memory.update_short_term(
            instance.instance_id,
            current_task="complete",
            status="finished",
            response_summary=result.response[:1000],
            duration_seconds=result.duration_seconds,
            cost_usd=result.cost_usd,
        )

        print(f"[{instance.instance_id}] done "
              f"({result.duration_seconds:.1f}s, ${result.cost_usd:.4f}, "
              f"{result.turns} turns, tools: {result.tools_used})")

        if mode != "channel":
            for line in result.response.splitlines()[:10]:
                print(f"  {line}")
            if len(result.response.splitlines()) > 10:
                print(f"  ... ({len(result.response.splitlines())} lines total)")

    except LLMError as e:
        final_status = "failed"
        print(f"[{instance.instance_id}] error: {e}", file=sys.stderr)
        memory.update_short_term(
            instance.instance_id,
            current_task="failed",
            status="failed",
            error=str(e),
        )
        log_file.write_text(json.dumps({
            "instance_id": instance.instance_id,
            "error": str(e),
            "timestamp": time.time(),
        }, indent=2))

    except Exception as e:
        final_status = "failed"
        traceback.print_exc()
        memory.update_short_term(
            instance.instance_id,
            current_task="failed",
            status="failed",
            error=str(e),
        )

    finally:
        registry.stop_heartbeat()
        registry.deregister(instance.instance_id, status=final_status)
        print(f"[{instance.instance_id}] deregistered")


def do_cleanup(config: Config):
    registry = InstanceRegistry(config)
    active_ids = {i.instance_id for i in registry.get_active()}
    if not config.short_term_dir.exists():
        return
    for f in config.short_term_dir.glob("*.json"):
        if f.stem not in active_ids:
            f.unlink(missing_ok=True)


def do_init(config: Config):
    config.initialize()
    do_setup(config)

    # Auto-register the webui channel
    channels = ChannelManager(config)
    channels.register("webui", "Web UI chat interface")

    # Auto-start the webui daemon
    from freza.daemon import daemonize
    pid = daemonize(config)
    print(f"\nWebUI daemon started (PID {pid})")
    print(f"  http://127.0.0.1:7888")
    print(f"  Log: {config.webui_log_file}")

    print(f"\nWorkspace: {config.base_dir}")
    print(f"Cron reflection is active ({config.cron_schedule}).")
    print(f"\nTo interact directly:")
    print(f"  freza channel webui \"hello\"")
    print(f"  freza webui --status")
    print(f"  freza status")


def do_setup(config: Config):
    config.initialize()

    agent_cmd = (
        f"{config.agent_cmd} reflect "
        f">> {config.logs_dir}/cron.log 2>&1"
    )
    cron_line = f"{config.cron_schedule} {agent_cmd}"

    try:
        existing = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True
        ).stdout
    except FileNotFoundError:
        existing = ""

    marker = "# freza-reflect"
    lines = [l for l in existing.splitlines() if marker not in l]
    lines.append(f"{cron_line}  {marker}")

    subprocess.run(
        ["crontab", "-"],
        input="\n".join(lines) + "\n",
        text=True,
        check=True,
    )

    print("Setup complete:")
    print(f"  Base dir:    {config.base_dir}")
    print(f"  Memory:      {config.memory_file}")
    print(f"  State:       {config.state_dir}")
    print(f"  Channels:    {config.channels_dir}")
    print(f"  Cron:        {cron_line}")
    print(f"\nManual invoke:")
    print(f"  {config.agent_cmd} reflect")
    print(f"  {config.agent_cmd} channel <name> \"<message>\"")


def do_status(config: Config):
    config.ensure_dirs()
    config.ensure_memory()

    registry = InstanceRegistry(config)
    memory = MemoryManager(config)
    channels = ChannelManager(config)

    instances = registry.get_active()
    chan_list = channels.list_channels()

    print("=" * 50)
    print("  Freza Status")
    print("=" * 50)

    mem = memory.read()
    mem_lines = mem.strip().splitlines()
    print(f"\n  Memory: {len(mem_lines)} lines, {len(mem)} bytes")
    for line in mem_lines[:5]:
        print(f"    {line}")
    if len(mem_lines) > 5:
        print(f"    ... ({len(mem_lines) - 5} more lines)")

    print(f"\n  Active instances: {len(instances)}")
    if instances:
        for inst in instances:
            st = memory.read_short_term(inst.instance_id)
            task = st.get("current_task", "?") if st else "?"
            age = time.time() - inst.started_at
            print(
                f"    {inst.instance_id}  mode={inst.mode:8s}  "
                f"task={task:20s}  uptime={age:.0f}s  pid={inst.pid}"
            )
    else:
        print("    (none)")

    from freza.daemon import is_running
    webui_pid = is_running(config)
    if webui_pid:
        print(f"\n  WebUI daemon: running (PID {webui_pid})")
    else:
        print(f"\n  WebUI daemon: not running")

    print(f"\n  Channels: {len(chan_list)}")
    for ch in chan_list:
        print(f"    {ch['name']}: {ch.get('description', '')}")
    if not chan_list:
        print("    (none)")

    print(f"\n  Recent logs:")
    log_files = sorted(
        config.logs_dir.glob("*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for lf in log_files[:5]:
        try:
            data = json.loads(lf.read_text())
            ts = datetime.fromtimestamp(
                data.get("timestamp", 0), timezone.utc
            ).strftime("%H:%M:%S")
            mode = data.get("mode", "?")
            dur = data.get("duration_seconds", 0)
            err = data.get("error")
            status = "X" if err else "OK"
            print(f"    {status} {ts} mode={mode} {dur:.1f}s  {lf.stem}")
        except Exception:
            pass

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Freza System",
    )
    parser.add_argument("--base-dir", default=None, help="Workspace directory (default: current directory)")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Create a new workspace")
    sub.add_parser("reflect", help="Cron reflection")

    ch = sub.add_parser("channel", help="Channel trigger")
    ch.add_argument("channel_name")
    ch.add_argument("message")
    ch.add_argument("--thread-id", default=None, help="Thread ID for multi-turn conversations")

    sub.add_parser("setup", help="Initialize workspace & install cron")

    ui = sub.add_parser("webui", help="Start the web UI server")
    ui.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    ui.add_argument("--port", type=int, default=7888, help="Bind port (default: 7888)")
    ui.add_argument("--daemon", action="store_true", help="Run as background daemon")
    ui.add_argument("--stop", action="store_true", help="Stop the running daemon")
    ui.add_argument("--status", action="store_true", help="Check if daemon is running")

    sub.add_parser("status", help="Show status")
    sub.add_parser("cleanup", help="Prune stale state")

    reg = sub.add_parser("register-channel", help="Register a channel")
    reg.add_argument("name")
    reg.add_argument("description")

    args = parser.parse_args()
    config = Config(base_dir=args.base_dir)

    if args.command == "init":
        do_init(config)

    elif args.command == "setup":
        do_setup(config)

    elif args.command == "webui":
        config.initialize()
        from freza.daemon import daemonize, stop_daemon, is_running

        if args.stop:
            if stop_daemon(config):
                print("WebUI daemon stopped.")
            else:
                print("WebUI daemon is not running.")
        elif args.status:
            pid = is_running(config)
            if pid:
                print(f"WebUI daemon is running (PID {pid})")
            else:
                print("WebUI daemon is not running.")
        elif args.daemon:
            pid = daemonize(config, host=args.host, port=args.port)
            print(f"WebUI daemon started (PID {pid})")
            print(f"  http://{args.host}:{args.port}")
            print(f"  Log: {config.webui_log_file}")
        else:
            from freza.webui.server import run as run_webui
            run_webui(config, host=args.host, port=args.port)

    elif args.command == "status":
        do_status(config)

    elif args.command == "cleanup":
        config.ensure_dirs()
        do_cleanup(config)
        print("Cleanup complete.")

    elif args.command == "register-channel":
        config.ensure_dirs()
        cm = ChannelManager(config)
        cm.register(args.name, args.description)
        print(f"Channel '{args.name}' registered.")

    elif args.command == "channel":
        config.initialize()
        do_cleanup(config)
        asyncio.run(do_invoke(
            config, mode="channel",
            channel_name=args.channel_name,
            trigger_message=args.message,
            thread_id=args.thread_id,
        ))

    else:
        config.initialize()
        do_cleanup(config)
        asyncio.run(do_invoke(config, mode="reflect"))


if __name__ == "__main__":
    main()
