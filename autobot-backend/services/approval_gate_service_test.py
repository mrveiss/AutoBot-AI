# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for ApprovalGateService (#1402), added alongside the #17043/#17056 changes.

No prior test file existed for this service. Covers:
- #17056: a decision comment's author_type is the caller's, never a literal.
- #17043: the unscoped chokepoint (get/list_approvals/_get_or_raise) excludes
  a company-scoped (LLC) row, so the still-unauthenticated-by-tenant general
  API can't leak data the migration moved into the same table.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.approval import Approval, ApprovalStatus
from services.approval_gate_service import ApprovalGateService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_approval(*, status: str = ApprovalStatus.PENDING.value) -> MagicMock:
    a = MagicMock(spec=Approval)
    a.id = uuid.uuid4()
    a.status = status
    a.company_id = None
    return a


def _make_session(scalar_result: object = None) -> AsyncMock:
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = scalar_result
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# #17056: author_type on a decision comment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_records_the_callers_author_type_on_its_comment() -> None:
    approval = _make_approval()
    session = _make_session(scalar_result=approval)
    svc = ApprovalGateService(session)

    await svc.approve(approval.id, "alice", "lgtm", author_type="human")

    comment = session.add.call_args[0][0]
    assert comment.author_type == "human"


@pytest.mark.asyncio
async def test_approve_records_a_non_human_callers_author_type() -> None:
    """A run/device JWT or the service key approving records that, not 'human' (#17056)."""
    approval = _make_approval()
    session = _make_session(scalar_result=approval)
    svc = ApprovalGateService(session)

    await svc.reject(approval.id, "run:workflow-42", "blocked", author_type="agent")

    comment = session.add.call_args[0][0]
    assert comment.author_type == "agent"


@pytest.mark.asyncio
async def test_add_comment_uses_the_explicit_author_type_not_a_default() -> None:
    approval = _make_approval()
    session = _make_session(scalar_result=approval)
    svc = ApprovalGateService(session)

    comment = await svc.add_comment(approval.id, "service:slm", "auto-escalated", author_type="system")

    assert comment.author_type == "system"


# ---------------------------------------------------------------------------
# #17043: never serve a company-scoped row through the unscoped chokepoint
# ---------------------------------------------------------------------------


def _statement_excludes_company_scoped_rows(session: AsyncMock) -> bool:
    stmt = session.execute.call_args[0][0]
    return "company_id IS NULL" in str(stmt)


@pytest.mark.asyncio
async def test_get_excludes_a_company_scoped_row() -> None:
    session = _make_session(scalar_result=None)
    svc = ApprovalGateService(session)

    await svc.get(uuid.uuid4())

    assert _statement_excludes_company_scoped_rows(session)


@pytest.mark.asyncio
async def test_list_approvals_excludes_company_scoped_rows() -> None:
    session = _make_session()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=execute_result)
    svc = ApprovalGateService(session)

    await svc.list_approvals()

    assert _statement_excludes_company_scoped_rows(session)


@pytest.mark.asyncio
async def test_approve_on_a_company_scoped_id_is_treated_as_not_found() -> None:
    """The general API has no tenant context to authorize an LLC row (#17043)."""
    session = _make_session(scalar_result=None)  # excluded by the WHERE, so "not found"
    svc = ApprovalGateService(session)

    with pytest.raises(ValueError, match="not found"):
        await svc.approve(uuid.uuid4(), "alice", author_type="human")

    assert _statement_excludes_company_scoped_rows(session)
