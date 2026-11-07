# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``resolve_successor`` names who inherits from a removed person, step by step (#20029).

Each test builds a company where a higher step AND a lower step both have an answer, so a wrong order shows as
the wrong id; the tie-break tests make the two candidates identical in tenure so only the id decides.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.company_ceo import LLCCompanyCEO
from llc.models.enums import MembershipRole, RoleHolderType
from llc.models.membership import LLCCompanyMembership
from llc.models.reporting_line import LLCReportingLine
from llc.models.role_assignment import LLCRoleAssignment
from llc.services.successor import pick_longest_tenure, resolve_successor
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode
from user_management.models.base import Base
from user_management.models.user import User

T0 = datetime(2026, 1, 1)
USER = RoleHolderType.USER.value
AGENT = RoleHolderType.AGENT.value


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    tables = [
        User.__table__,
        LLCCompanyMembership.__table__,
        LLCReportingLine.__table__,
        LLCCompanyCEO.__table__,
        LLCRoleAssignment.__table__,
        AgentOrgNode.__table__,
    ]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


class World:
    """One company plus helpers that seed people into it."""

    def __init__(self, factory) -> None:  # noqa: ANN001
        self.factory = factory
        self.company = uuid.uuid4()

    async def person(self, *, active=True, deleted=False, role=MembershipRole.MEMBER, joined=0, uid=None, row=True):
        """A company member; ``row=False`` leaves a membership with no user row (a hard delete)."""
        uid = uid or uuid.uuid4()
        async with self.factory() as s:
            if row:
                await s.execute(
                    sa.insert(User.__table__).values(
                        id=uid,
                        email=f"{uid}@x.test",
                        username=str(uid),
                        is_active=active,
                        is_verified=True,
                        mfa_enabled=False,
                        is_platform_admin=False,
                        preferences={},
                        deleted_at=T0 if deleted else None,
                    )
                )
            s.add(
                LLCCompanyMembership(
                    id=uuid.uuid4(),
                    company_id=self.company,
                    user_id=uid,
                    role=role.value,
                    created_at=T0 + timedelta(days=joined),
                )
            )
            await s.commit()
        return uid

    async def manager(self, subject, manager_type, manager_id):  # noqa: ANN001
        async with self.factory() as s:
            s.add(
                LLCReportingLine(
                    id=uuid.uuid4(),
                    company_id=self.company,
                    subject_type=USER,
                    subject_user_id=subject,
                    manager_type=manager_type,
                    manager_user_id=manager_id if manager_type == USER else None,
                    manager_agent_id=manager_id if manager_type == AGENT else None,
                )
            )
            await s.commit()

    async def ceo(self, holder_type, holder_id):  # noqa: ANN001
        async with self.factory() as s:
            s.add(
                LLCCompanyCEO(
                    id=uuid.uuid4(),
                    company_id=self.company,
                    holder_type=holder_type,
                    holder_user_id=holder_id if holder_type == USER else None,
                    holder_agent_id=holder_id if holder_type == AGENT else None,
                )
            )
            await s.commit()

    async def agent(self):
        node = uuid.uuid4()
        async with self.factory() as s:
            s.add(AgentOrgNode(id=node, agent_id=str(uuid.uuid4()), name="A", org_role="ceo", company_id=self.company))
            await s.commit()
        return node

    async def role(self, holder, role_id, *, since=0, ended=False):  # noqa: ANN001
        async with self.factory() as s:
            s.add(
                LLCRoleAssignment(
                    id=uuid.uuid4(),
                    company_id=self.company,
                    role_id=role_id,
                    holder_type=USER,
                    holder_user_id=holder,
                    started_at=T0 + timedelta(days=since),
                    ended_at=T0 + timedelta(days=99) if ended else None,
                )
            )
            await s.commit()

    async def resolve(self, user):  # noqa: ANN001
        async with self.factory() as s:
            return await resolve_successor(s, self.company, user)


@pytest_asyncio.fixture
async def world(factory) -> World:  # noqa: ANN001
    return World(factory)


@pytest.mark.asyncio
async def test_the_explicit_human_manager_wins_over_every_lower_step(world):
    leaving, manager, ceo, owner, peer = [await world.person() for _ in range(5)]
    await world.manager(leaving, USER, manager)
    await world.ceo(USER, ceo)
    owner = await world.person(role=MembershipRole.OWNER)
    role = uuid.uuid4()
    await world.role(leaving, role)
    await world.role(peer, role)
    assert await world.resolve(leaving) == manager


@pytest.mark.asyncio
async def test_an_agent_manager_falls_to_the_human_ceo_not_up_the_agents_chain(world):
    leaving = await world.person()
    ceo = await world.person()
    above_agent = await world.person()
    agent = await world.agent()
    await world.manager(leaving, AGENT, agent)
    await world.manager(above_agent, USER, above_agent)  # irrelevant row: the agent's chain is not walked
    await world.ceo(USER, ceo)
    assert await world.resolve(leaving) == ceo


