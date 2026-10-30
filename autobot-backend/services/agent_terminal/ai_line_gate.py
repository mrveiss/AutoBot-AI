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

from sqlalchemy import select

from autobot_shared.logging_manager import get_logger
from services.ai_line_enforcement import TERMINAL_TOOL, LineVerdict, Outcome, enforce_line
from user_management.database import get_async_session_factory
from user_management.models.user import User

from .approval_handler import ApprovalHandler
from .models import AgentTerminalSession

__all__ = ["Outcome", "decide_command", "resolve_command_line"]

logger = get_logger(__name__)


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
    if force_approval:
        return False, None
    if verdict.outcome is Outcome.RUN:
        return True, None
    user_id = session.get_user_id()
    is_auto_approved = await approval_handler.check_auto_approve_rules(
        user_id=user_id,
        command=command,
        risk_level=risk.value,
    )
    if is_auto_approved:
        logger.info("Command auto-approved by rule: %s (user: %s, risk: %s)", command, user_id, risk.value)
    return is_auto_approved, None
