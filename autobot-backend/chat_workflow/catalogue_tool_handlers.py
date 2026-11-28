# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Chat handlers of the tools the catalogue (``tools/tool_records.py``) serves without MCP.

* ``read_spilled_output`` (#13919): re-reads a window of a spilled tool result.
* ``query_self_model``, ``query_system_information`` and ``list_system_services`` (#22278, #22267): dispatched to
  ``ToolRegistry``, which had no production caller, so the model could not reach them from chat. Each is gated by
  the permission the catalogue declares for it, and receives the AUTHENTICATED caller, never one the model names.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from async_chat_workflow import WorkflowMessage
from autobot_shared.logging_manager import get_logger
from autobot_shared.self_model_constants import ENTITY_KINDS
from chat_workflow.tool_permission_gate import permission_denial
from tools.tool_records import SELF_MODEL_QUERY_TOOL_NAME, permission_value_for

logger = get_logger(__name__)

SYSTEM_INFO_TOOL_NAME = "query_system_information"
LIST_SERVICES_TOOL_NAME = "list_system_services"

#: Tools run through ``ToolRegistry.execute_tool`` from chat.
REGISTRY_CHAT_TOOL_NAMES: frozenset[str] = frozenset(
    {SELF_MODEL_QUERY_TOOL_NAME, SYSTEM_INFO_TOOL_NAME, LIST_SERVICES_TOOL_NAME}
)

_NO_ARGUMENTS: dict = {"type": "object", "properties": {}}

REGISTRY_CHAT_TOOL_SCHEMAS: dict[str, dict] = {
    SELF_MODEL_QUERY_TOOL_NAME: {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(ENTITY_KINDS), "description": "Entity kind to list."},
            "name": {"type": "string", "description": "Substring of the entity name."},
            "node_id": {"type": "string", "description": "Only entities on this node."},
            "status": {"type": "string", "description": "declared, probed_ok, probed_failed, absent or stale."},
            "limit": {"type": "integer", "description": "Entities to return (capped server-side)."},
        },
    },
    SYSTEM_INFO_TOOL_NAME: _NO_ARGUMENTS,
    LIST_SERVICES_TOOL_NAME: _NO_ARGUMENTS,
}


def _failure(tool_name: str, reason: str, execution_results: list[dict[str, Any]]) -> WorkflowMessage:
    """Record a refused or failed registry tool and return the error the model sees."""
    execution_results.append({"tool": tool_name, "status": "error", "error": reason})
    return WorkflowMessage(type="error", content=reason, metadata={"tool": tool_name, "error": True})


async def handle_registry_tool(
    tool_name: str,
    tool_call: dict[str, Any],
    execution_results: list[dict[str, Any]],
    session_id: str,
    role: str,
    user_id: str | None,
) -> AsyncIterator[WorkflowMessage]:
    """Run one catalogue tool through ``ToolRegistry`` as *user_id*, after the catalogue's permission gate.

    A tool whose catalogue permission is ``None`` declares no check, so the gate (which refuses a missing
    permission, #14523) is skipped for it; the tool itself decides what the caller may see. Without a verified
    user no tool runs at all.
    """
    from tools.tool_registry import ToolRegistry  # noqa: PLC0415  (tools -> chat_workflow import cycle, #4557)

    params = tool_call.get("params", {}) or {}
    if not user_id:
        yield _failure(tool_name, "no verified user for this turn", execution_results)
        return
    permission = permission_value_for(tool_name)
    if permission is not None:
        denial = await permission_denial(tool_name, params, session_id, permission, role, execution_results)
        if denial is not None:
            yield denial
            return
    try:
        result = await ToolRegistry().execute_tool(tool_name, params, user_id)
    except Exception as exc:  # noqa: BLE001 - reported to the model as a tool error, never swallowed
        logger.error("%s failed: %s", tool_name, exc, exc_info=True)
        yield _failure(tool_name, f"{tool_name} failed: {exc}", execution_results)
        return
    output = result.get("result", "")
    text = output if isinstance(output, str) else json.dumps(output, default=str, ensure_ascii=False)
    status = result.get("status", "error")
    execution_results.append({"tool": tool_name, "status": status, "output": text})
    yield WorkflowMessage(
        type="command_output" if status == "success" else "error",
        content=text,
        metadata={"tool": tool_name, "status": status},
    )


