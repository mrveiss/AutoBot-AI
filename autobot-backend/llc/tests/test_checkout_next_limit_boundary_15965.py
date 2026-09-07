# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`checkout_next` must not report "no work" while eligible work exists (#15965).

The original defect: the assignee predicate was applied in Python **after** the
`LIMIT`. Ten items assigned to another agent, ordered ahead, filled the candidate
window; the filter then removed all ten and the function returned ``None`` while
an eligible item sat just below them.

**Why the existing tests could not catch it, which is the point of this file.**
`test_checkout_excludes_user_assigned_15964.py` asserts the *predicate's shape*,
and `test_agent_stub_routes_15905.py` asserts route behaviour and ordering.
Neither builds a population larger than `CHECKOUT_CANDIDATES`, and that is the
only condition under which the defect appears. A test of the fix's shape is not
a test of the failure it fixed.

**The decoy count is read from `CHECKOUT_CANDIDATES`, never written as 10.** That
is the whole of criterion 5. With a hard-coded ten, raising the constant to 100
would make this file pass while the bug returned at the new boundary — the fix
and the mask are indistinguishable to a test that does not move with the
constant. Reading it means the window is always exactly full, whatever it is.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import WorkItemStatus, WorkItemType
from llc.services.work_item_queue import CHECKOUT_CANDIDATES, checkout_next
from llc.services.work_item_service import WorkItemService
from llc.tests import _e2e_harness as harness

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:  # noqa: ANN001
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        yield s


async def _ready_item(session: AsyncSession, company: str, title: str, *, position: int, assignee: str | None):
    """Seed through the service, so the fixture cannot disagree with production."""
    svc = WorkItemService()
    item = await svc.create(session, company_id=company, type=WorkItemType.TASK, title=title)
    item.status = WorkItemStatus.READY.value
    # Explicit ordering: `backlog_order()` sorts on `backlog_position` first, so
    # this is what puts the decoys AHEAD of the eligible item rather than relying
    # on creation timestamps, which collide at sqlite's resolution.
    item.backlog_position = position
    if assignee is not None:
        item.assignee_agent_id = uuid.UUID(assignee)
    await session.commit()
    return item


async def test_an_eligible_item_below_a_full_window_is_still_returned(session):  # noqa: ANN001
    """The defect itself: a full candidate window of another agent's items.

    Seeds exactly `CHECKOUT_CANDIDATES` decoys ordered ahead of one unassigned
    item. Before the fix the LIMIT consumed the decoys, the Python filter removed
    them all, and this returned `None`.
    """
    company, mine, theirs = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    for i in range(CHECKOUT_CANDIDATES):
        await _ready_item(session, company, f"theirs {i}", position=i, assignee=theirs)
    eligible = await _ready_item(session, company, "mine", position=CHECKOUT_CANDIDATES, assignee=None)

    claimed = await checkout_next(session, WorkItemService(), agent_id=mine, company_id=company)

    assert claimed is not None, (
        f"{CHECKOUT_CANDIDATES} items assigned to another agent filled the candidate "
        "window and the eligible item below them was reported as no work at all"
    )
    assert str(claimed.id) == str(eligible.id)


async def test_the_window_is_full_at_exactly_checkout_candidates(session):  # noqa: ANN001
    """Criterion 5: the boundary is pinned to the constant, not to the number 10.

    This is the assertion that stops the constant being raised INSTEAD of the
    predicate being fixed. It states the property a reader must not break: the
    test above seeds exactly as many decoys as the window holds, so the window is
    full whatever the constant becomes.
    """
    assert CHECKOUT_CANDIDATES >= 1, "a window of zero would make the test above vacuous"
    company, mine, theirs = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    for i in range(CHECKOUT_CANDIDATES):
        await _ready_item(session, company, f"theirs {i}", position=i, assignee=theirs)

    # One MORE than the window, so nothing eligible can be reached by luck of the
    # limit: every candidate slot is occupied by another agent's item.
    await _ready_item(session, company, "theirs overflow", position=CHECKOUT_CANDIDATES, assignee=theirs)
    claimed = await checkout_next(session, WorkItemService(), agent_id=mine, company_id=company)
    assert claimed is None, "no item is eligible here, so `None` is the correct answer"


async def test_a_window_of_only_other_agents_items_does_not_claim_one(session):  # noqa: ANN001
    """Contrast: the fix must not make `checkout_next` claim what it may not.

    Without this, "return something below the window" is satisfied by returning
    another agent's item, which passes the first test and is a far worse bug than
    the one being fixed.
    """
    company, mine, theirs = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    for i in range(CHECKOUT_CANDIDATES + 5):
        await _ready_item(session, company, f"theirs {i}", position=i, assignee=theirs)

    assert await checkout_next(session, WorkItemService(), agent_id=mine, company_id=company) is None


async def test_an_item_already_assigned_to_this_agent_is_claimable(session):  # noqa: ANN001
    """The other branch of the predicate, below a full window of foreign items."""
    company, mine, theirs = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    for i in range(CHECKOUT_CANDIDATES):
        await _ready_item(session, company, f"theirs {i}", position=i, assignee=theirs)
    ours = await _ready_item(session, company, "already mine", position=CHECKOUT_CANDIDATES, assignee=mine)

    claimed = await checkout_next(session, WorkItemService(), agent_id=mine, company_id=company)
    assert claimed is not None and str(claimed.id) == str(ours.id)
