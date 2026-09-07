# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The three remaining agent_api stubs now do their work (#15905).

`GET /work-items/next`, `POST /comments` and `POST /heartbeat/report` returned
an explicit negative and no effect. #15859 made them *honest*; honest and
unimplemented is still unimplemented.

**Every assertion here is on the effect, not the response.** The response is
what the stubs were already producing correctly -- a route that returns
``{"recorded": True}`` and writes nothing is exactly the defect #15859 fixed on
two sibling routes, and a test reading the response cannot tell the two apart.
So: the item is assigned, the comment is readable, the run row changed.

The handlers are called with a mocked `Request` and a REAL session factory, so
the body runs end to end. That is the precedent from
`test_cost_accrual_15859_15860.py`, and it exists because service-level tests
there passed against handlers that would have raised `NameError` on every
request -- no test entered a handler, so nothing reported it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import LLCRunStatus, WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem, LLCWorkItemComment
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


def _request(agent_id: str, company_id: str):
    from unittest.mock import MagicMock

    req = MagicMock()
    req.state.agent_id = agent_id
    req.state.company_id = company_id
    return req


def _factory_yielding(session: AsyncSession):
    """Two levels of indirection, matching the production shape (see #15859)."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _cm():
        yield session

    def _get_factory():
        return lambda: _cm()

    return _get_factory


async def _seed_agent_node(session: AsyncSession, company_id: str, agent_id: str) -> uuid.UUID:
    """The agent's `agent_org_nodes` row, which is what `assignee_agent_id` points at.

    `_agent_context` yields a company-scoped slug; `checkout` writes a UUID. The
    route resolves one to the other, so without this row the route 404s — which
    is correct behaviour, and the reason this helper exists rather than the route
    being loosened.

    Through the ORM, like every other seed here. Raw `INSERT` was tried three
    times in this file and failed three times on mixin-managed timestamp columns
    a hand-written column list does not know about. The model is what production
    inserts, so the fixture cannot disagree with it.
    """
    from models.agent_org import AgentOrgNode

    node = AgentOrgNode(
        id=uuid.uuid4(),
        agent_id=agent_id,
        name=agent_id,
        org_role="ic",
        company_id=uuid.UUID(company_id),
    )
    session.add(node)
    await session.commit()
    return node.id


async def _seed_item(
    session: AsyncSession,
    company_id: str,
    *,
    title: str = "an item",
    status: str = WorkItemStatus.READY.value,
    priority: WorkItemPriority = WorkItemPriority.MEDIUM,
    position: int | None = None,
) -> LLCWorkItem:
    """Seed through `WorkItemService.create`, not by hand-building the row.

    A hand-built `LLCWorkItem` is a shape no producer emits: it took two rounds
    of NOT NULL failures (`type`, then `labels`) to discover that, and the third
    would have been a column whose default happens to be valid but wrong. The
    service is what production uses, so the fixture and the code under test
    disagree about nothing.

    `status` and `backlog_position` are set afterwards because `create` does not
    take them -- a new item is `backlog` at position 0 by design, and this test
    needs `ready` items in a chosen order.
    """
    from autobot_shared.singleton_factory import lazy_singleton
    from llc.services.work_item_service import WorkItemService

    item = await lazy_singleton(WorkItemService)().create(
        session,
        company_id=company_id,
        type=WorkItemType.TASK,
        title=title,
        priority=priority,
    )
    item.status = status
    if position is not None:
        item.backlog_position = position
    await session.commit()
    return item


# ---------------------------------------------------------------------------
# GET /work-items/next
# ---------------------------------------------------------------------------


async def test_the_next_route_actually_checks_the_item_out(session):  # noqa: ANN001
    """The effect: the item is claimed, not merely described in the response."""
    from unittest.mock import patch

    from llc.api import agent_api

    company = str(uuid.uuid4())
    item = await _seed_item(session, company, title="claim me")

    await _seed_agent_node(session, company, "agent-next")

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        result = await agent_api.get_next_work_item(_request("agent-next", company))

    assert result["checked_out"] is True
    assert result["work_item"]["id"] == str(item.id)

    await session.refresh(item)
    assert item.checkout_run_id is not None, "the route reported a checkout and the item was not claimed"
    assert item.status == WorkItemStatus.IN_PROGRESS.value


async def test_the_next_route_reports_no_work_without_claiming_anything(session):  # noqa: ANN001
    """`None` is an ordinary answer. The contrast case for the test above.

    Without this, a handler that returned `checked_out: True` unconditionally --
    or one that claimed an ineligible item -- passes everything else here.
    """
    from unittest.mock import patch

    from llc.api import agent_api

    company = str(uuid.uuid4())
    backlog = await _seed_item(session, company, status=WorkItemStatus.BACKLOG.value)

    await _seed_agent_node(session, company, "agent-none")

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        result = await agent_api.get_next_work_item(_request("agent-none", company))

    assert result["checked_out"] is False
    assert result["work_item"] is None

    await session.refresh(backlog)
    assert backlog.checkout_run_id is None, "a backlog item was claimed; only `ready` items are eligible"


async def test_the_next_route_will_not_reach_into_another_company(session):  # noqa: ANN001
    """Company scoping, asserted by seeding an eligible item the caller must not get."""
    from unittest.mock import patch

    from llc.api import agent_api

    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    other = await _seed_item(session, theirs, title="not yours")

    await _seed_agent_node(session, mine, "agent-x")

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        result = await agent_api.get_next_work_item(_request("agent-x", mine))

    assert result["checked_out"] is False
    await session.refresh(other)
    assert other.checkout_run_id is None, "an agent claimed another company's work item"


async def test_the_next_route_honours_the_backlog_ordering(session):  # noqa: ANN001
    """ "Next" must be the backlog's next, not an arbitrary row.

    The point of reusing `BacklogService`'s ordering is that the agent gets what
    a human sees at the top of the same list. Seeding in the wrong order is what
    makes this assert the ordering rather than the insertion.
    """
    from unittest.mock import patch

    from llc.api import agent_api

    company = str(uuid.uuid4())
    await _seed_item(session, company, title="later", position=5)
    first = await _seed_item(session, company, title="first", position=1)

    await _seed_agent_node(session, company, "agent-order")

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        result = await agent_api.get_next_work_item(_request("agent-order", company))

    assert result["work_item"]["title"] == "first", "the route ignored backlog_position"
    assert result["work_item"]["id"] == str(first.id)


# ---------------------------------------------------------------------------
# POST /comments
# ---------------------------------------------------------------------------


async def test_the_comment_route_stores_a_readable_comment(session):  # noqa: ANN001
    """The effect: the comment is in the table, with the body that was sent."""
    from unittest.mock import patch

    from llc.api import agent_api

    company = str(uuid.uuid4())
    item = await _seed_item(session, company)

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        result = await agent_api.post_comment(
            agent_api.CommentBody(work_item_id=str(item.id), body="the agent said this"),
            _request("agent-c", company),
        )

    assert result["recorded"] is True
    stored = (
        (await session.execute(select(LLCWorkItemComment).where(LLCWorkItemComment.work_item_id == item.id)))
        .scalars()
        .all()
    )
    assert len(stored) == 1, "the route reported the comment recorded and nothing was stored"
    assert stored[0].body == "the agent said this"
    assert str(stored[0].id) == result["comment_id"]


async def test_the_comment_route_refuses_another_companys_item(session):  # noqa: ANN001
    """404, and — the part that matters — no row written.

    `add_comment` writes `company_id` from its argument without reading the
    item, so an unchecked route would store the comment under the CALLER's
    company while attached to another company's item: readable by neither.
    """
    from unittest.mock import patch

    from fastapi import HTTPException

    from llc.api import agent_api

    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    item = await _seed_item(session, theirs)

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        with pytest.raises(HTTPException) as exc:
            await agent_api.post_comment(
                agent_api.CommentBody(work_item_id=str(item.id), body="not mine to comment on"),
                _request("agent-c", mine),
            )

    assert exc.value.status_code == 404
    rows = (
        (await session.execute(select(LLCWorkItemComment).where(LLCWorkItemComment.work_item_id == item.id)))
        .scalars()
        .all()
    )
    assert rows == [], "a comment was stored on another company's work item"


# ---------------------------------------------------------------------------
# POST /heartbeat/report
# ---------------------------------------------------------------------------


async def _seed_run(session: AsyncSession, company_id: str, agent_id: str) -> uuid.UUID:
    """Seed through the model, for the reason `_seed_item` gives.

    Raw SQL here cost two rounds of NOT NULL failures (`created_at`, then
    `updated_at`) — timestamp columns a mixin fills in and a hand-written INSERT
    does not.
    """
    from llc.models.heartbeat_run import LLCHeartbeatRun

    run = LLCHeartbeatRun(
        id=uuid.uuid4(),
        company_id=uuid.UUID(company_id),
        agent_id=agent_id,
        invocation_source="schedule",
        status=LLCRunStatus.RUNNING.value,
        started_at=datetime.now(tz=timezone.utc),
    )
    session.add(run)
    await session.commit()
    return run.id


async def _run_status(session: AsyncSession, run_id: uuid.UUID) -> tuple:
    """Read back through the ORM, for the same reason the route writes through it.

    A raw `WHERE id = :id` with a dashed UUID string does not match what SQLite
    stores (32 hex, no dashes), so this helper reported `None` for a row that
    had been updated correctly — an assertion failing on the harness while the
    code under test was right.
    """
    from llc.models.heartbeat_run import LLCHeartbeatRun

    row = (await session.execute(select(LLCHeartbeatRun).where(LLCHeartbeatRun.id == run_id))).scalar_one_or_none()
    if row is None:
        return (None, None)
    await session.refresh(row)
    return (row.status, row.finished_at)


async def test_the_heartbeat_route_updates_the_existing_run(session):  # noqa: ANN001
    """The effect: the run's own row changed. No second row.

    Inserting here instead of updating would satisfy any response-shaped
    assertion while making every count of runs wrong.
    """
    from unittest.mock import patch

    from llc.api import agent_api

    company, agent = str(uuid.uuid4()), "agent-hb"
    run_id = await _seed_run(session, company, agent)

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        result = await agent_api.report_heartbeat(
            agent_api.HeartbeatReport(run_id=str(run_id), status=LLCRunStatus.COMPLETED.value),
            _request(agent, company),
        )

    assert result["recorded"] is True
    status, finished_at = await _run_status(session, run_id)
    assert status == LLCRunStatus.COMPLETED.value, "the route reported the run recorded and the row did not change"
    assert finished_at is not None

    from sqlalchemy import func

    from llc.models.heartbeat_run import LLCHeartbeatRun

    total = (
        await session.execute(
            select(func.count()).select_from(LLCHeartbeatRun).where(LLCHeartbeatRun.company_id == uuid.UUID(company))
        )
    ).scalar_one()
    assert total == 1, "reporting a heartbeat inserted a second run row instead of updating the first"


async def test_the_heartbeat_route_404s_on_another_companys_run(session):  # noqa: ANN001
    """A `run_id` is a UUID, and guessing or replaying one must not close it out."""
    from unittest.mock import patch

    from fastapi import HTTPException

    from llc.api import agent_api

    mine, theirs, agent = str(uuid.uuid4()), str(uuid.uuid4()), "agent-hb"
    run_id = await _seed_run(session, theirs, agent)

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        with pytest.raises(HTTPException) as exc:
            await agent_api.report_heartbeat(
                agent_api.HeartbeatReport(run_id=str(run_id), status=LLCRunStatus.COMPLETED.value),
                _request(agent, mine),
            )

    assert exc.value.status_code == 404
    status, _ = await _run_status(session, run_id)
    assert status == LLCRunStatus.RUNNING.value, "another company's run was closed out"


async def test_the_heartbeat_route_rejects_an_unknown_status(session):  # noqa: ANN001
    """422 before any write, so a typo cannot leave a run in a status that is
    not in the enum."""
    from unittest.mock import patch

    from fastapi import HTTPException

    from llc.api import agent_api

    company, agent = str(uuid.uuid4()), "agent-hb"
    run_id = await _seed_run(session, company, agent)

    with patch("user_management.database.get_async_session_factory", new=_factory_yielding(session)):
        with pytest.raises(HTTPException) as exc:
            await agent_api.report_heartbeat(
                agent_api.HeartbeatReport(run_id=str(run_id), status="finished-ish"),
                _request(agent, company),
            )

    assert exc.value.status_code == 422
    status, _ = await _run_status(session, run_id)
    assert status == LLCRunStatus.RUNNING.value


async def test_no_route_still_announces_itself_as_a_stub(session):  # noqa: ANN001
    """#15905's last criterion, checked against the source rather than a response.

    The negative markers #15859 added were to stay *until the effect was real*.
    They are now gone, and this is what stops one being left behind on a route
    that does work -- a response saying "not implemented" from a handler that
    writes is the #15859 defect with the sign flipped.
    """
    import inspect

    from llc.api import agent_api

    source = inspect.getsource(agent_api)
    assert "Not implemented (stub)" not in source, "a stub marker remains on a route that now performs its work"


async def test_a_non_uuid_company_in_the_agent_context_is_a_401_not_a_500(session):  # noqa: ANN001
    """The other element of the same tuple (#15905).

    This PR's whole subject is that `_agent_context` yields values the code then
    feeds to `uuid.UUID()` unguarded. It fixed that for `agent_id` and left
    `company_id`, which is *less* constrained: `LLCApiKey.company_id` is
    `String(255)`, `_agent_context` checked truthiness only, and the auth
    middleware's own test asserts `company_id == "co-1"`.

    So a malformed company reached `uuid.UUID()` and raised `ValueError` — a 500
    for something that is not a server fault, which is the exact sentence in the
    comment on `get_next_work_item`.
    """
    from fastapi import HTTPException

    from llc.api._common import agent_context

    with pytest.raises(HTTPException) as exc:
        agent_context(_request("agent-bad-co", "co-1"))

    assert exc.value.status_code == 401
    assert "malformed company" in str(exc.value.detail)


async def test_a_well_formed_company_still_passes(session):  # noqa: ANN001
    """The contrast case. Without it, a `_agent_context` that rejected every
    company would satisfy the assertion above and break every other route."""
    from llc.api._common import agent_context

    company = str(uuid.uuid4())
    agent_id, returned = agent_context(_request("agent-ok", company))

    assert (agent_id, returned) == ("agent-ok", company)


async def test_a_malformed_work_item_id_is_422_on_both_routes(session):  # noqa: ANN001
    """The third instance of this PR's own class, on client-supplied input.

    `WorkItemService.get` converts with `uuid.UUID(str(...))` and no guard, so a
    malformed body field was a 500 on both `post_comment` and `report_heartbeat`
    — while `run_id`, two lines away in the same handler, had an explicit 422.
    The guard was on the input that looked dangerous rather than the one that
    was unchecked.

    Both routes asserted together because they share `_assert_item_in_company`:
    fixing one and leaving the other is the shape this PR keeps finding.
    """
    from fastapi import HTTPException

    from llc.api import agent_api

    company, agent = str(uuid.uuid4()), "agent-badid"
    run_id = await _seed_run(session, company, agent)

    with pytest.raises(HTTPException) as via_comment:
        await agent_api.post_comment(
            agent_api.CommentBody(work_item_id="not-a-uuid", body="x"),
            _request(agent, company),
        )
    assert via_comment.value.status_code == 422

    with pytest.raises(HTTPException) as via_heartbeat:
        await agent_api.report_heartbeat(
            agent_api.HeartbeatReport(
                run_id=str(run_id), status=LLCRunStatus.COMPLETED.value, work_item_id="not-a-uuid"
            ),
            _request(agent, company),
        )
    assert via_heartbeat.value.status_code == 422
