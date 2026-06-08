# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for LLC board approval gates — GH#8214.

Tests cover:
- ApprovalService.request_approval
- ApprovalService.decide (approve / reject)
- ApprovalService.get_pending
- requires_approval decorator
- API route layer (via TestClient + in-memory mocks)
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.approval import LLCApproval
from llc.models.enums import ApprovalStatus, ApprovalType
from llc.services.approval import (
    ApprovalNotFoundError,
    ApprovalRequiredError,
    ApprovalService,
    ApprovalStateError,
    requires_approval,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_approval(
    *,
    id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    gate_type: ApprovalType = ApprovalType.HIRE,
    status: ApprovalStatus = ApprovalStatus.PENDING,
    requested_by: uuid.UUID | None = None,
    payload: Dict[str, Any] | None = None,
    decided_by: uuid.UUID | None = None,
    decided_at: datetime | None = None,
) -> MagicMock:
    """Build a lightweight MagicMock that looks like LLCApproval without a DB session.

    Using MagicMock avoids SQLAlchemy's _sa_instance_state requirement while
    still providing the attribute interface the service layer queries.
    """
    a = MagicMock(spec=LLCApproval)
    a.id = id or uuid.uuid4()
    a.company_id = company_id or uuid.uuid4()
    a.type = gate_type.value
    a.status = status.value
    a.requested_by_agent_id = requested_by or uuid.uuid4()
    a.payload = payload or {}
    a.decided_by_agent_id = decided_by
    a.decided_at = decided_at
    a.created_at = datetime.now(timezone.utc)
    a.updated_at = datetime.now(timezone.utc)
    return a


def _make_session_stub(scalar_result: Any = None) -> MagicMock:
    """Return an async session that returns ``scalar_result`` from execute."""
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = scalar_result
    session.execute = AsyncMock(return_value=execute_result)
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# ApprovalService.request_approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_approval_creates_pending_record() -> None:
    """request_approval should add a PENDING row and call flush."""
    svc = ApprovalService()
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    company_id = uuid.uuid4()
    requester = uuid.uuid4()

    with patch("llc.services.approval.get_async_redis_client", new_callable=AsyncMock) as mock_redis_fn:
        mock_redis = AsyncMock()
        mock_redis_fn.return_value = mock_redis

        approval = await svc.request_approval(
            session,
            company_id=company_id,
            gate_type=ApprovalType.HIRE,
            payload={"role": "engineer"},
            requested_by=requester,
        )

    session.add.assert_called_once_with(approval)
    session.flush.assert_awaited_once()
    assert approval.type == ApprovalType.HIRE.value
    assert approval.status == ApprovalStatus.PENDING.value
    assert approval.company_id == company_id
    assert approval.requested_by_agent_id == requester


@pytest.mark.asyncio
async def test_request_approval_publishes_redis_event() -> None:
    """request_approval should publish to llc:approval_requested."""
    svc = ApprovalService()
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    with patch("llc.services.approval.get_async_redis_client", new_callable=AsyncMock) as mock_redis_fn:
        mock_redis = AsyncMock()
        mock_redis_fn.return_value = mock_redis

        approval = await svc.request_approval(
            session,
            company_id=uuid.uuid4(),
            gate_type=ApprovalType.STRATEGY,
            payload={},
            requested_by=uuid.uuid4(),
        )
        await svc.publish_requested(approval)

    mock_redis.publish.assert_awaited_once()
    channel, raw_payload = mock_redis.publish.call_args[0]
    assert channel == "llc:approval_requested"
    data = json.loads(raw_payload)
    assert data["type"] == ApprovalType.STRATEGY.value
    assert data["approval_id"] == str(approval.id)


@pytest.mark.asyncio
async def test_request_approval_survives_redis_unavailable() -> None:
    """request_approval should succeed even when Redis returns None."""
    svc = ApprovalService()
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    with patch("llc.services.approval.get_async_redis_client", new_callable=AsyncMock) as mock_redis_fn:
        mock_redis_fn.return_value = None
        approval = await svc.request_approval(
            session,
            company_id=uuid.uuid4(),
            gate_type=ApprovalType.BUDGET_OVERRIDE,
            payload={},
            requested_by=uuid.uuid4(),
        )

    assert approval.status == ApprovalStatus.PENDING.value


# ---------------------------------------------------------------------------
# ApprovalService.decide
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decide_approve_sets_status_and_decided_fields() -> None:
    """decide(APPROVED) should update status, decided_by, and decided_at."""
    existing = _make_approval(status=ApprovalStatus.PENDING)
    session = _make_session_stub(scalar_result=existing)

    svc = ApprovalService()
    decider = uuid.uuid4()

    with patch("llc.services.approval.get_async_redis_client", new_callable=AsyncMock) as mock_redis_fn:
        mock_redis_fn.return_value = AsyncMock()

        updated = await svc.decide(
            session,
            approval_id=existing.id,
            decision=ApprovalStatus.APPROVED,
            decided_by=decider,
        )

    assert updated.status == ApprovalStatus.APPROVED.value
    assert updated.decided_by_agent_id == decider
    assert updated.decided_at is not None
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_decide_reject_sets_rejected_status() -> None:
    existing = _make_approval(status=ApprovalStatus.PENDING)
    session = _make_session_stub(scalar_result=existing)

    svc = ApprovalService()

    with patch("llc.services.approval.get_async_redis_client", new_callable=AsyncMock) as mock_redis_fn:
        mock_redis_fn.return_value = AsyncMock()

        updated = await svc.decide(
            session,
            approval_id=existing.id,
            decision=ApprovalStatus.REJECTED,
            decided_by=uuid.uuid4(),
        )

    assert updated.status == ApprovalStatus.REJECTED.value


@pytest.mark.asyncio
async def test_decide_publishes_decided_event() -> None:
    existing = _make_approval(status=ApprovalStatus.PENDING)
    session = _make_session_stub(scalar_result=existing)

    svc = ApprovalService()

    with patch("llc.services.approval.get_async_redis_client", new_callable=AsyncMock) as mock_redis_fn:
        mock_redis = AsyncMock()
        mock_redis_fn.return_value = mock_redis

        updated = await svc.decide(
            session,
            approval_id=existing.id,
            decision=ApprovalStatus.APPROVED,
            decided_by=uuid.uuid4(),
        )
        await svc.publish_decided(updated, ApprovalStatus.APPROVED)

    mock_redis.publish.assert_awaited_once()
    channel, raw_payload = mock_redis.publish.call_args[0]
    assert channel == "llc:approval_decided"
    data = json.loads(raw_payload)
    assert data["decision"] == ApprovalStatus.APPROVED.value


@pytest.mark.asyncio
async def test_decide_raises_not_found_when_missing() -> None:
    session = _make_session_stub(scalar_result=None)
    svc = ApprovalService()

    with pytest.raises(ApprovalNotFoundError):
        await svc.decide(
            session,
            approval_id=uuid.uuid4(),
            decision=ApprovalStatus.APPROVED,
            decided_by=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_decide_raises_state_error_when_not_pending() -> None:
    existing = _make_approval(status=ApprovalStatus.APPROVED)
    session = _make_session_stub(scalar_result=existing)
    svc = ApprovalService()

    with pytest.raises(ApprovalStateError):
        await svc.decide(
            session,
            approval_id=existing.id,
            decision=ApprovalStatus.REJECTED,
            decided_by=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_decide_raises_state_error_for_invalid_decision() -> None:
    existing = _make_approval(status=ApprovalStatus.PENDING)
    session = _make_session_stub(scalar_result=existing)
    svc = ApprovalService()

    with pytest.raises(ApprovalStateError):
        await svc.decide(
            session,
            approval_id=existing.id,
            decision=ApprovalStatus.WITHDRAWN,
            decided_by=uuid.uuid4(),
        )


# ---------------------------------------------------------------------------
# ApprovalService.get_pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pending_returns_list() -> None:
    expected = [_make_approval(), _make_approval()]
    session = AsyncMock()
    execute_result = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = expected
    execute_result.scalars.return_value = scalars_result
    session.execute = AsyncMock(return_value=execute_result)

    svc = ApprovalService()
    result = await svc.get_pending(session, uuid.uuid4())

    assert result == expected


@pytest.mark.asyncio
async def test_get_pending_with_type_filter() -> None:
    """Verify the query is executed (type filter is passed to the service layer)."""
    session = AsyncMock()
    execute_result = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = []
    execute_result.scalars.return_value = scalars_result
    session.execute = AsyncMock(return_value=execute_result)

    svc = ApprovalService()
    result = await svc.get_pending(session, uuid.uuid4(), gate_type=ApprovalType.SPRINT_CLOSE)

    session.execute.assert_awaited_once()
    assert result == []


# ---------------------------------------------------------------------------
# requires_approval decorator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_requires_approval_passes_with_approved_approval() -> None:
    """Decorated method should execute when approval is APPROVED and correct type."""
    approval = _make_approval(gate_type=ApprovalType.HIRE, status=ApprovalStatus.APPROVED)
    session = _make_session_stub(scalar_result=approval)

    class _Svc(ApprovalService):
        @requires_approval(ApprovalType.HIRE)
        async def do_hire(self, session: Any, *, approval_id: uuid.UUID, name: str) -> str:
            return f"hired:{name}"

    result = await _Svc().do_hire(session, approval_id=approval.id, name="Alice")
    assert result == "hired:Alice"


@pytest.mark.asyncio
async def test_requires_approval_raises_when_no_approval_id() -> None:
    """Decorated method should raise ApprovalRequiredError when approval_id is missing."""
    session = _make_session_stub()

    class _Svc(ApprovalService):
        @requires_approval(ApprovalType.STRATEGY)
        async def do_strategy(self, session: Any, *, approval_id: uuid.UUID) -> None:
            pass

    with pytest.raises(ApprovalRequiredError) as exc_info:
        await _Svc().do_strategy(session)

    assert exc_info.value.gate_type == ApprovalType.STRATEGY


@pytest.mark.asyncio
async def test_requires_approval_raises_when_approval_not_found() -> None:
    session = _make_session_stub(scalar_result=None)

    class _Svc(ApprovalService):
        @requires_approval(ApprovalType.HIRE)
        async def do_hire(self, session: Any, *, approval_id: uuid.UUID) -> None:
            pass

    with pytest.raises(ApprovalNotFoundError):
        await _Svc().do_hire(session, approval_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_requires_approval_raises_on_wrong_type() -> None:
    approval = _make_approval(gate_type=ApprovalType.STRATEGY, status=ApprovalStatus.APPROVED)
    session = _make_session_stub(scalar_result=approval)

    class _Svc(ApprovalService):
        @requires_approval(ApprovalType.HIRE)
        async def do_hire(self, session: Any, *, approval_id: uuid.UUID) -> None:
            pass

    with pytest.raises(ApprovalStateError, match="type"):
        await _Svc().do_hire(session, approval_id=approval.id)


@pytest.mark.asyncio
async def test_requires_approval_raises_when_not_approved() -> None:
    approval = _make_approval(gate_type=ApprovalType.HIRE, status=ApprovalStatus.PENDING)
    session = _make_session_stub(scalar_result=approval)

    class _Svc(ApprovalService):
        @requires_approval(ApprovalType.HIRE)
        async def do_hire(self, session: Any, *, approval_id: uuid.UUID) -> None:
            pass

    with pytest.raises(ApprovalStateError, match="APPROVED"):
        await _Svc().do_hire(session, approval_id=approval.id)


def test_requires_approval_attaches_gate_type_metadata() -> None:
    """The decorator should attach __approval_gate__ for introspection."""

    class _Svc(ApprovalService):
        @requires_approval(ApprovalType.BUDGET_OVERRIDE)
        async def do_override(self, session: Any, *, approval_id: uuid.UUID) -> None:
            pass

    assert _Svc.do_override.__approval_gate__ == ApprovalType.BUDGET_OVERRIDE
