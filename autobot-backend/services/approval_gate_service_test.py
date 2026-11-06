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
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import sqlalchemy as sa

from autobot_shared.time_utils import now_utc
from llc.tests.test_ai_lines_api_18430 import factory  # noqa: F401 -- fixture
from models.approval import Approval, ApprovalComment, ApprovalStatus
from services import approval_execution
from services.approval_gate_service import ApprovalGateService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_approval(*, status: str = ApprovalStatus.PENDING.value) -> MagicMock:
    a = MagicMock(spec=Approval)
    a.id = uuid.uuid4()
    a.status = status
    a.company_id = None
    # #17141 review: an unconfigured MagicMock attribute is truthy and
    # supports .get(), so run_post_approval_actions's `(approval.context or
    # {}).get("action")` would read a mock object as a real, unregistered
    # action name -- these tests are about decision-comment authorship, not
    # post-approval dispatch, so a real approval's actual default (no
    # context at all) is what they mean to simulate.
    a.context = None
    # #13421: likewise for resume dispatch -- an unconfigured mock's source and
    # resume_ref are truthy, which would read as an approval waiting on a resumer.
    a.source = None
    a.resume_ref = None
    a.expires_at = None
    return a


def _make_session(scalar_result: object = None) -> AsyncMock:
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = scalar_result
    execute_result.first.return_value = (1,)  # #18413: the conditional UPDATE claimed the row
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


@pytest.mark.asyncio
async def test_unlink_task_on_a_company_scoped_id_is_treated_as_not_found() -> None:
    """unlink_task must go through _get_or_raise like every sibling mutation (#17043 review).

    Before this fix it queried TaskApprovalLink directly, so the general,
    tenant-blind API could delete an LLC approval's task link.
    """
    session = _make_session(scalar_result=None)  # excluded by the WHERE, so "not found"
    svc = ApprovalGateService(session)

    with pytest.raises(ValueError, match="not found"):
        await svc.unlink_task(uuid.uuid4(), "task-1")

    assert _statement_excludes_company_scoped_rows(session)
    # _get_or_raise's own select must be the only one issued -- unlink_task
    # never reaches its TaskApprovalLink query once the guard refuses.
    session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# #18978: the action's decider review, before the decision commits
# ---------------------------------------------------------------------------

_REFUSED = "test.refused_decider_18978"


@pytest.fixture
def refused_action():
    """An action whose review writes to the session and then refuses; yields its post-approval handler."""

    async def _refuse(approval, session) -> bool:
        session.add(ApprovalComment(approval_id=approval.id, author="review", author_type="system", body="uncommitted"))
        raise ValueError("refused by the review")

    handler = AsyncMock()
    approval_execution.register_post_approval_action(_REFUSED, handler, proposed_by="test", review=_refuse)
    with patch("events.bus.publish_event", AsyncMock()):
        yield handler
    for registry in (
        approval_execution._REGISTRY,
        approval_execution._PROPOSERS,
        approval_execution._FREE_TEXT_KEYS,
        approval_execution._DECISION_REVIEWS,
    ):
        registry.pop(_REFUSED, None)


async def _stored(factory, status: str) -> uuid.UUID:  # noqa: F811
    async with factory() as session:
        row = Approval(title="x", approval_type="workflow_gate", status=status, context={"action": _REFUSED})
        session.add(row)
        await session.commit()
        return row.id


async def _state(factory, approval_id: uuid.UUID) -> tuple:  # noqa: F811
    async with factory() as session:
        row = await session.get(Approval, approval_id)
        comments = (await session.execute(sa.select(ApprovalComment))).scalars().all()
        return row.status, row.decided_by_user, row.decided_at, [c.body for c in comments]


@pytest.mark.asyncio
async def test_a_refusing_review_rolls_back_with_no_claim_and_no_comment(factory, refused_action) -> None:  # noqa: F811
    """The same session commits afterwards, so what the review had pending survives unless it was rolled back."""
    approval_id = await _stored(factory, ApprovalStatus.PENDING.value)
    async with factory() as session:
        with pytest.raises(ValueError, match="refused by the review"):
            await ApprovalGateService(session).approve(approval_id, "alice", "lgtm", author_type="human")
        await session.commit()
    assert await _state(factory, approval_id) == (ApprovalStatus.PENDING.value, None, None, [])
    refused_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_decided_row_gets_the_transition_error_not_the_review(factory, refused_action) -> None:  # noqa: F811
    approval_id = await _stored(factory, ApprovalStatus.APPROVED.value)
    async with factory() as session:
        with pytest.raises(ValueError, match="Cannot transition from approved to approved"):
            await ApprovalGateService(session).approve(approval_id, "alice", author_type="human")
    refused_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_expired_row_gets_the_expiry_error_not_the_review(refused_action) -> None:
    """A mocked session: SQLite hands back a naive ``expires_at``, which cannot be compared with the aware clock."""
    approval = _make_approval()
    approval.context = {"action": _REFUSED}
    approval.expires_at = now_utc() - timedelta(minutes=1)
    with pytest.raises(ValueError, match="expired"):
        await ApprovalGateService(_make_session(scalar_result=approval)).approve(
            approval.id, "alice", author_type="human"
        )
    refused_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_row_awaiting_revision_is_still_reviewed(factory, refused_action) -> None:  # noqa: F811
    """revision_requested -> approved is a legal transition, so skipping the review there would bypass it."""
    approval_id = await _stored(factory, ApprovalStatus.REVISION_REQUESTED.value)
    async with factory() as session:
        with pytest.raises(ValueError, match="refused by the review"):
            await ApprovalGateService(session).approve(approval_id, "alice", author_type="human")
    assert (await _state(factory, approval_id))[0] == ApprovalStatus.REVISION_REQUESTED.value
