# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent terminal's call into the single AI-line enforcement point (#18430, #17463).

The role policy ``ApprovalHandler.needs_approval`` (``auto_approve_safe`` / ``auto_approve_moderate``) is an
INPUT to the point that can only tighten: a role that needs approval for a risk can never be line 1.
With no company the owner's personal scope applies (#18430). Line 2 holds the command in this
terminal's own approval queue, so the point is told not to file a second approval for it.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from autobot_shared.async_compat import fire_and_forget
from autobot_shared.logging_manager import get_logger
from models.command_execution import CommandState
from services.ai_line_enforcement import TERMINAL_TOOL, LineVerdict, Outcome, enforce_line
from user_management.database import get_async_session_factory
from user_management.models.user import User

from .approval_handler import ApprovalHandler
from .models import AgentTerminalSession

__all__ = ["Outcome", "decide_command", "permission_refusal", "write_reservation", "resolve_command_line"]

logger = get_logger(__name__)

PENDING_APPROVAL_REFUSAL = "An earlier command is still waiting for your decision; this one did not run"


async def _owner_user_id(owner: str | None) -> str | None:
    """The verified creator's user id, from the username stamped on the session (#17053); ``None`` if unknown."""
    if not owner:
        return None
    try:
        async with get_async_session_factory()() as db:
            found = await db.execute(select(User.id).where(User.username == owner))
            user_id = found.scalar_one_or_none()
            return str(user_id) if user_id else None
    except Exception as exc:  # noqa: BLE001 - no user id means no personal scope: the command is refused
        logger.warning("Could not resolve the terminal owner's user id: %s", exc)
        return None


async def resolve_command_line(
    approval_handler: ApprovalHandler, session: AgentTerminalSession, command: str, risk
) -> LineVerdict:
    """Resolve *command*'s line for this session's company (its tenant) and agent role."""
    return await enforce_line(
        tool_name=TERMINAL_TOOL,
        params={"command": command},
        company_id=session.tenant_id,
        user_id=None if session.tenant_id else await _owner_user_id(session.owner),
        requested_by=session.agent_id,
        surface="agent_terminal",
        role_requires_approval=approval_handler.needs_approval(session.agent_role, risk),
        hold_in_approvals=False,
    )


async def decide_command(
    approval_handler: ApprovalHandler, session: AgentTerminalSession, command: str, risk, *, force_approval: bool
) -> tuple[bool, str | None]:
    """``(runs without a person, refusal)``: line 3 refuses, line 1 runs, line 2 asks the user's rules.

    ``force_approval`` sends the command to a person whatever line 1 or a learned rule would say.
    Nothing lifts line 3.
    """
    verdict = await resolve_command_line(approval_handler, session, command, risk)
    if verdict.outcome is Outcome.REFUSE:
        return False, verdict.message
    if verdict.outcome is Outcome.RUN and not force_approval:
        return True, None
    if session.has_pending_approval():  # queueing would replace it, so a yes to its card would run this one
        return False, PENDING_APPROVAL_REFUSAL
    if force_approval:
        return False, None
    user_id = session.get_user_id()
    is_auto_approved = await approval_handler.check_auto_approve_rules(
        user_id=user_id,
        command=command,
        risk_level=risk.value,
    )
    if is_auto_approved:
        logger.info("Command auto-approved by rule: %s (user: %s, risk: %s)", command, user_id, risk.value)
    return is_auto_approved, None


async def write_reservation(session: AgentTerminalSession, command, queue) -> None:
    """Queue *command*, whose pending approval is already set; a write that fails or is cancelled undoes it.

    The write is shielded, because cancelling the await would not stop its worker thread. The row is
    closed only once the write has finished, so it cannot land pending after the close.
    """
    write = asyncio.ensure_future(queue.add_command(command))
    try:
        await asyncio.shield(write)
    except BaseException:
        if (session.pending_approval or {}).get("command_id") == command.command_id:
            session.pending_approval = None
        fire_and_forget(_close_queued_command(queue, command, write), name=f"close-queued-{command.command_id}")
        raise


async def _close_queued_command(queue, command, write: "asyncio.Future") -> None:
    await asyncio.wait({write})
    command.state = CommandState.CANCELLED
    if not await queue.update_command(command):
        logger.error("Could not close queued command %s after its write was abandoned", command.command_id)


def permission_refusal(approval_handler: ApprovalHandler, session: AgentTerminalSession, command: str, risk):
    """The role policy's error response when this role may not run *risk*, else ``None``."""
    allowed, reason = approval_handler.check_agent_permission(session.agent_role, risk)
    if allowed:
        return None
    logger.warning("Agent %s denied command execution: %s", session.agent_id, reason)
    return session.get_permission_denied_response(reason, command, risk.value)