@pytest.mark.asyncio
async def test_an_inactive_manager_is_skipped_for_the_ceo(world):
    leaving, ceo = await world.person(), await world.person()
    gone = await world.person(active=False)
    await world.manager(leaving, USER, gone)
    await world.ceo(USER, ceo)
    assert await world.resolve(leaving) == ceo


@pytest.mark.asyncio
async def test_an_agent_ceo_is_skipped_for_the_owner(world):
    leaving = await world.person()
    owner = await world.person(role=MembershipRole.OWNER)
    await world.ceo(AGENT, await world.agent())
    assert await world.resolve(leaving) == owner


@pytest.mark.asyncio
async def test_the_ceo_wins_over_owner_and_role(world):
    leaving, ceo, peer = await world.person(), await world.person(), await world.person()
    await world.person(role=MembershipRole.OWNER)
    role = uuid.uuid4()
    await world.role(leaving, role)
    await world.role(peer, role)
    await world.ceo(USER, ceo)
    assert await world.resolve(leaving) == ceo


@pytest.mark.asyncio
async def test_the_owner_with_the_longest_tenure_wins(world):
    leaving = await world.person()
    await world.person(role=MembershipRole.OWNER, joined=5)
    senior = await world.person(role=MembershipRole.OWNER, joined=1)
    assert await world.resolve(leaving) == senior


@pytest.mark.asyncio
async def test_owner_tenure_tie_goes_to_the_lowest_id(world):
    leaving = await world.person()
    low, high = sorted([uuid.uuid4(), uuid.uuid4()])
    await world.person(role=MembershipRole.OWNER, joined=2, uid=high)
    await world.person(role=MembershipRole.OWNER, joined=2, uid=low)
    assert await world.resolve(leaving) == low


@pytest.mark.asyncio
async def test_the_owner_ranks_above_a_same_role_user(world):
    leaving, peer = await world.person(), await world.person()
    owner = await world.person(role=MembershipRole.OWNER, joined=9)
    role = uuid.uuid4()
    await world.role(leaving, role)
    await world.role(peer, role, since=0)
    assert await world.resolve(leaving) == owner


@pytest.mark.asyncio
async def test_a_removed_owner_is_not_their_own_successor(world):
    leaving = await world.person(role=MembershipRole.OWNER, joined=0)
    other = await world.person(role=MembershipRole.OWNER, joined=3)
    assert await world.resolve(leaving) == other


@pytest.mark.asyncio
async def test_deactivated_deleted_and_no_row_owners_are_skipped(world):
    leaving = await world.person()
    await world.person(role=MembershipRole.OWNER, joined=0, active=False)
    await world.person(role=MembershipRole.OWNER, joined=1, deleted=True)
    await world.person(role=MembershipRole.OWNER, joined=2, row=False)
    live = await world.person(role=MembershipRole.OWNER, joined=8)
    assert await world.resolve(leaving) == live


@pytest.mark.asyncio
async def test_a_same_role_user_is_chosen_by_role_tenure_then_id(world):
    leaving = await world.person()
    role = uuid.uuid4()
    newer, older = await world.person(), await world.person()
    await world.role(leaving, role)
    await world.role(newer, role, since=7)
    await world.role(older, role, since=2)
    assert await world.resolve(leaving) == older


@pytest.mark.asyncio
async def test_role_tenure_tie_goes_to_the_lowest_id(world):
    leaving = await world.person()
    low, high = sorted([uuid.uuid4(), uuid.uuid4()])
    await world.person(uid=high)
    await world.person(uid=low)
    role = uuid.uuid4()
    for holder in (leaving, high, low):
        await world.role(holder, role, since=3)
    assert await world.resolve(leaving) == low


@pytest.mark.asyncio
async def test_role_holders_who_are_ended_inactive_or_have_no_row_are_skipped(world):
    leaving = await world.person()
    role = uuid.uuid4()
    await world.role(leaving, role)
    ended = await world.person()
    await world.role(ended, role, ended=True)
    inactive = await world.person(active=False)
    await world.role(inactive, role)
    ghost = await world.person(row=False)
    await world.role(ghost, role)
    live = await world.person()
    await world.role(live, role, since=30)
    assert await world.resolve(leaving) == live


@pytest.mark.asyncio
async def test_a_user_in_another_role_is_not_a_same_role_user(world):
    leaving, other = await world.person(), await world.person()
    await world.role(leaving, uuid.uuid4())
    await world.role(other, uuid.uuid4())
    assert await world.resolve(leaving) is None


@pytest.mark.asyncio
async def test_nobody_to_inherit_is_none(world):
    leaving = await world.person()
    await world.person()  # an ordinary member is not a successor
    assert await world.resolve(leaving) is None


@pytest.mark.asyncio
async def test_the_direct_reports_are_never_the_successor(world):
    leaving, report = await world.person(), await world.person()
    await world.manager(report, USER, leaving)
    assert await world.resolve(leaving) is None


def test_a_missing_start_sorts_after_a_recorded_one():
    early, unknown = uuid.UUID(int=9), uuid.UUID(int=1)
    assert pick_longest_tenure([(unknown, None), (early, T0)]) == early
    assert pick_longest_tenure([]) is None
