"""Autonomous agent -- main entry point."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
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
from freza.agents import AgentManager, validate_agent_name
from freza.llm import invoke_claude, LLMError, InvocationResult


def _system_prompt(
    config: Config,
    instance: InstanceInfo,
    agent_name: str,
    agent_config: dict | None = None,
    channel_prompt: str | None = None,
) -> str:
    agent_dir = config.agent_dir(agent_name)
    memory_file = config.agent_memory_file(agent_name)

    base = f"""\
You are "{agent_name}", an autonomous agent running in a persistent environment.
You may be one of several simultaneous instances of yourself.
Each agent has its own memory file and working directory.

## Environment
- Your agent directory: {agent_dir}
- Long-term memory:     {memory_file}
- Short-term state:     {config.short_term_dir}/{instance.instance_id}.json
- Channels dir:         {config.channels_dir}/
- Your instance ID:     {instance.instance_id}
- Your agent name:      {agent_name}

## Memory Rules
- Edit {memory_file} directly for persistent knowledge.
  Prefer the locked helper for appends:
    {config.tools_dir}/update_memory.sh "text to append"
- Keep memory concise: identity, core knowledge, active projects, channels.
- Update your short-term state file's "current_task" field so other
  instances know what you are doing.

## Agent System
You are part of a multi-agent system. Each agent has its own directory,
memory, and optional custom invocation logic.

To create a new agent:
  {config.agent_cmd} register-agent <name> "<description>" [--system-prompt "..."]

Agent directories live at {config.agents_dir}/<name>/ and contain:
  - agent.json:  Agent configuration (name, description, system_prompt)
  - memory.md:   Agent-specific long-term memory
  - invoke.py:   Optional custom invocation script (Claude Agent SDK)

To invoke another agent directly:
  {config.agent_cmd} invoke <agent_name> "<message>" [--thread-id <id>]

Custom invoke.py convention:
  async def invoke(prompt, system_prompt, agent_dir, config_path) -> str

## Channel System
Channels are external programs that route messages to specific agents.
1. Create a program in {config.channels_dir}/<name>/
2. That program should call back:
     {config.agent_cmd} channel <name> "<message>" [--agent <agent_name>]
3. Register the channel:
     {config.agent_cmd} register-channel <name> "<description>" [--default-agent <name>]
4. To start/manage it as a background service, use systemd, supervisord,
   screen, or any method you prefer.
5. Document it in your long-term memory.

### Multi-turn threads
Pass --thread-id <id> to continue a conversation across invocations:
  {config.agent_cmd} channel <name> "<message>" --thread-id <id>
The same thread ID reuses the prior Claude session, preserving context.

### Custom system prompts
Set a channel-specific system prompt at registration time:
  {config.agent_cmd} register-channel <name> "<desc>" --system-prompt "instructions"
  {config.agent_cmd} register-channel <name> "<desc>" --system-prompt @file.txt
The custom prompt is appended to the default system prompt for every
invocation on that channel.

## Behaviour
- Check what other instances are doing before starting work.
- Do not duplicate work another instance is already handling.
- You have full bash, file-editing, and network access.
"""
    if agent_config and agent_config.get("system_prompt"):
        base += f"""
## Agent-Specific Instructions
{agent_config['system_prompt']}
"""
    if channel_prompt:
        base += f"""
