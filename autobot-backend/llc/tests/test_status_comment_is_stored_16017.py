# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The comment on a status transition reaches the database (#16017).

`StatusUpdate.comment` was declared and `body.comment` appeared nowhere in
`agent_api.py`. An agent explaining a transition got a `200` and the explanation
was discarded on every call.

**This asserts the effect, not the shape.** The PR's other tests read the
handler's source with `ast`, and all of them pass if `add_comment` is rewritten
to `return None` — a test of the fix's shape rather than of the failure it
fixed. This one fails, because it looks for the row.

That distinction has bitten this exact route before: its own docstring records
that it once echoed the requested status back with `{"updated": True}` without
performing the transition, so any test reading the response passed against code
that did nothing. `test_cost_accrual_15859_15860.py` carries the same warning
about the sibling route.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem, LLCWorkItemComment
from llc.tests import _e2e_harness as harness

pytestmark = pytest.mark.asyncio

_COMPANY = uuid.uuid4()
_AGENT = "agent-16017"


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def factory(engine):  # noqa: ANN001, ANN201
    return async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )


async def _seed_item(factory) -> uuid.UUID:  # noqa: ANN001
    item_id = uuid.uuid4()
    async with factory() as session:
        session.add(
            LLCWorkItem(
                id=item_id,
                company_id=_COMPANY,
                type=WorkItemType.TASK,
                identifier=f"T-{item_id.hex[:8]}",
                title="a work item",
                status=WorkItemStatus.READY,
                priority=WorkItemPriority.MEDIUM,
                labels=[],
                linked_pr_urls=[],
                requires_approval_before=[],
                backlog_position=0,
                needs_triage=False,
            )
        )
        await session.commit()
    return item_id


async def _transition(factory, item_id: uuid.UUID, comment: str | None):  # noqa: ANN001, ANN202
    """Call the handler directly. The FastAPI plumbing is patched, not the subject."""
    from llc.api.agent_api import StatusUpdate, update_work_item_status

    author = uuid.uuid4()
    with (
        patch("llc.api.agent_api.agent_context", return_value=(_AGENT, str(_COMPANY))),
        patch("llc.api.agent_api.agent_node_uuid", return_value=author),
        patch("user_management.database.get_async_session_factory", return_value=factory),
    ):
        return await update_work_item_status(
            item_id,
            StatusUpdate(status=WorkItemStatus.IN_PROGRESS.value, comment=comment),
            object(),  # type: ignore[arg-type]  # agent_context is patched; the request is unused
        )


async def _comments(factory, item_id: uuid.UUID) -> list[LLCWorkItemComment]:  # noqa: ANN001
    async with factory() as session:
        rows = await session.execute(select(LLCWorkItemComment).where(LLCWorkItemComment.work_item_id == item_id))
        return list(rows.scalars())


async def test_the_comment_is_written_to_the_database(factory):  # noqa: ANN001
    """The regression, asserted on the EFFECT.

    Rewriting the handler to skip `add_comment` leaves every AST assertion in
    `repo_tests/status_comment_is_stored_16017_test.py` passing and fails this.
    """
    item_id = await _seed_item(factory)
    await _transition(factory, item_id, "blocked on the upstream fix")

    stored = await _comments(factory, item_id)
    assert len(stored) == 1, (
        "the transition stored no comment — an agent's explanation was accepted "
        "and discarded, which is exactly #16017"
    )
    assert stored[0].body == "blocked on the upstream fix"


async def test_no_comment_stores_no_row(factory):  # noqa: ANN001
    """The contrast.

    A handler that wrote a row unconditionally would pass the test above while
    filling the table with empty comments on every status change — and every
    transition would then carry a reason that nobody wrote.
    """
    item_id = await _seed_item(factory)
    result = await _transition(factory, item_id, None)

    assert await _comments(factory, item_id) == []
    assert result["comment_id"] is None


async def test_a_whitespace_only_comment_is_not_a_comment(factory):  # noqa: ANN001
    """`"   "` is the shape a UI sends when the field was focused and left empty."""
    item_id = await _seed_item(factory)
    await _transition(factory, item_id, "   ")
    assert await _comments(factory, item_id) == []


async def test_a_failed_commit_leaves_no_comment_behind(factory):  # noqa: ANN001
    """The claim the code comment makes, which nothing tested (review of #16017).

    `add_comment` sits before `session.commit()` because a comment committed
    separately could outlive a transition that failed — a recorded reason for
    something that did not happen. Every other test here takes the happy path,
    so moving the write after the commit leaves them all green.

    This forces the commit to fail and asserts the comment did not survive it.
    Both writes ride one transaction; if they ever stop doing so, this is what
    notices.
    """
    from sqlalchemy.exc import OperationalError

    item_id = await _seed_item(factory)

    class _FailingCommitSession:
        """Delegates everything to the real session but refuses to commit."""

        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        async def commit(self):
            raise OperationalError("forced", None, Exception("commit refused"))

    real = factory()

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return _FailingCommitSession(await real.__aenter__())

        async def __aexit__(self, *exc):
            return await real.__aexit__(*exc)

    with pytest.raises(OperationalError):
        await _transition(_Factory(), item_id, "this reason must not survive")

    # Read through a FRESH session: the failed transaction must have taken the
    # comment with it.
    assert await _comments(factory, item_id) == [], (
        "a comment survived a transaction that never committed — the transition "
        "did not happen and its reason did (#16017)"
    )
