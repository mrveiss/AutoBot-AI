# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The reporting hierarchy across people and agents (#15763).

The tests that carry the weight, each covering a way this looks right while
being wrong:

``test_the_walk_stops_at_the_bound`` — the bound is on the walk, not the
organisation. Unbounded, a deep chain hands edit rights (#15765) to everyone
above; the result of a correct walk and an unbounded one are identical until
the chain is three deep.

``test_a_cycle_is_refused_however_deep`` — the write-time check is deliberately
unbounded while the read walk is not. A depth-limited cycle check passes a loop
closed three levels up, and the row it admits then hangs any later unbounded
consumer.

``test_no_ceo_is_reported_not_hidden`` — every company is in this state today.
A chain that silently stops at the last explicit edge is indistinguishable from
a correctly rooted one.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import MembershipRole, RoleHolderType
from llc.models.membership import LLCCompanyMembership
from llc.models.reporting_line import LLCReportingLine
from llc.services.authz import NotAuthorisedError
from llc.services.reporting_line import ChainEnd, Holder, ReportingLineService
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base

_ADMIN = uuid.uuid4()
_OUTSIDER = uuid.uuid4()


def _user(uid: uuid.UUID | None = None) -> Holder:
    return Holder(type=RoleHolderType.USER.value, id=uid or uuid.uuid4())


def _agent(aid: uuid.UUID | None = None) -> Holder:
    return Holder(type=RoleHolderType.AGENT.value, id=aid or uuid.uuid4())


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [LLCCompanyMembership.__table__, LLCReportingLine.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


async def _member(session_factory, company: uuid.UUID, user_id: uuid.UUID, role: str) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=company, user_id=user_id, role=role))
        await session.commit()


async def _admin(session_factory, company: uuid.UUID) -> None:  # noqa: ANN001
    await _member(session_factory, company, _ADMIN, MembershipRole.ADMIN.value)


async def _set(session_factory, company, subject, manager):  # noqa: ANN001
    async with session_factory() as session:
        row = await ReportingLineService().set_line(
            session,
            company_id=company,
            subject=subject,
            manager=manager,
            actor_user_id=_ADMIN,
        )
        await session.commit()
        return row


@pytest.mark.asyncio
async def test_an_agent_can_report_to_a_person_and_back(session_factory):  # noqa: ANN001
    """All four combinations are legitimate; nothing rejects on holder type."""
    company = uuid.uuid4()
    await _admin(session_factory, company)
    person, agent, other_person, other_agent = _user(), _agent(), _user(), _agent()

    await _set(session_factory, company, agent, person)
    await _set(session_factory, company, other_person, other_agent)

    async with session_factory() as session:
        service = ReportingLineService()
        assert await service.explicit_manager(session, company, agent) == person
        assert await service.explicit_manager(session, company, other_person) == other_agent


@pytest.mark.asyncio
async def test_manages_is_derived_from_the_stored_edge(session_factory):  # noqa: ANN001
    """The downward view is a query, never a second store."""
    company = uuid.uuid4()
    await _admin(session_factory, company)
    boss = _user()
    a, b = _user(), _agent()
    await _set(session_factory, company, a, boss)
    await _set(session_factory, company, b, boss)

    async with session_factory() as session:
        reports = await ReportingLineService().direct_reports(session, company, boss)

    assert {(r.type, r.id) for r in reports} == {(a.type, a.id), (b.type, b.id)}


@pytest.mark.asyncio
async def test_the_walk_stops_at_the_bound(session_factory):  # noqa: ANN001
    """Two hops, not the whole chain.

    The fourth person exists precisely so an unbounded walk would reach them.
    Without the bound, everyone above gains edit rights in #15765.
    """
    company = uuid.uuid4()
    await _admin(session_factory, company)
    me, m1, m2, m3 = _user(), _user(), _user(), _user()
    await _set(session_factory, company, me, m1)
    await _set(session_factory, company, m1, m2)
    await _set(session_factory, company, m2, m3)

    async with session_factory() as session:
        chain = await ReportingLineService().chain_up(session, company, me)

    assert [h.id for h in chain.managers] == [m1.id, m2.id]
    assert chain.ended is ChainEnd.DEPTH