#: What to tell the model when an anchor does not resolve, by reason.
#: Module-level rather than rebuilt per call.
_SPILL_MISS_ADVICE: dict[str, str] = {
    # Bad offset/limit — the model can fix this itself, so mirror the
    # self-correction hint the schema gate gives.
    "invalid_window": "offset and limit must be integers. Retry this anchor with valid values.",
    # No run is bound to this context: an anchor cannot resolve here at all,
    # and a different anchor would fare no better.
    "no_run_bound": "No run is bound to this context, so no spilled output is readable. Do not retry.",
    # The artifact is genuinely gone or never existed.
    "not_found": "Do not retry this anchor.",
}

#: The default, for a miss whose cause the reader could not determine.
#:
#: `read_spilled` swallows every exception into `None`, and a cross-run refusal
#: returns `None` too, so an unknown reason covers a truncated artifact mid-write
#: (spill_if_oversized writes with a bare write_text, no temp+rename, to a
#: content-addressed path a re-spill rewrites), a transient OSError, a
#: PermissionError, and a run-scope refusal. In every one of those the output is
#: still on disk. Telling the model "do not retry" there is a permanent verdict
#: on a cause nobody established — the shape this whole issue is about.
_SPILL_MISS_UNKNOWN_ADVICE = (
    "The read did not report why it failed. This may be transient — retrying once is reasonable."
)


async def read_spilled_output(
    tool_call: dict[str, Any],
    execution_results: list[dict[str, Any]],
):
    """Re-read a window of a tool result that was spilled out of context (#13919).
    #14529: ungated by decision — see chat_workflow/tool_permission_gate.

    #13692 writes oversized tool output aside and leaves a bounded excerpt
    plus an anchor, and the excerpt's note tells the model to call this tool.
    #13754 made it dispatchable through ``ToolRegistry.execute_tool`` — which
    has no production callers, so at this seam, the one every real tool call
    funnels through, the instruction still named something unreachable. An
    agent following it landed in ``_build_unknown_tool_error`` and burned its
    invalid-call budget.

    The run is bound server-side by the agent loop, never taken from
    arguments: the anchor carries its owning run id in plaintext, so a
    ``task_id`` parameter would let any holder of an anchor read the run it
    came from by echoing the id back.

    Yields:
        WorkflowMessage for the read result.
    """
    params = tool_call.get("params", {})
    anchor = str(params.get("anchor", ""))

    try:
        from agent_loop.tool_output_spill import read_spilled_window

        # Off the event loop. read_spilled reads and json-parses the WHOLE
        # artifact (up to SPILL_MAX_ARTIFACT_CHARS, 5,000,000) before
        # slicing out at most 8,000 chars, so paging a large artifact means
        # re-reading and re-parsing it once per call. The write side already
        # took this decision — spill_results_async exists because a blocking
        # write_text stalls every other coroutine in the process.
        window = await asyncio.to_thread(
            read_spilled_window, anchor, offset=params.get("offset", 0), limit=params.get("limit")
        )
    except Exception as exc:
        logger.error("[#13919] read_spilled_output failed: %s", exc)
        execution_results.append({"tool": "read_spilled_output", "status": "error", "error": str(exc)})
        yield WorkflowMessage(
            type="error",
            content=f"read_spilled_output failed: {exc}",
            metadata={"tool": "read_spilled_output", "error": True},
        )
        return

    if not window.get("found"):
        # The miss reasons need different responses. Flattening them into
        # "do not retry" tells a model to abandon an anchor over a
        # self-correctable argument error, or over a transient one.
        reason = window.get("reason", "unknown")
        advice = _SPILL_MISS_ADVICE.get(reason, _SPILL_MISS_UNKNOWN_ADVICE)
        execution_results.append({"tool": "read_spilled_output", "status": reason, "anchor": anchor})
        yield WorkflowMessage(
            type="command_output",
            content=f"No spilled output for anchor {anchor!r} ({reason}). {advice}",
            metadata={"tool": "read_spilled_output", "status": reason},
        )
        return

    execution_results.append({"tool": "read_spilled_output", "status": "success", "output": window["content"]})
    yield WorkflowMessage(
        type="command_output",
        content=window["content"],
        metadata={
            "tool": "read_spilled_output",
            "status": "success",
            "offset": window["offset"],
            "total_chars": window["total_chars"],
            "has_more": window["has_more"],
        },
    )
