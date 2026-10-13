# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PROPOSE a change to an AI line; never apply it (#18430, #17038).

Changing a line is itself a decision for a person, so it goes through Approvals: this files one
company-scoped approval whose context names ``ai_line.set_line``. Nothing in this module writes the
line store, and an already-pending request for the same company, action and line is reused.
"""

from __future__ import annotations

from sqlalchemy import select

from autobot_shared.ai_lines import SCOPE_COMPANY, AiLine, LineScope
from autobot_shared.logging_manager import get_logger
from llc.services.ai_lines import normalise_key
from models.approval import Approval, ApprovalStatus, ApprovalType
from services.ai_line_change_action import ACTION
from services.approval_gate_service import ApprovalGateService
from user_management.database import get_async_session_factory

logger = get_logger(__name__)

REQUESTER_PREFIX = "ai-line-change"


async def propose_line_change(
    *, scope: LineScope, key: str, line: AiLine, requested_by: str, reason: str | None = None
) -> Approval:
    """File (or reuse) the pending request to set *key* to *line* in *scope* (a company, or one user).

    A personal change is an unscoped approval whose context names the user; the handler lets only that user
    decide it.
    """
    key = normalise_key(key)
    company_id = scope.id if scope.kind == SCOPE_COMPANY else None
    scope_ctx = {"scope_kind": scope.kind, "scope_id": str(scope.id)}
    requester = f"{REQUESTER_PREFIX}:{requested_by}"
    async with get_async_session_factory()() as session:
        where = [
            Approval.status == ApprovalStatus.PENDING.value,
            Approval.approval_type == ApprovalType.WORKFLOW_GATE.value,
            Approval.requested_by_agent == requester,
            Approval.company_id == company_id if company_id else Approval.company_id.is_(None),
        ]
        for existing in (await session.execute(select(Approval).where(*where))).scalars().all():
            ctx = existing.context or {}
            same = (ctx.get("action"), ctx.get("action_key"), ctx.get("line"), ctx.get("scope_id"))
            if same == (ACTION, key, line.value, scope_ctx["scope_id"]):
                return existing
        return await ApprovalGateService(session).create_approval(
            title=f"Set the AI line for '{key}' to {line.value}",
            approval_type=ApprovalType.WORKFLOW_GATE.value,
            requested_by_agent=requester,
            description=reason or f"Change the line for '{key}' to {line.value}. Nothing changes until approved.",
            context={"action": ACTION, "action_key": key, "line": line.value, **scope_ctx},
            company_id=company_id,
        )
