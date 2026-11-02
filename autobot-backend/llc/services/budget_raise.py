# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A company with ``require_approval_for_budget_raises`` cannot raise a budget limit without the board (#8214).

Without it an admin could lift an agent's limit directly and skip the BUDGET_OVERRIDE approval. What counts as a
raise is judged on the limit that is actually enforced: the token limit for a tokens-mode budget that has one,
the dollar limit otherwise. A change of which of the two is enforced cannot be compared (dollars against
tokens) and can lift enforcement altogether, so it needs the approval too. Lowering a limit, or touching only
the alert threshold, applies at once.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.models.organization import Organization

from ..models.budget import LLCAgentBudget
from ..models.enums import ApprovalType
from .approval import ApprovalService


class BudgetRaisePending(BaseModel):
    """Answer to a limit change that needs the board: the request exists, the limit has not moved (#8214)."""

    status: str = "pending_approval"
    approval_id: str
    company_id: str
    agent_id: str


async def company_requires_budget_approval(session: AsyncSession, company_id: uuid.UUID) -> bool:
    """Whether *company_id* has ``require_approval_for_budget_raises`` on; an unknown company does not."""
    row = await session.execute(
        select(Organization.require_approval_for_budget_raises).where(Organization.id == company_id)
    )
    return bool(row.scalar_one_or_none())


def _enforced(mode: str, dollars: Any, tokens: Optional[int]) -> Tuple[str, Decimal]:
    """Which limit bites, and its value: tokens only for a tokens-mode budget that has a token limit."""
    if mode == "tokens" and tokens is not None:
        return "tokens", Decimal(int(tokens))
    return "dollars", Decimal(str(dollars))


def raises_limit(row: LLCAgentBudget, mode: Optional[str], dollars: Any, tokens: Optional[int]) -> bool:
    """Whether setting (*mode*, *dollars*, *tokens*) -- ``None`` meaning unchanged -- lifts the enforced limit."""
    before = _enforced(str(row.budget_mode), row.budget_limit, row.token_limit)
    after = _enforced(
        mode if mode is not None else str(row.budget_mode),
        dollars if dollars is not None else row.budget_limit,
        tokens if tokens is not None else row.token_limit,
    )
    return after[0] != before[0] or after[1] > before[1]


def override_payload(agent_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """The BUDGET_OVERRIDE payload for the fields the caller set (``None`` = not set), JSON-ready."""
    return {
        "agent_id": agent_id,
        **{k: str(v) if isinstance(v, Decimal) else v for k, v in fields.items() if v is not None},
    }


async def file_budget_raise(
    session: AsyncSession, svc: ApprovalService, row: LLCAgentBudget, payload: Dict[str, Any], requester: uuid.UUID
) -> BudgetRaisePending:
    """Record the raise as a pending BUDGET_OVERRIDE and commit it; the requester is the verified caller.

    Nothing about the budget changes until the board approves it, under the same four-eyes rule as a hire.
    """
    approval = await svc.request_approval(
        session,
        company_id=uuid.UUID(str(row.company_id)),
        gate_type=ApprovalType.BUDGET_OVERRIDE,
        payload=payload,
        requested_by=str(requester),
        actor_user_id=requester,
    )
    await session.commit()
    await svc.publish_requested(approval)
    return BudgetRaisePending(approval_id=str(approval.id), company_id=str(row.company_id), agent_id=row.agent_id)
