# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC ApprovalService — board approval gates (GH#8214).

Provides:
- ``ApprovalService.request_approval`` — create a pending approval record
- ``ApprovalService.decide`` — approve or reject
- ``ApprovalService.get_pending`` — list pending approvals for a company
- ``ApprovalService.log_decision_to_kb`` — post-decision hook: indexes to decisions KB (GH#8243)
- ``requires_approval`` — decorator that gates async methods behind a board approval
"""

import functools
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client

from ..kb.decision_log import DecisionLogWriter
from ..models.approval import LLCApproval
from ..models.enums import ApprovalStatus, ApprovalType
from .base import LLCServiceBase

logger = logging.getLogger(__name__)

_EVENT_REQUESTED = "llc:approval_requested"
_EVENT_DECIDED = "llc:approval_decided"


class ApprovalRequiredError(Exception):
    """Raised when a gated operation is called without a valid approved approval."""

    def __init__(self, gate_type: ApprovalType) -> None:
        self.gate_type = gate_type
        super().__init__(f"Approval of type '{gate_type.value}' required before this operation")


class ApprovalNotFoundError(Exception):
    """Raised when an approval record cannot be located."""


class ApprovalStateError(Exception):
    """Raised when an approval is in an unexpected state for the requested action."""


class ApprovalService(LLCServiceBase):
    """Manages LLC board approval gate records."""

    async def request_approval(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        gate_type: ApprovalType,
        payload: Dict[str, Any],
        requested_by: uuid.UUID,
    ) -> LLCApproval:
        """Create a pending approval record and emit a Redis event.

        Args:
            session: Async SQLAlchemy session (caller owns the transaction).
            company_id: Tenant company.
            gate_type: The gate type being requested.
            payload: Arbitrary context for the board reviewer.
            requested_by: Agent ID making the request.

        Returns:
            The newly created ``LLCApproval`` row (status=PENDING).
        """
        approval = LLCApproval(
            company_id=company_id,
            type=gate_type.value,
            status=ApprovalStatus.PENDING.value,
            requested_by_agent_id=requested_by,
            payload=payload,
        )
        session.add(approval)
        await session.flush()
        logger.info(
            "Approval requested: id=%s type=%s company=%s requested_by=%s",
            approval.id,
            gate_type.value,
            company_id,
            requested_by,
        )
        return approval

    async def publish_requested(self, approval: "LLCApproval") -> None:
        """Publish approval_requested event — call AFTER the DB transaction commits."""
        await self._publish(
            _EVENT_REQUESTED,
            {
                "approval_id": str(approval.id),
                "company_id": str(approval.company_id),
                "type": approval.type,
                "requested_by_agent_id": str(approval.requested_by_agent_id),
            },
        )

    async def decide(
        self,
        session: AsyncSession,
        *,
        approval_id: uuid.UUID,
        decision: ApprovalStatus,
        decided_by: uuid.UUID,
    ) -> LLCApproval:
        """Record an approve or reject decision.

        Args:
            session: Async SQLAlchemy session.
            approval_id: ID of the pending approval.
            decision: Must be ``APPROVED`` or ``REJECTED``.
            decided_by: Agent ID making the decision.

        Returns:
            Updated ``LLCApproval`` row.

        Raises:
            ApprovalNotFoundError: approval_id does not exist.
            ApprovalStateError: approval is not in PENDING state, or decision
                value is not APPROVED/REJECTED.
        """
        if decision not in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
            raise ApprovalStateError(f"Decision must be APPROVED or REJECTED, got {decision.value!r}")

        result = await session.execute(select(LLCApproval).where(LLCApproval.id == approval_id).with_for_update())
        approval = result.scalar_one_or_none()
        if approval is None:
            raise ApprovalNotFoundError(f"Approval {approval_id} not found")

        if approval.status != ApprovalStatus.PENDING.value:
            raise ApprovalStateError(f"Approval {approval_id} is already in state {approval.status!r}")

        approval.status = decision.value
        approval.decided_by_agent_id = decided_by
        approval.decided_at = datetime.now(timezone.utc)
        await session.flush()
        logger.info(
            "Approval decided: id=%s decision=%s decided_by=%s",
            approval_id,
            decision.value,
            decided_by,
        )
        return approval

    async def publish_decided(self, approval: "LLCApproval", decision: ApprovalStatus) -> None:
        """Publish approval_decided event — call AFTER the DB transaction commits."""
        await self._publish(
            _EVENT_DECIDED,
            {
                "approval_id": str(approval.id),
                "company_id": str(approval.company_id),
                "type": approval.type,
                "decision": decision.value,
                "decided_by_agent_id": str(approval.decided_by_agent_id),
            },
        )

    async def log_decision_to_kb(self, approval: "LLCApproval") -> None:
        """Post-decision hook: index the resolved approval into the decisions KB (GH#8243).

        Best-effort — never raises; KB failures are logged but do not affect callers.
        Call AFTER the DB transaction commits, alongside ``publish_decided``.
        """
        try:
            writer = DecisionLogWriter()
            await writer.write(approval)
        except Exception as exc:
            logger.warning(
                "Decision KB write failed for approval %s (non-fatal): %s",
                approval.id,
                exc,
            )

    async def get_pending(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        gate_type: Optional[ApprovalType] = None,
    ) -> List[LLCApproval]:
        """Return all pending approvals for a company, optionally filtered by type.

        Args:
            session: Async SQLAlchemy session.
            company_id: Tenant company.
            gate_type: If provided, filter to this gate type only.

        Returns:
            List of ``LLCApproval`` rows with status=PENDING, ordered oldest-first.
        """
        stmt = (
            select(LLCApproval)
            .where(
                LLCApproval.company_id == company_id,
                LLCApproval.status == ApprovalStatus.PENDING.value,
            )
            .order_by(LLCApproval.created_at)
        )
        if gate_type is not None:
            stmt = stmt.where(LLCApproval.type == gate_type.value)

        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def _publish(channel: str, payload: Dict[str, Any]) -> None:
        """Best-effort Redis pub/sub publish — never raises."""
        redis = await get_async_redis_client()
        if redis is None:
            logger.warning("Redis unavailable; skipping publish to %s", channel)
            return
        try:
            await redis.publish(channel, json.dumps(payload))
        except Exception as exc:
            logger.warning("Failed to publish to %s: %s", channel, exc)


def requires_approval(gate_type: ApprovalType) -> Callable:
    """Decorator that gates an async method behind a validated board approval.

    The decorated function must accept an ``approval_id: uuid.UUID`` keyword
    argument.  When called, the decorator checks that a corresponding
    ``LLCApproval`` with the right type and ``APPROVED`` status exists.

    Usage::

        class HireService(LLCServiceBase):
            @requires_approval(ApprovalType.HIRE)
            async def hire_agent(
                self,
                session: AsyncSession,
                *,
                approval_id: uuid.UUID,
                agent_name: str,
            ) -> ...:
                ...

    Raises:
        ApprovalRequiredError: No ``approval_id`` supplied.
        ApprovalNotFoundError: approval_id does not exist.
        ApprovalStateError: The approval is not APPROVED or is of the wrong type.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(self: Any, session: AsyncSession, *args: Any, **kwargs: Any) -> Any:
            approval_id: Optional[uuid.UUID] = kwargs.get("approval_id")
            if approval_id is None:
                raise ApprovalRequiredError(gate_type)

            result = await session.execute(select(LLCApproval).where(LLCApproval.id == approval_id))
            approval = result.scalar_one_or_none()

            if approval is None:
                raise ApprovalNotFoundError(f"Approval {approval_id} not found")
            if approval.type != gate_type.value:
                raise ApprovalStateError(
                    f"Approval {approval_id} is type {approval.type!r}, expected {gate_type.value!r}"
                )
            if approval.status != ApprovalStatus.APPROVED.value:
                raise ApprovalStateError(f"Approval {approval_id} has status {approval.status!r}, must be APPROVED")
            target_company_id: Optional[uuid.UUID] = kwargs.get("company_id")
            if target_company_id is not None and approval.company_id != target_company_id:
                raise ApprovalStateError(
                    f"Approval {approval_id} belongs to company {approval.company_id!r}, " f"not {target_company_id!r}"
                )

            return await fn(self, session, *args, **kwargs)

        # Attach gate_type metadata for introspection.
        wrapper.__approval_gate__ = gate_type  # type: ignore[attr-defined]
        return wrapper

    return decorator


__all__ = [
    "ApprovalService",
    "ApprovalRequiredError",
    "ApprovalNotFoundError",
    "ApprovalStateError",
    "requires_approval",
    "_EVENT_REQUESTED",
    "_EVENT_DECIDED",
]
