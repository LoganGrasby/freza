"""LLM invocation via the Claude Code SDK."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import claude_agent_sdk._internal.client as _client
import claude_agent_sdk._internal.message_parser as _mp
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

# Patch the parser to tolerate unknown message types (e.g. rate_limit_event)
# instead of crashing the stream.
_original_parse = _client.parse_message


def _tolerant_parse(data):
    try:
        return _original_parse(data)
    except _mp.MessageParseError:
        return None


_client.parse_message = _tolerant_parse

MAX_CONTENT_LENGTH = int(os.environ.get("AGENT_LOG_MAX_CONTENT", 50_000))


def _truncate(text: str) -> tuple[str, dict]:
    if len(text) <= MAX_CONTENT_LENGTH:
        return text, {}
    return text[:MAX_CONTENT_LENGTH], {"truncated": True, "original_length": len(text)}


def _serialize_content_block(block) -> dict | None:
    if isinstance(block, TextBlock):
        text, extra = _truncate(block.text)
        return {"type": "text", "text": text, **extra}
    if isinstance(block, ThinkingBlock):
        thinking, extra = _truncate(block.thinking)
        return {"type": "thinking", "thinking": thinking, "signature": block.signature, **extra}
    if isinstance(block, ToolUseBlock):
        inp = json.dumps(block.input, default=str)
        if len(inp) > MAX_CONTENT_LENGTH:
            return {
                "type": "tool_use", "id": block.id, "name": block.name,
                "input": inp[:MAX_CONTENT_LENGTH],
                "truncated": True, "original_length": len(inp),
            }
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    if isinstance(block, ToolResultBlock):
        content = block.content
        extra = {}
        if isinstance(content, str):
            content, extra = _truncate(content)
        elif isinstance(content, list):
            content = json.dumps(content, default=str)
            content, extra = _truncate(content)
        return {
            "type": "tool_result", "tool_use_id": block.tool_use_id,
            "content": content, "is_error": block.is_error, **extra,
        }
    return {"type": type(block).__name__, "data": str(block)}


def _serialize_message(message) -> dict | None:
    if isinstance(message, AssistantMessage):
        blocks = [_serialize_content_block(b) for b in message.content]
        d = {"role": "assistant", "model": message.model, "content": [b for b in blocks if b]}
        if message.parent_tool_use_id:
            d["parent_tool_use_id"] = message.parent_tool_use_id
        if getattr(message, "error", None):
            d["error"] = message.error
        return d
    if isinstance(message, UserMessage):
        if isinstance(message.content, list):
            blocks = [_serialize_content_block(b) for b in message.content]
            content = [b for b in blocks if b]
        elif isinstance(message.content, str):
            content, extra = _truncate(message.content)
            if extra:
                content = {"text": content, **extra}
        else:
            content = str(message.content)
        d = {"role": "user", "content": content}
        if message.parent_tool_use_id:
            d["parent_tool_use_id"] = message.parent_tool_use_id
        return d
    if isinstance(message, SystemMessage):
        return {"role": "system", "subtype": message.subtype, "data": message.data}
    if isinstance(message, ResultMessage):
        return {
            "role": "result",
            "subtype": message.subtype,
            "duration_ms": message.duration_ms,
            "duration_api_ms": message.duration_api_ms,
            "is_error": message.is_error,
            "num_turns": message.num_turns,
            "session_id": message.session_id,
            "total_cost_usd": message.total_cost_usd,
            "usage": message.usage,
            "result": message.result,
            "structured_output": getattr(message, "structured_output", None),
        }
    return None


class LLMError(RuntimeError):
    pass


@dataclass
class InvocationResult:
    response: str = ""
    duration_seconds: float = 0.0
    cost_usd: float = 0.0
    tools_used: list[str] = field(default_factory=list)
    turns: int = 0
    conversation: list[dict] = field(default_factory=list)


async def invoke_claude(
    prompt: str,
    *,
    system_prompt: str | None = None,
    cwd: str = ".",
    model: str = "sonnet",
    max_turns: int = 50,
    on_text: Callable[[str], None] | None = None,
) -> InvocationResult:
    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        cwd=cwd,
        model=model,
        max_turns=max_turns,
    )

    if system_prompt:
        options.system_prompt = system_prompt

    result = InvocationResult()
    response_parts: list[str] = []
    start = time.monotonic()

    try:
        async for message in query(prompt=prompt, options=options):
            if message is None:
                continue

            serialized = _serialize_message(message)
            if serialized is not None:
                result.conversation.append(serialized)

            if isinstance(message, AssistantMessage):
                result.turns += 1
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_parts.append(block.text)
                        if on_text:
                            on_text(block.text)
                    elif isinstance(block, ToolUseBlock):
                        result.tools_used.append(block.name)

            elif isinstance(message, ResultMessage):
                result.cost_usd = message.total_cost_usd or 0.0

    except Exception as e:
        result.duration_seconds = time.monotonic() - start
        raise LLMError(f"Agent failed: {e}") from e

    result.duration_seconds = time.monotonic() - start
    result.response = "\n".join(response_parts)
    return result
