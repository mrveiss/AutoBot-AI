# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Stop a turn whose model keeps calling tools that do not exist (#20848).

The tools reminder (``ChatWorkflowManager._build_tools_reminder``) starts at ``limits.INVALID_CALL_LIMIT``. A model
that still cannot name a tool ``limits.INVALID_TOOL_ABORT_LIMIT`` calls in a row is not helped by a third reminder:
the turn ends with ``INVALID_TOOL_ABORT_REPLY`` and the stop is written to the audit trail.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from async_chat_workflow import WorkflowMessage
from autobot_shared.logging_manager import get_logger
from chat_workflow import limits
from services.audit_logger import audit_log

logger = get_logger(__name__)

INVALID_TOOL_ABORT_REPLY = (
    "I could not form a valid tool call after several attempts, so I stopped instead of repeating them. "
    "Please rephrase the request or try again."
)


def should_abort(consecutive_invalid_tool_calls: int) -> bool:
    """Whether *consecutive_invalid_tool_calls* has reached the abort limit."""
    return consecutive_invalid_tool_calls >= limits.INVALID_TOOL_ABORT_LIMIT


async def abort_message(ctx, iteration: int) -> WorkflowMessage:
    """The honest failure that ends the turn; records the stop in the audit trail."""
    logger.warning(
        "Stopping session %s after %d consecutive invalid tool calls (limit %d)",
        ctx.session_id,
        ctx.consecutive_invalid_tool_calls,
        limits.INVALID_TOOL_ABORT_LIMIT,
    )
    recorded = await audit_log(
        "chat.invalid_tool_calls_abort",
        result="failed",
        session_id=ctx.session_id,
        details={"consecutive_invalid": ctx.consecutive_invalid_tool_calls, "iteration": iteration},
    )
    if not recorded:
        logger.error("The invalid-tool-call stop of session %s could not be written to the audit trail", ctx.session_id)
    message = WorkflowMessage(
        type="response",
        content=INVALID_TOOL_ABORT_REPLY,
        metadata={"invalid_tool_abort": True, "iteration": iteration},
    )
    ctx.workflow_messages.append(message)
    return message


async def abort_invalid_tools(state: Dict[str, Any], config: RunnableConfig) -> dict:
    """Graph node (#20848): the same stop as the streaming loop, for a turn the graph routed here.

    ``route_after_execution`` sends a turn here once ``should_abort`` holds for the state's
    ``consecutive_invalid_tool_calls``; the counter is the one ``unknown_tool_error`` raises on the iteration context.
    """
    iteration = state.get("iteration_count", 0)
    ctx = SimpleNamespace(
        session_id=state.get("session_id"),
        consecutive_invalid_tool_calls=state.get("consecutive_invalid_tool_calls", 0),
        workflow_messages=[],
    )
    message = (await abort_message(ctx, iteration)).to_dict()
    stream_cb = config["configurable"].get("stream_callback")
    if stream_cb:
        stream_cb(message)
    return {"workflow_messages": [*state.get("workflow_messages", []), message], "should_continue": False}
