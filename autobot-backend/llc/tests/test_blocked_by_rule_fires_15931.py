# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GH#8252's blocked-by rule must fire without being handed its collaborator (#15931).

The rule refuses `BLOCKED -> IN_PROGRESS` while unresolved `blocked_by`
relations remain. It had never fired: it was gated on `relation_svc is not None
and company_id is not None`, and **nothing outside `test_work_item_relations.py`
ever passed `relation_svc`**. A blocked item moved to `in_progress` from the
work-item API and from a board card drag.

**Why green CI did not catch it, and this is the point of this file.** The
existing tests pass `relation_svc` explicitly. They prove the rule works *when
invoked* and say nothing about whether anything invokes it — a test that
supplies a collaborator no caller supplies is testing a configuration that does
not occur. So the assertions here call `transition_status` **the way production
calls it**: no `relation_svc`, and in one case no `company_id` either.

Same class as #15914's dead constructors — correct, tested, unreachable.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import WorkItemRelationType, WorkItemStatus, WorkItemType
from llc.services.work_item_service import InvalidTransition, WorkItemService
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


async def _item(session: AsyncSession, company: str, *, status: WorkItemStatus, title: str):
    """Seed through the service, so the fixture cannot disagree with production."""
    svc = WorkItemService()
    item = await svc.create(session, company_id=company, type=WorkItemType.TASK, title=title)
    item.status = status.value
    await session.commit()
    return item


async def _block(session: AsyncSession, company: str, blocker, blocked) -> None:
    from llc.services.work_item_relations import WorkItemRelationService

    await WorkItemRelationService().add(
        session,
        company_id=company,
        source_id=str(blocker.id),
        target_id=str(blocked.id),
        relation_type=WorkItemRelationType.BLOCKED_BY,
    )
    await session.commit()


async def test_the_rule_fires_without_an_injected_relation_service(session):  # noqa: ANN001
    """Called as production calls it: no `relation_svc`.

    Before #15931 this passed — the transition succeeded — because the missing
    collaborator disabled the check rather than failing.
    """
    company = str(uuid.uuid4())
    blocker = await _item(session, company, status=WorkItemStatus.READY, title="blocker")
    blocked = await _item(session, company, status=WorkItemStatus.BLOCKED, title="blocked")
    await _block(session, company, blocker, blocked)

    with pytest.raises(InvalidTransition, match="unresolved blocked_by"):
        await WorkItemService().transition_status(
            session, str(blocked.id), WorkItemStatus.IN_PROGRESS, company_id=company
        )

    await session.refresh(blocked)
    assert blocked.status == WorkItemStatus.BLOCKED.value, "the refusal did not prevent the write"


async def test_the_rule_fires_without_company_id_either(session):  # noqa: ANN001
    """The second gate. `work_items.py:644` and `board.py:329` pass neither.

    `company_id` was never needed: the company is on the row already loaded, and
    the old `cid = company_id or str(item.company_id)` fallback proves the author
    knew — but the guard above it made that line unreachable.
    """
    company = str(uuid.uuid4())
    blocker = await _item(session, company, status=WorkItemStatus.READY, title="blocker-2")
    blocked = await _item(session, company, status=WorkItemStatus.BLOCKED, title="blocked-2")
    await _block(session, company, blocker, blocked)

    with pytest.raises(InvalidTransition, match="unresolved blocked_by"):
        await WorkItemService().transition_status(session, str(blocked.id), WorkItemStatus.IN_PROGRESS)


async def test_a_resolved_blocker_does_not_refuse(session):  # noqa: ANN001
    """The contrast case, and the one that stops the fix over-refusing.

    Without it, a rule that raised on every BLOCKED -> IN_PROGRESS satisfies
    both assertions above while making the status unreachable.
    """
    company = str(uuid.uuid4())
    blocker = await _item(session, company, status=WorkItemStatus.DONE, title="finished blocker")
    blocked = await _item(session, company, status=WorkItemStatus.BLOCKED, title="unblocked")
    await _block(session, company, blocker, blocked)

    item = await WorkItemService().transition_status(session, str(blocked.id), WorkItemStatus.IN_PROGRESS)

    assert item.status == WorkItemStatus.IN_PROGRESS


async def test_an_unblocked_item_still_transitions(session):  # noqa: ANN001
    """The other contrast: no relations at all must not be read as blocked."""
    company = str(uuid.uuid4())
    blocked = await _item(session, company, status=WorkItemStatus.BLOCKED, title="no blockers")

    item = await WorkItemService().transition_status(session, str(blocked.id), WorkItemStatus.IN_PROGRESS)

    assert item.status == WorkItemStatus.IN_PROGRESS


async def test_another_companys_blocker_does_not_refuse(session):  # noqa: ANN001
    """The company scope survives the ungating.

    `has_unresolved_blockers` filters `LLCWorkItemRelation.company_id`, and the
    company now comes from the loaded row rather than the argument. This asserts
    that substitution kept the boundary rather than widening it.
    """
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    blocker = await _item(session, theirs, status=WorkItemStatus.READY, title="their blocker")
    blocked = await _item(session, mine, status=WorkItemStatus.BLOCKED, title="my item")
    await _block(session, theirs, blocker, blocked)

    item = await WorkItemService().transition_status(session, str(blocked.id), WorkItemStatus.IN_PROGRESS)

    assert item.status == WorkItemStatus.IN_PROGRESS, "another company's relation refused this company's transition"