@pytest.mark.asyncio
async def test_a_cycle_is_refused_however_deep(session_factory):  # noqa: ANN001
    """The write-time cycle check is unbounded, unlike the read walk.

    The loop closes three hops up — past the read walk's bound — so a check
    that reused that bound would admit the row.
    """
    company = uuid.uuid4()
    await _admin(session_factory, company)
    a, b, c = _user(), _user(), _user()
    await _set(session_factory, company, a, b)
    await _set(session_factory, company, b, c)

    async with session_factory() as session:
        with pytest.raises(ValueError, match="cycle"):
            await ReportingLineService().set_line(
                session, company_id=company, subject=c, manager=a, actor_user_id=_ADMIN
            )


@pytest.mark.asyncio
async def test_a_subject_cannot_report_to_itself(session_factory):  # noqa: ANN001
    company = uuid.uuid4()
    await _admin(session_factory, company)
    me = _user()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="itself"):
            await ReportingLineService().set_line(
                session,
                company_id=company,
                subject=me,
                manager=me,
                actor_user_id=_ADMIN,
            )


@pytest.mark.asyncio
async def test_no_ceo_is_reported_not_hidden(session_factory):  # noqa: ANN001
    """The state every company is in today (#15770).

    A chain that stopped silently would be indistinguishable from a rooted one.
    """
    company = uuid.uuid4()
    await _admin(session_factory, company)
    me = _user()

    async with session_factory() as session:
        chain = await ReportingLineService().chain_up(session, company, me)

    assert chain.managers == ()
    assert chain.ended is ChainEnd.NO_CEO


@pytest.mark.asyncio
async def test_an_owner_terminates_the_walk(session_factory):  # noqa: ANN001
    """An owner's absent line is the top, not a defaulted one.

    Without the exception the rule sends the owner to the CEO, who reports to
    the owner — a two-node loop reached on the very first step.
    """
    company = uuid.uuid4()
    await _admin(session_factory, company)
    owner_id = uuid.uuid4()
    await _member(session_factory, company, owner_id, MembershipRole.OWNER.value)

    async with session_factory() as session:
        chain = await ReportingLineService().chain_up(session, company, _user(owner_id))

    assert chain.managers == ()
    assert chain.ended is ChainEnd.OWNER


@pytest.mark.asyncio
async def test_setting_a_line_replaces_rather_than_accumulates(session_factory):  # noqa: ANN001
    """Line management is single-valued; a second write moves it."""
    company = uuid.uuid4()
    await _admin(session_factory, company)
    me, first, second = _user(), _user(), _user()
    await _set(session_factory, company, me, first)
    await _set(session_factory, company, me, second)

    async with session_factory() as session:
        rows = await session.execute(
            sa.select(sa.func.count()).select_from(LLCReportingLine).where(LLCReportingLine.company_id == company)
        )
        assert rows.scalar_one() == 1
        assert (await ReportingLineService().explicit_manager(session, company, me)) == second


@pytest.mark.asyncio
async def test_clearing_returns_the_subject_to_the_default(session_factory):  # noqa: ANN001
    """Clearing is not orphaning — the default chain takes over."""
    company = uuid.uuid4()
    await _admin(session_factory, company)
    me, boss = _user(), _user()
    await _set(session_factory, company, me, boss)

    async with session_factory() as session:
        removed = await ReportingLineService().clear_line(session, company_id=company, subject=me, actor_user_id=_ADMIN)
        await session.commit()
    assert removed is True

    async with session_factory() as session:
        assert await ReportingLineService().explicit_manager(session, company, me) is None


@pytest.mark.asyncio
async def test_a_non_admin_cannot_set_a_reporting_line(session_factory):  # noqa: ANN001
    """The service floor holds even though the real gate is the route's.

    ``admin.reporting_line.write`` lands at the route (#15765). This asserts the
    service does not assume that gate ran.
    """
    company = uuid.uuid4()
    await _admin(session_factory, company)

    async with session_factory() as session:
        with pytest.raises(NotAuthorisedError):
            await ReportingLineService().set_line(
                session,
                company_id=company,
                subject=_user(),
                manager=_user(),
                actor_user_id=_OUTSIDER,
            )


@pytest.mark.asyncio
async def test_lines_do_not_cross_companies(session_factory):  # noqa: ANN001
    company, other = uuid.uuid4(), uuid.uuid4()
    await _admin(session_factory, company)
    await _admin(session_factory, other)
    me, boss = _user(), _user()
    await _set(session_factory, company, me, boss)

    async with session_factory() as session:
        assert await ReportingLineService().explicit_manager(session, other, me) is None
