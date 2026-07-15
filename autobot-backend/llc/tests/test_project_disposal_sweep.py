# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Beat sweep disposes only due + approved pending_disposal projects (#11129 P2)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import ApprovalStatus
from llc.scheduler.project_disposal_sweep import _async_sweep, _is_disposal_allowed


def _factory_for(session):
    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    return _Factory()


def _sweep_session(due):
    session = AsyncMock()
    scal = MagicMock()
    scal.scalars.return_value.all.return_value = due
    session.execute = AsyncMock(return_value=scal)
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_sweep_disposes_due_projects():
    due = [SimpleNamespace(id=uuid.uuid4(), code_source_id=None, disposal_approval_id=None)]
    session = _sweep_session(due)
    with (
        patch("llc.scheduler.project_disposal_sweep.get_async_session_factory", return_value=_factory_for(session)),
        patch("llc.scheduler.project_disposal_sweep.dispose", AsyncMock()) as disp,
        patch("llc.scheduler.project_disposal_sweep._is_disposal_allowed", AsyncMock(return_value=True)),
    ):
        count = await _async_sweep()
    assert count == 1
    disp.assert_awaited_once()


@pytest.mark.asyncio
async def test_sweep_skips_unapproved_projects():
    due = [SimpleNamespace(id=uuid.uuid4(), code_source_id=None, disposal_approval_id=uuid.uuid4())]
    session = _sweep_session(due)
    with (
        patch("llc.scheduler.project_disposal_sweep.get_async_session_factory", return_value=_factory_for(session)),
        patch("llc.scheduler.project_disposal_sweep.dispose", AsyncMock()) as disp,
        patch("llc.scheduler.project_disposal_sweep._is_disposal_allowed", AsyncMock(return_value=False)),
    ):
        count = await _async_sweep()
    assert count == 0
    disp.assert_not_awaited()


@pytest.mark.asyncio
async def test_is_disposal_allowed_no_approval_required():
    project = SimpleNamespace(disposal_approval_id=None)
    assert await _is_disposal_allowed(project, AsyncMock()) is True


@pytest.mark.asyncio
async def test_is_disposal_allowed_gates_on_approved_status():
    approval_id = uuid.uuid4()
    project = SimpleNamespace(disposal_approval_id=approval_id)

    def _session_returning(status):
        session = AsyncMock()
        res = MagicMock()
        res.scalar_one_or_none.return_value = SimpleNamespace(status=status)
        session.execute = AsyncMock(return_value=res)
        return session

    approved = _session_returning(ApprovalStatus.APPROVED.value)
    pending = _session_returning(ApprovalStatus.PENDING.value)
    assert await _is_disposal_allowed(project, approved) is True
    assert await _is_disposal_allowed(project, pending) is False

    # Missing approval row → not allowed.
    missing = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    missing.execute = AsyncMock(return_value=res)
    assert await _is_disposal_allowed(project, missing) is False
