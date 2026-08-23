# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Bridge from an ACP prompt turn to AutoBot's chat workflow (#14825).

``AcpServer`` owns the protocol; this module owns the translation.  Keeping the
two apart means the protocol layer is testable without an LLM, and the chat
workflow never learns ACP vocabulary — the same separation AHP describes between
a coordination layer and the agent beneath it.

``ChatWorkflowManager.process_message_stream`` yields AutoBot's own message
dicts; this maps each onto the matching ``session/update`` shape.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict

from acp.protocol import agent_message_chunk, agent_thought_chunk, tool_call_update
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# One manager per agent process, initialised on the first turn.  The ACP entry
# point is a sub-process serving a single client, so process-wide is the correct
# scope here — unlike the API layer, which caches on ``app.state``.
_manager: Any = None

# AutoBot message types that represent the agent's visible reply.
_REPLY_TYPES = {"llm_response", "agent_llm_chunk", "default", "bot"}
# Types representing internal reasoning, surfaced separately by ACP clients.
_THOUGHT_TYPES = {"thought", "agent_step_start", "planning"}
# Types representing tool activity.
_TOOL_TYPES = {"tool_code", "tool_output", "agent_tool_call", "agent_tool_result"}


def _text_of(message: Dict[str, Any]) -> str:
    """Extract displayable text from an AutoBot workflow message."""
    for key in ("text", "content", "message", "chunk"):
        value = message.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


async def autobot_turn_runner(session_id: str, prompt: str, cwd: str) -> AsyncIterator[Dict[str, Any]]:
    """Run one turn through AutoBot and yield ACP ``session/update`` payloads.

    Imports are deferred: the ACP entry point must be startable without pulling
    the whole chat stack at module import time, and a missing dependency should
    surface as a clear error on the first turn rather than an import crash.
    """
    global _manager
    try:
        if _manager is None:
            from chat_workflow import ChatWorkflowManager

            _manager = ChatWorkflowManager()
            await _manager.initialize()
    except Exception as exc:
        logger.error("Chat workflow unavailable for ACP turn: %s", exc)
        yield agent_message_chunk(session_id, f"AutoBot chat workflow is unavailable: {exc}")
        return

    manager = _manager
    context: Dict[str, Any] = {"cwd": cwd, "source": "acp"}

    async for message in manager.process_message_stream(session_id, prompt, context):
        if not isinstance(message, dict):
            continue
        message_type = str(message.get("type") or message.get("message_type") or "default")
        text = _text_of(message)
        if not text:
            continue

        if message_type in _THOUGHT_TYPES:
            yield agent_thought_chunk(session_id, text)
        elif message_type in _TOOL_TYPES:
            yield tool_call_update(
                session_id,
                tool_call_id=str(message.get("tool_call_id") or message.get("id") or "tool"),
                title=str(message.get("tool_name") or message_type),
                status="completed" if "result" in message_type or "output" in message_type else "in_progress",
                kind="execute",
            )
        elif message_type in _REPLY_TYPES:
            yield agent_message_chunk(session_id, text)
        else:
            # Unknown types still reach the user as reply text rather than
            # being dropped — silence would be worse than an imperfect label.
            yield agent_message_chunk(session_id, text)
