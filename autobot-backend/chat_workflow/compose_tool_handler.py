# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Compose-tool (GH#11568) body helpers for ``chat_workflow.tool_handler``.

Extracted from ``tool_handler`` (#14491) to offset that PR's own additions and
keep the module under its file-size ceiling — the same move #14469 made for
``browser_tool_handler.py``.

Unlike the browser extraction, several of these functions are called back
into ``self`` from ``ToolHandlerMixin._handle_compose_tool`` via matching
one-line delegate methods that KEEP their original names
(``_guard_compose``, ``_persist_compose_approval``, ``_poll_compose_approval``,
``_compose_shim_snapshot``, ``_execute_compose``, ...): several are replaced
wholesale by an ``AsyncMock``/plain mock in
``tests/unit/chat_workflow/test_code_exec.py`` (e.g.
``handler._persist_compose_approval = AsyncMock(...)``), which only works
because ``_handle_compose_tool`` still dispatches through ``self.<method>``
rather than calling a module-level function directly. Moving the *bodies*
here while keeping the delegate methods preserves that contract.

``_dispatch_tool_call`` (bound to the live ``ToolHandlerMixin`` instance) is
threaded in explicitly as ``dispatch_tool_call`` rather than imported, since
this module carries no instance state of its own.
"""

from __future__ import annotations

import asyncio
import uuid as uuid_module
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from async_chat_workflow import WorkflowMessage
from autobot_shared.env_utils import env_flag, env_int
from autobot_shared.logging_manager import get_logger
from chat_workflow.code_exec.tool_policy import CODEEXEC_READONLY_TOOLS
from utils.errors import RepairableException

if TYPE_CHECKING:
    from chat_workflow.models import LLMIterationContext

logger = get_logger(__name__)

# GH#11568: compose tool tuning constants — moved here from tool_handler.py
# (#14491) along with the functions that are their only readers.
CODEEXEC_AUTOAPPROVE_READONLY: bool = env_flag("AUTOBOT_CODEEXEC_AUTOAPPROVE_READONLY", default=True)
# #13481: this is how long THIS TURN waits, not how long the approval lives —
# see tool_handler.py's CODEEXEC_ENABLED block for the full rationale (kept
# there since it also documents the deliberate absence of an expiry knob).
CODEEXEC_APPROVAL_WAIT_SECONDS: int = env_int("AUTOBOT_CODEEXEC_APPROVAL_WAIT_SECONDS", default=1800)
CODEEXEC_APPROVAL_POLL_SECONDS: int = env_int("AUTOBOT_CODEEXEC_APPROVAL_POLL_SECONDS", default=2)

DispatchToolCall = Callable[..., Any]


def guard_compose(program: str, agent_id: "str | None") -> "WorkflowMessage | None":
    """Run AST guard; return error WorkflowMessage on violation, else None."""
    from chat_workflow.code_exec.ast_guard import check_script
    from chat_workflow.code_exec.shim_codegen import injectable_tool_set
    from orchestration.agent_registry import resolve_forbidden_tools

    forbidden = resolve_forbidden_tools(agent_id)
    injected = frozenset(injectable_tool_set([], forbidden))
    verdict = check_script(program, frozenset(forbidden), injected_tools=injected)
    if verdict.ok:
        return None
    lines = "; ".join(f"line {v['line']}: {v['message']}" for v in verdict.violations)
    return WorkflowMessage(
        type="tool_result",
        content=f"compose script rejected by AST guard: {lines}",
        metadata={"tool_name": "compose", "ast_violations": verdict.violations},
    )


def compose_auto_approvable(shim_snapshot: list[str]) -> bool:
    """Auto-approve only when the flag is on AND all shims are read-only (design §3.1)."""
    return CODEEXEC_AUTOAPPROVE_READONLY and set(shim_snapshot) <= CODEEXEC_READONLY_TOOLS


async def poll_compose_approval(approval_id: str) -> str:
    """Poll the WORKFLOW_GATE until decided; return its terminal status (GH#11568 MINOR-2).

    Mirrors the terminal-command approval loop: a bounded poll on the persisted
    gate. Returns ``approved``/``rejected``/``revision_requested``, or
    ``timeout`` when no decision lands within the wait budget.
    """
    from services.approval_gate_service import ApprovalGateService
    from user_management.database import get_async_session_factory

    elapsed = 0
    session_factory = get_async_session_factory()
    while elapsed < CODEEXEC_APPROVAL_WAIT_SECONDS:
        async with session_factory() as db:
            approval = await ApprovalGateService(db).get(uuid_module.UUID(approval_id))
        status = getattr(approval, "status", None)
        if status and status != "pending":
            return status
        await asyncio.sleep(CODEEXEC_APPROVAL_POLL_SECONDS)
        elapsed += CODEEXEC_APPROVAL_POLL_SECONDS
    return "timeout"


async def persist_compose_approval(program: str, shim_snapshot: list[str], session_id: str) -> "str | None":
    """Persist a WORKFLOW_GATE Approval carrying program + shims + budgets (GH#11568)."""
    from chat_workflow.code_exec.broker import CODEEXEC_MAX_TOOL_CALLS
    from models.approval import ApprovalType
    from secure_sandbox_executor import CODEEXEC_TIMEOUT_SECONDS
    from services.approval_gate_service import ApprovalGateService
    from user_management.database import get_async_session_factory

    context = {
        "program": program,
        "shim_snapshot": shim_snapshot,
        "budgets": {"max_tool_calls": CODEEXEC_MAX_TOOL_CALLS, "timeout_seconds": CODEEXEC_TIMEOUT_SECONDS},
    }
    session_factory = get_async_session_factory()
    async with session_factory() as db:
        approval = await ApprovalGateService(db).create_approval(
            title="compose script execution",
            approval_type=ApprovalType.WORKFLOW_GATE.value,
            requested_by_agent="chat_agent",
            description="Sandboxed Python compose script awaiting approval.",
            workflow_id=session_id,
            workflow_step="compose",
            context=context,
        )
        return str(approval.id)


def build_compose_dispatch(
    session_id: str, ctx: "LLMIterationContext | None", dispatch_tool_call: DispatchToolCall
) -> Callable[[str, dict], Awaitable[Any]]:
    """Return an async dispatch callable routing shim calls through the seam (GH#11568)."""

    async def _dispatch(tool: str, params: dict) -> Any:
        from chat_workflow.session_role import DEFAULT_AUTH_ROLE  # noqa: PLC0415

        sub_results: list[dict[str, Any]] = []
        sub_call = {"name": tool, "params": params}
        # #13821: a tool called from inside a compose script is still the same
        # authenticated caller. Omitting the role here left this one path on
        # the "user" default — the very bug this issue fixes, unfixed.
        role = ctx.auth_role if ctx is not None else DEFAULT_AUTH_ROLE
        async for _ in dispatch_tool_call(
            sub_call, session_id, session_id, "", "", sub_results, [], ctx=ctx, role=role
        ):
            pass
        last = sub_results[-1] if sub_results else {}
        if last.get("status") == "error":
            raise RepairableException(last.get("error", "tool dispatch failed"))
        return last.get("output", last)

    return _dispatch


async def execute_compose(
    program: str,
    agent_id: "str | None",
    run_id: str,
    session_id: str,
    ctx: "LLMIterationContext | None",
    dispatch_tool_call: DispatchToolCall,
) -> "WorkflowMessage":
    """Run the script inside the sandbox via a live broker; return result msg."""
    from chat_workflow.code_exec.broker import CodeExecBroker
    from chat_workflow.code_exec.shim_codegen import generate_shim_module, injectable_tool_set
    from orchestration.agent_registry import resolve_forbidden_tools
    from secure_sandbox_executor import CODEEXEC_TIMEOUT_SECONDS, SecureSandboxExecutor  # lazy

    forbidden = resolve_forbidden_tools(agent_id)
    tools = injectable_tool_set([], forbidden)
    shim_src = generate_shim_module(tools)
    broker = CodeExecBroker(
        build_compose_dispatch(session_id, ctx, dispatch_tool_call),
        tools,
        forbidden,
        run_id,
        f"autobot:codeexec:security:events:{run_id}",
        progress_channel=f"workflow:{session_id}",
    )
    executor = SecureSandboxExecutor()
    result = await executor.execute_with_stdio_broker(program, shim_src, broker, CODEEXEC_TIMEOUT_SECONDS, run_id)
    return compose_result_message(result, run_id)


def compose_result_message(result: Any, run_id: str) -> "WorkflowMessage":
    """Build the tool_result WorkflowMessage from a SandboxResult (GH#11568)."""
    if result.success:
        return WorkflowMessage(
            type="tool_result",
            content=result.stdout or "(no output)",
            metadata={"tool_name": "compose", "run_id": run_id},
        )
    content = f"compose execution failed (exit {result.exit_code}): {result.stderr or result.stdout}"
    return WorkflowMessage(
        type="tool_result",
        content=content,
        metadata={"tool_name": "compose", "run_id": run_id, "failed": True},
    )


def compose_shim_snapshot(agent_id: "str | None") -> list[str]:
    """Injectable-tool snapshot for this agent (allowlist ∩ allowed − forbidden)."""
    from chat_workflow.code_exec.shim_codegen import injectable_tool_set
    from orchestration.agent_registry import resolve_forbidden_tools

    return injectable_tool_set([], resolve_forbidden_tools(agent_id))


def reject_delegated_compose(agent_id: "str | None") -> "WorkflowMessage | None":
    """Main-chat-only: reject compose for any profile-bound (delegated) agent (GH#11568)."""
    if agent_id is None:
        return None
    return WorkflowMessage(
        type="tool_result",
        content="compose is not available for delegated subagents",
        metadata={"tool_name": "compose"},
    )


def compose_gate_request_msg(approval_id: str, shim_snapshot: list[str]) -> "WorkflowMessage":
    """Build the WORKFLOW_GATE approval-required notification (GH#11568)."""
    return WorkflowMessage(
        type="approval_required",
        content="compose script requires approval before execution",
        metadata={
            "tool": "compose",
            "approval_required": True,
            "approval_id": approval_id,
            "shim_snapshot": shim_snapshot,
        },
    )


def compose_gate_refusal_msg(status: str) -> "WorkflowMessage":
    """Terminal refusal message for a non-approved gate (GH#11568)."""
    return WorkflowMessage(
        type="tool_result",
        content=f"compose execution not approved (gate status: {status}).",
        metadata={"tool_name": "compose", "approval_status": status, "denied": True},
    )


__all__ = [
    "build_compose_dispatch",
    "compose_auto_approvable",
    "compose_gate_refusal_msg",
    "compose_gate_request_msg",
    "compose_result_message",
    "compose_shim_snapshot",
    "execute_compose",
    "guard_compose",
    "persist_compose_approval",
    "poll_compose_approval",
    "reject_delegated_compose",
]
