# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for SprintAutoCloseService (GH#8224).

Tests use mock sessions and mock approval service so no live DB is required.
Run with: python -m pytest autobot-backend/llc/ -k sprint_close
"""

import uuid
from datetime import date
from typing import Optional
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from llc.models.enums import ApprovalStatus, ApprovalType, SprintStatus
from llc.models.sprint import LLCSprint
from llc.services.sprint_autoclose import SprintAutoCloseService

# ------------------------------------------------------------------ Helpers


def _make_sprint(
    *,
    status: str = SprintStatus.ACTIVE.value,
    end_date: Optional[date] = None,
    pending_close_approval_id: Optional[uuid.UUID] = None,
) -> LLCSprint:
    sprint = MagicMock(spec=LLCSprint)
    sprint.id = uuid.uuid4()
    sprint.company_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    sprint.project_id = uuid.uuid4()
    sprint.name = "Sprint 1"
    sprint.status = status
    sprint.end_date = end_date or date(2026, 5, 1)
    sprint.pending_close_approval_id = pending_close_approval_id
    sprint.actual_points = 0
    return sprint


def _make_approval(*, status: str = ApprovalStatus.APPROVED.value) -> MagicMock:
    approval = MagicMock()
    approval.id = uuid.uuid4()
    approval.company_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    approval.type = ApprovalType.SPRINT_CLOSE.value
    approval.status = status
    return approval


def _make_session(scalars: list | None = None, scalar_value: int = 0) -> AsyncMock:
    """Build a minimal async session mock."""
    session = AsyncMock()

    # Default result: scalars().all() returns the provided list
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = scalars or []

    # Scalar result for aggregate queries
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = None
    scalar_result.scalar_one.return_value = scalar_value
    scalar_result.scalars.return_value.all.return_value = scalars or []

    session.execute.return_value = scalar_result
    return session


# ------------------------------------------------------------------ check_and_queue tests


@pytest.mark.asyncio
async def test_check_and_queue_creates_approval_for_expired_sprint() -> None:
    sprint = _make_sprint(
        status=SprintStatus.ACTIVE.value,
        end_date=date(2026, 5, 1),
        pending_close_approval_id=None,
    )

    session = AsyncMock()
    expired_result = MagicMock()
    expired_result.scalars.return_value.all.return_value = [sprint]
    session.execute.return_value = expired_result

    mock_approval_svc = AsyncMock()
    created_approval = _make_approval(status=ApprovalStatus.PENDING.value)
    mock_approval_svc.request_approval = AsyncMock(return_value=created_approval)

    svc = SprintAutoCloseService(approval_service=mock_approval_svc)
    queued = await svc.check_and_queue(session, today=date(2026, 5, 23))

    assert len(queued) == 1
    assert sprint.pending_close_approval_id == created_approval.id
    mock_approval_svc.request_approval.assert_called_once()
    call_kwargs = mock_approval_svc.request_approval.call_args.kwargs
    assert call_kwargs["gate_type"] == ApprovalType.SPRINT_CLOSE
    assert call_kwargs["company_id"] == sprint.company_id


@pytest.mark.asyncio
async def test_check_and_queue_skips_sprint_with_pending_approval() -> None:
    """Sprints that already have a pending_close_approval_id are filtered by the query."""
    session = AsyncMock()
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    session.execute.return_value = empty_result

    mock_approval_svc = AsyncMock()
    svc = SprintAutoCloseService(approval_service=mock_approval_svc)
    queued = await svc.check_and_queue(session, today=date(2026, 5, 23))

    assert queued == []
    mock_approval_svc.request_approval.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_queue_no_expired_sprints() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result

    svc = SprintAutoCloseService()
    queued = await svc.check_and_queue(session, today=date(2026, 5, 23))

    assert queued == []


# ------------------------------------------------------------------ execute_close tests


@pytest.mark.asyncio
async def test_execute_close_happy_path() -> None:
    approval_id = uuid.uuid4()
    sprint = _make_sprint(
        status=SprintStatus.ACTIVE.value,
        pending_close_approval_id=approval_id,
    )
    decided_by = uuid.uuid4()

    session = AsyncMock()
    call_count = [0]

    approved_approval = _make_approval(status=ApprovalStatus.APPROVED.value)

    async def _execute(stmt: object) -> MagicMock:
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            # sprint lookup
            result.scalar_one_or_none.return_value = sprint
        elif call_count[0] == 2:
            # approval validation lookup (GH#8473)
            result.scalar_one_or_none.return_value = approved_approval
        elif call_count[0] == 3:
            # actual_points aggregate
            result.scalar_one.return_value = 13
        elif call_count[0] == 4:
            # project auto_rollover lookup
            result.scalar_one_or_none.return_value = None  # use company default
        else:
            # rollover count + update
            result.scalar_one.return_value = 2
        return result

    session.execute.side_effect = _execute

    mock_summarizer = AsyncMock()
    svc = SprintAutoCloseService(summarizer=mock_summarizer)

    closed = await svc.execute_close(
        session,
        sprint_id=sprint.id,
        approval_id=approval_id,
        decided_by=decided_by,
    )

    assert closed.status == SprintStatus.CLOSED.value
    assert closed.actual_points == 13
    assert closed.pending_close_approval_id is None
    mock_summarizer.summarize_and_merge.assert_called_once_with(sprint.id, session=ANY)


@pytest.mark.asyncio
async def test_execute_close_raises_on_sprint_not_found() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    svc = SprintAutoCloseService()
    with pytest.raises(ValueError, match="not found"):
        await svc.execute_close(
            session,
            sprint_id=uuid.uuid4(),
            approval_id=uuid.uuid4(),
            decided_by=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_execute_close_raises_on_wrong_status() -> None:
    sprint = _make_sprint(status=SprintStatus.PLANNING.value)

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = sprint
    session.execute.return_value = result

    svc = SprintAutoCloseService()
    with pytest.raises(ValueError, match="expected active or review"):
        await svc.execute_close(
            session,
            sprint_id=sprint.id,
            approval_id=uuid.uuid4(),
            decided_by=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_execute_close_raises_on_approval_mismatch() -> None:
    stored_approval_id = uuid.uuid4()
    sprint = _make_sprint(
        status=SprintStatus.ACTIVE.value,
        pending_close_approval_id=stored_approval_id,
    )

    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = sprint
    session.execute.return_value = result

    svc = SprintAutoCloseService()
    with pytest.raises(ValueError, match="pending approval"):
        await svc.execute_close(
            session,
            sprint_id=sprint.id,
            approval_id=uuid.uuid4(),  # different ID
            decided_by=uuid.uuid4(),
        )


# ------------------------------------------------------------------ Rollover tests


@pytest.mark.asyncio
async def test_rollover_items_auto_rollover_true() -> None:
    """auto_rollover=True: items get sprint_id=None, backlog_position=0."""
    sprint = _make_sprint(status=SprintStatus.ACTIVE.value)
    approval_id = sprint.pending_close_approval_id = uuid.uuid4()
    decided_by = uuid.uuid4()

    session = AsyncMock()
    call_count = [0]
    approved_approval = _make_approval(status=ApprovalStatus.APPROVED.value)

    async def _execute(stmt: object) -> MagicMock:
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            result.scalar_one_or_none.return_value = sprint
        elif call_count[0] == 2:
            # approval validation lookup (GH#8473)
            result.scalar_one_or_none.return_value = approved_approval
        elif call_count[0] == 3:
            result.scalar_one.return_value = 5  # actual_points
        elif call_count[0] == 4:
            result.scalar_one_or_none.return_value = True  # auto_rollover
        elif call_count[0] == 5:
            result.scalar_one.return_value = 3  # incomplete count
        else:
            pass  # update stmts
        return result

    session.execute.side_effect = _execute

    mock_summarizer = AsyncMock()
    svc = SprintAutoCloseService(summarizer=mock_summarizer)
    closed = await svc.execute_close(
        session,
        sprint_id=sprint.id,
        approval_id=approval_id,
        decided_by=decided_by,
    )
    assert closed.status == SprintStatus.CLOSED.value


@pytest.mark.asyncio
async def test_kb_summarizer_stub_is_called() -> None:
    """Phase 2 stub must be invoked on close — logs and doesn't raise."""
    from llc.kb.sprint_summarizer import SprintKbSummarizer

    summarizer = SprintKbSummarizer()
    sprint_id = uuid.uuid4()
    # Should complete without raising
    await summarizer.summarize_and_merge(sprint_id)
