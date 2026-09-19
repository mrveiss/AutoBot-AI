# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One permission gate for every builtin tool branch (#14529).

#14420 wired the first branch, #14469 three more, #14491 two more and #14529
the rest. Each repeated the same fourteen lines: emit the hook, log the denial,
append a ``permission_denied`` record so the model can see it, and yield an
error ``WorkflowMessage`` carrying ``cancelled_by_hook``. Six copies of a
security decision is six chances for one of them to drift — and a copy that
drifts *quietly* still returns a message, so the branch looks gated while
enforcing nothing.

The caller keeps the two things that genuinely differ per branch: which
``Permission`` the tool requires, and what to do after a denial (every current
branch returns, but the shape does not force it).

Its own module rather than another function in ``tool_handler.py``: that file
is at its recorded size ceiling and a grandfathered file may not grow (#14236).
Folding six copies into one call site each is what makes the gates fit.

Branches that stay ungated, and why (#14491 option (b), #14529)
--------------------------------------------------------------
Recorded here rather than scattered across five handlers, so the whole picture
is readable in one place. Each handler carries a one-line pointer back.

``compose``
    Gating it would gate the *interpreter*, not the effects.
    ``_build_compose_dispatch`` routes back through ``_dispatch_tool_call``, so a
    script's ``create_task`` or ``crawl_site`` already hits the gates above with
    the caller's own role. It also has ``_guard_compose``'s AST pass and a
    WORKFLOW_GATE human approval.

``read_spilled_output``
    Reads an artifact the same run already produced and already showed the model
    an excerpt of; the anchor is server-bound to its owning run and never taken
    from a caller-supplied id. Any role that could see the excerpt can see the
    window, so a permission would mean inventing a tier below the chat access
    the caller demonstrably holds. Not covered by this reasoning: anchor forgery
    or a cross-session read — a different risk class, which RBAC would not
    address either, and the thing to re-check here.

``respond``
    Loop-control, not an external effect: builds a ``WorkflowMessage`` from
    LLM-supplied text and returns ``(break_loop, respond_content)``. No dispatch,
    no I/O, not even a coroutine. A permission on it would gate the agent's
    ability to stop talking.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from async_chat_workflow import WorkflowMessage
from autobot_shared.logging_manager import get_logger
from chat_workflow.llm_handler import _emit_before_tool_execute

logger = get_logger(__name__)


async def permission_denial(
    tool_name: str,
    params: Dict[str, Any],
    session_id: str,
    permission: Optional[str],
    role: str,
    execution_results: List[Dict[str, Any]],
) -> Optional[WorkflowMessage]:
    """Run the BEFORE_TOOL_EXECUTE gate; return a message only when denied.

    ``None`` means proceed. A ``WorkflowMessage`` means the caller must yield it
    and stop before the side effect — the record has already been appended to
    ``execution_results``, because a denial the model cannot see becomes a
    silent retry loop.

    #14523: ``permission`` of ``None`` is refused by the extension rather than
    waved through, so a caller that cannot name a permission is not thereby
    exempt from the gate.
    """
    if await _emit_before_tool_execute(tool_name, params, session_id, tool_permission=permission, user_role=role):
        return None

    logger.info("[#14529] %s cancelled by permission hook (role=%s)", tool_name, role)
    execution_results.append({"tool": tool_name, "status": "error", "error": "permission_denied"})
    return WorkflowMessage(
        type="error",
        content=f"{tool_name} execution cancelled",
        metadata={"tool": tool_name, "cancelled_by_hook": True, "reason": "permission_denied"},
    )