## Channel-Specific Instructions
{channel_prompt}
"""
    return base


def _user_prompt(
    config: Config,
    memory: MemoryManager,
    registry: InstanceRegistry,
    channels: ChannelManager,
    agents: AgentManager,
    instance: InstanceInfo,
    agent_name: str,
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

    # Registered agents
    agent_list = agents.list_agents()
    parts.append("## Registered Agents\n")
    if agent_list:
        for a in agent_list:
            marker = " (you)" if a["name"] == agent_name else ""
            invoke_exists = config.agent_invoke_file(a["name"]).exists()
            invoke_info = " [custom invoke.py]" if invoke_exists else ""
            parts.append(
                f"- **{a['name']}**: {a.get('description', '')}{marker}{invoke_info}"
            )
    else:
        parts.append("(none)")
    parts.append("")

    instances = registry.get_active()
    others = [i for i in instances if i.instance_id != instance.instance_id]

    parts.append("## Active Instances\n")
    parts.append(f"**You**: `{instance.instance_id}` (mode={instance.mode}, "
                 f"agent={agent_name}, pid={instance.pid})")
    if others:
        parts.append(f"\n{len(others)} other instance(s):\n")
        for o in others:
            st = memory.read_short_term(o.instance_id)
            task = st.get("current_task", "unknown") if st else "unknown"
            age = time.time() - o.started_at
            parts.append(
                f"- `{o.instance_id}` mode={o.mode} agent={o.agent_name} "
                f"task=\"{task}\" uptime={age:.0f}s"
            )
    else:
        parts.append("\nYou are the only running instance.")
    parts.append("")

    chans = channels.list_channels()
    parts.append("## Registered Channels\n")
    if chans:
        for ch in chans:
            default_agent = ch.get("default_agent", "default")
            parts.append(
                f"- **{ch['name']}**: {ch.get('description', '')} "
                f"(default_agent={default_agent})"
            )
    else:
        parts.append("(none)")
    parts.append("")

    parts.append("## Trigger\n")
    if mode == "channel":
        parts.append(f"**Incoming message** on channel `{channel_name}`:\n")
        parts.append(f"```\n{trigger_message}\n```\n")
        parts.append("Respond to this message and take any appropriate actions.")
    elif mode == "invoke":
        parts.append(f"**Direct invocation** of agent `{agent_name}`:\n")
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


def _find_session_for_thread(config: Config, thread_id: str, agent_name: str) -> str | None:
    """Find the session_id from the most recent log for a given thread and agent."""
    log_files = sorted(
        config.logs_dir.glob("*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for lf in log_files:
        try:
            data = json.loads(lf.read_text())
            if (
                data.get("thread_id") == thread_id
                and data.get("agent_name") == agent_name
                and data.get("session_id")
            ):
                return data["session_id"]
        except Exception:
            continue
    return None


async def _custom_invoke(
    invoke_file: Path,
    prompt: str,
    system_prompt: str,
    agent_dir: Path,
    config_path: Path,
) -> InvocationResult:
    """Load and call an agent's custom invoke.py."""
    spec = importlib.util.spec_from_file_location("agent_invoke", invoke_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    if not hasattr(mod, "invoke"):
        raise RuntimeError(f"{invoke_file} does not define an 'invoke' function")

    start = time.time()
    response = await mod.invoke(
        prompt=prompt,
        system_prompt=system_prompt,
        agent_dir=str(agent_dir),
        config_path=str(config_path),
    )
    duration = time.time() - start

    return InvocationResult(
        response=response,
        duration_seconds=duration,
        cost_usd=0.0,
        tools_used=[],
        turns=1,
        session_id=None,
        conversation=[],
    )


async def do_invoke(
    config: Config,
    mode: str,
    channel_name: str | None = None,
    trigger_message: str | None = None,
    thread_id: str | None = None,
    agent_name: str = "default",
):
    _ensure_claude_cli()
    agents = AgentManager(config)
    registry = InstanceRegistry(config)
    channels = ChannelManager(config)

    agent_name = validate_agent_name(agent_name)
    agent_config = agents.get_agent_config(agent_name)
    if not agent_config:
        raise ValueError(
            f"Unknown agent '{agent_name}'. Register it first with:\n"
            f"  freza register-agent {agent_name} \"Description\""
        )
    memory = MemoryManager(config, agent_name=agent_name)

    instance = registry.register(
        mode=mode,
        channel_name=channel_name,
        trigger_message=trigger_message,
        agent_name=agent_name,
    )
    print(f"[{instance.instance_id}] registered (mode={mode}, agent={agent_name}, pid={instance.pid})")

    memory.write_short_term(instance.instance_id, {
        "instance_id": instance.instance_id,
        "mode": mode,
        "agent_name": agent_name,
        "channel_name": channel_name,
        "started_at": instance.started_at,
        "current_task": "initializing",
        "status": "running",
    })

    registry.start_heartbeat(instance.instance_id)

    log_file = config.logs_dir / f"{instance.instance_id}.log"
    final_status = "finished"

    try:
        channel_prompt = None
        if mode == "channel" and channel_name:
            ch_record = channels.get_channel(channel_name)
            if ch_record:
                channel_prompt = ch_record.get("system_prompt")

        system = _system_prompt(
            config, instance,
            agent_name=agent_name,
            agent_config=agent_config,
            channel_prompt=channel_prompt,
        )
        user = _user_prompt(
            config, memory, registry, channels, agents,
            instance, agent_name, mode, channel_name, trigger_message,
        )

        memory.update_short_term(instance.instance_id, current_task="thinking")

        # Check for custom invoke.py
        invoke_file = config.agent_invoke_file(agent_name)
        if invoke_file.exists():
            print(f"[{instance.instance_id}] using custom invoke.py for agent '{agent_name}'")
            result = await _custom_invoke(
                invoke_file, user, system,
                config.agent_dir(agent_name),
                config.base_dir,
            )
            if mode == "channel" and result.response:
                end = "" if result.response.endswith("\n") else "\n"
                print(result.response, end=end, flush=True)
        else:
            # Look up prior session for multi-turn threads
            resume_session = None
            if thread_id:
                resume_session = _find_session_for_thread(config, thread_id, agent_name)
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
                cwd=str(config.agent_dir(agent_name)),
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
            "agent_name": agent_name,
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
            "agent_name": agent_name,
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

    # Auto-register the webui channel with default agent
    channels = ChannelManager(config)
    channels.register("webui", "Web UI chat interface", default_agent="default")

    # Auto-start the webui daemon
    from freza.daemon import daemonize
    pid = daemonize(config)
    print(f"\nWebUI daemon started (PID {pid})")
    print(f"  http://127.0.0.1:7888")
    print(f"  Log: {config.webui_log_file}")

    print(f"\nWorkspace: {config.base_dir}")
    print(f"\nTo interact:")
    print(f"  freza invoke default \"hello\"")
    print(f"  freza channel webui \"hello\"")
    print(f"  freza register-agent researcher \"Research agent\"")
    print(f"  freza webui --status")
    print(f"  freza status")


def do_status(config: Config):
    config.ensure_dirs()

    registry = InstanceRegistry(config)
    channels = ChannelManager(config)
    agents = AgentManager(config)

    instances = registry.get_active()
    chan_list = channels.list_channels()
    agent_list = agents.list_agents()

    print("=" * 50)
    print("  Freza Status")
    print("=" * 50)

    # Agents section
    print(f"\n  Agents: {len(agent_list)}")
    for a in agent_list:
        name = a["name"]
        mem_file = config.agent_memory_file(name)
        invoke_file = config.agent_invoke_file(name)
        mem_info = ""
        if mem_file.exists():
            mem_text = mem_file.read_text()
            mem_lines = mem_text.strip().splitlines()
            mem_info = f"{len(mem_lines)} lines, {len(mem_text)} bytes"
        else:
            mem_info = "no memory"
        invoke_info = " [custom invoke.py]" if invoke_file.exists() else ""
        print(f"    {name}: {a.get('description', '')}")
        print(f"      memory: {mem_info}{invoke_info}")

        # Show memory preview
        if mem_file.exists():
            mem_text = mem_file.read_text()
            mem_lines = mem_text.strip().splitlines()
            for line in mem_lines[:3]:
                print(f"        {line}")
            if len(mem_lines) > 3:
                print(f"        ... ({len(mem_lines) - 3} more lines)")
    if not agent_list:
        print("    (none)")

    print(f"\n  Active instances: {len(instances)}")
    if instances:
        # Use default agent for short-term reads
        memory = MemoryManager(config, agent_name="default")
        for inst in instances:
            st = memory.read_short_term(inst.instance_id)
            task = st.get("current_task", "?") if st else "?"
            age = time.time() - inst.started_at
            print(
                f"    {inst.instance_id}  mode={inst.mode:8s}  "
                f"agent={inst.agent_name:12s}  "
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
        prompt_info = ""
        sp = ch.get("system_prompt")
        if sp:
            prompt_info = f"  [custom prompt: {len(sp)} chars]"
        default_agent = ch.get("default_agent", "default")
        print(f"    {ch['name']}: {ch.get('description', '')} (agent={default_agent}){prompt_info}")
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
            agent = data.get("agent_name", "?")
            dur = data.get("duration_seconds", 0)
            err = data.get("error")
            status = "X" if err else "OK"
            print(f"    {status} {ts} mode={mode} agent={agent} {dur:.1f}s  {lf.stem}")
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

    ch = sub.add_parser("channel", help="Channel trigger")
    ch.add_argument("channel_name")
    ch.add_argument("message")
    ch.add_argument("--thread-id", default=None, help="Thread ID for multi-turn conversations")
    ch.add_argument("--agent", default=None, help="Agent to route to (overrides channel default)")

    inv = sub.add_parser("invoke", help="Invoke an agent directly")
    inv.add_argument("agent_name")
    inv.add_argument("message")
    inv.add_argument("--thread-id", default=None, help="Thread ID for multi-turn conversations")

    ui = sub.add_parser("webui", help="Start the web UI server")
    ui.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    ui.add_argument("--port", type=int, default=7888, help="Bind port (default: 7888)")
    ui.add_argument("--daemon", action="store_true", help="Run as background daemon")
    ui.add_argument("--stop", action="store_true", help="Stop the running daemon")
    ui.add_argument("--status", action="store_true", help="Check if daemon is running")
    ui.add_argument("--generate-token", action="store_true", help="Generate a new API token for remote access")

    sub.add_parser("status", help="Show status")
    sub.add_parser("cleanup", help="Prune stale state")

    reg = sub.add_parser("register-channel", help="Register a channel")
    reg.add_argument("name")
    reg.add_argument("description")
    reg.add_argument("--system-prompt", default=None,
                     help="Custom system prompt (use @filepath to load from file)")
    reg.add_argument("--default-agent", default=None,
                     help="Default agent for this channel")

    reg_agent = sub.add_parser("register-agent", help="Register an agent")
    reg_agent.add_argument("name")
    reg_agent.add_argument("description")
    reg_agent.add_argument("--system-prompt", default=None,
                           help="Custom system prompt for this agent")

    args = parser.parse_args()
    config = Config(base_dir=args.base_dir)

    if args.command == "init":
        do_init(config)

    elif args.command == "webui":
        config.initialize()
        from freza.daemon import daemonize, stop_daemon, is_running

        if args.generate_token:
            token = config.webui_token(generate=True)
            print(f"API token: {token}")
            print(f"Stored in: {config.webui_token_file}")
            return

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
            token = config.webui_token()
            pid = daemonize(config, host=args.host, port=args.port, token=token)
            print(f"WebUI daemon started (PID {pid})")
            print(f"  http://{args.host}:{args.port}")
            print(f"  Log: {config.webui_log_file}")
        else:
            from freza.webui.server import run as run_webui
            token = config.webui_token()
            run_webui(config, host=args.host, port=args.port, token=token)

    elif args.command == "status":
        do_status(config)

    elif args.command == "cleanup":
        config.ensure_dirs()
        do_cleanup(config)
        print("Cleanup complete.")

    elif args.command == "register-channel":
        config.ensure_dirs()
        cm = ChannelManager(config)
        kwargs = {}
        if args.system_prompt is not None:
            prompt_val = args.system_prompt
            if prompt_val.startswith("@"):
                prompt_val = Path(prompt_val[1:]).read_text()
            kwargs["system_prompt"] = prompt_val
        if args.default_agent is not None:
            default_agent = validate_agent_name(args.default_agent)
            am = AgentManager(config)
            if not am.get_agent_config(default_agent):
                raise ValueError(
                    f"Unknown default agent '{default_agent}'. Register it first with:\n"
                    f"  freza register-agent {default_agent} \"Description\""
                )
            kwargs["default_agent"] = default_agent
        cm.register(args.name, args.description, **kwargs)
        print(f"Channel '{args.name}' registered.")
        if "system_prompt" in kwargs:
            print(f"  Custom system prompt: {len(kwargs['system_prompt'])} chars")
        if "default_agent" in kwargs:
            print(f"  Default agent: {kwargs['default_agent']}")

    elif args.command == "register-agent":
        config.ensure_dirs()
        am = AgentManager(config)
        kwargs = {}
        if args.system_prompt is not None:
            prompt_val = args.system_prompt
            if prompt_val.startswith("@"):
                prompt_val = Path(prompt_val[1:]).read_text()
            kwargs["system_prompt"] = prompt_val
        am.register(args.name, args.description, **kwargs)
        print(f"Agent '{args.name}' registered.")
        print(f"  Directory: {config.agent_dir(args.name)}")
        print(f"  Memory:    {config.agent_memory_file(args.name)}")
        if "system_prompt" in kwargs:
            print(f"  Custom system prompt: {len(kwargs['system_prompt'])} chars")

    elif args.command == "invoke":
        config.initialize()
        do_cleanup(config)
        try:
            asyncio.run(do_invoke(
                config, mode="invoke",
                trigger_message=args.message,
                thread_id=args.thread_id,
                agent_name=args.agent_name,
            ))
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            raise SystemExit(2) from e

    elif args.command == "channel":
        config.initialize()
        do_cleanup(config)

        # Resolve agent: explicit --agent flag > channel's default_agent > "default"
        agent_name = args.agent
        if not agent_name:
            cm = ChannelManager(config)
            ch_record = cm.get_channel(args.channel_name)
            if ch_record:
                agent_name = ch_record.get("default_agent", "default")
            else:
                agent_name = "default"

        try:
            asyncio.run(do_invoke(
                config, mode="channel",
                channel_name=args.channel_name,
                trigger_message=args.message,
                thread_id=args.thread_id,
                agent_name=agent_name,
            ))
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            raise SystemExit(2) from e

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
