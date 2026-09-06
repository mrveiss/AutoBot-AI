# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A company has a CEO, and the default reporting chain resolves through it (#15770).

The failure mode this file is written against is a **creation-only**
implementation: one that provisions a CEO for new companies, passes every test
written against a freshly made company, and changes nothing for any company that
already exists. Today every company is in that state, so a test suite that only
ever looks at new companies would report the feature complete while the
hierarchy stayed broken everywhere it actually matters.

So the provisioning tests here start from a company row with **no** designation
-- which is precisely what an existing company is -- rather than from one the
creation path just built.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
import sqlalchemy.exc

from llc.models.company_ceo import LLCCompanyCEO
from llc.models.enums import MembershipRole, RoleHolderType
from llc.models.membership import LLCCompanyMembership
from llc.services.company_ceo import CompanyCEOService, default_ceo_slug
from llc.services.reporting_line import ChainEnd, Holder, ReportingLineService
from llc.tests.test_llc_org_chart import (  # noqa: F401
    _seed_org_node,
    app,
    client,
    engine,
    session_factory,
)
from models.agent_org import AgentOrgNode

# ---------------------------------------------------------------------------


async def _seed_company_without_ceo(session_factory) -> uuid.UUID:  # noqa: ANN001
    """A company id with no CEO designation -- i.e. every company today."""
    return uuid.uuid4()


async def _seed_owner(session_factory, company_id: uuid.UUID) -> uuid.UUID:  # noqa: ANN001
    user_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company_id,
                user_id=user_id,
                role=MembershipRole.OWNER.value,
            )
        )
        await session.commit()
    return user_id


async def _seed_member(session_factory, company_id: uuid.UUID) -> uuid.UUID:  # noqa: ANN001
    """A plain member of the company."""
    user_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company_id,
                user_id=user_id,
                role=MembershipRole.MEMBER.value,
            )
        )
        await session.commit()
    return user_id


async def _seed_agent(session_factory, company_id: uuid.UUID, slug: str) -> uuid.UUID:  # noqa: ANN001
    agent_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(AgentOrgNode(id=agent_id, agent_id=slug, name=slug, company_id=company_id))
        await session.commit()
    return agent_id


# ---------------------------------------------------------------------------
# The designation itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_company_with_no_designation_resolves_to_no_ceo(session_factory):  # noqa: ANN001
    """The state every company is in before this change."""
    company_id = await _seed_company_without_ceo(session_factory)

    async with session_factory() as session:
        assert await CompanyCEOService().resolve(session, company_id) is None


@pytest.mark.asyncio
async def test_provisioning_gives_an_existing_company_an_agent_ceo(session_factory):  # noqa: ANN001
    """AC: existing companies acquire one too.

    The company here was never built by the creation path -- it is a bare id
    with no designation, which is what a company created before this change
    looks like.
    """
    company_id = await _seed_company_without_ceo(session_factory)

    async with session_factory() as session:
        row = await CompanyCEOService().provision_default(session, company_id)
        await session.commit()

    assert row.holder_type == RoleHolderType.AGENT.value
    assert row.holder_agent_id is not None
    assert row.holder_user_id is None

    async with session_factory() as session:
        agent = (
            await session.execute(sa.select(AgentOrgNode).where(AgentOrgNode.id == row.holder_agent_id))
        ).scalar_one()
    assert agent.agent_id == default_ceo_slug(company_id)
    assert agent.company_id == company_id


@pytest.mark.asyncio
async def test_provisioning_twice_does_not_displace_a_chosen_ceo(session_factory):  # noqa: ANN001
    """Provisioning means "ensure there is one", not "make a new one".

    A retry at company creation must not evict a CEO an owner has since chosen.
    """
    company_id = await _seed_company_without_ceo(session_factory)
    chosen = await _seed_agent(session_factory, company_id, "chosen-ceo")

    async with session_factory() as session:
        await CompanyCEOService().set_ceo(session, company_id, RoleHolderType.AGENT.value, chosen)
        await session.commit()

    async with session_factory() as session:
        row = await CompanyCEOService().provision_default(session, company_id)
        await session.commit()

    assert row.holder_agent_id == chosen


@pytest.mark.asyncio
async def test_the_ceo_can_be_a_person(session_factory):  # noqa: ANN001
    """AC: the designation can be changed to a person.

    The contrast that matters: code reading `holder_agent_id` directly rather
    than through the discriminator passes every agent test and breaks here.
    """
    company_id = await _seed_company_without_ceo(session_factory)
    person = await _seed_owner(session_factory, company_id)

    async with session_factory() as session:
        await CompanyCEOService().provision_default(session, company_id)
        await session.commit()

    async with session_factory() as session:
        row = await CompanyCEOService().set_ceo(session, company_id, RoleHolderType.USER.value, person)
        await session.commit()

    assert row.holder_type == RoleHolderType.USER.value
    assert row.holder_user_id == person
    # The agent id must be cleared, not merely ignored: a row whose populated
    # columns contradict its discriminator is corrupt.
    assert row.holder_agent_id is None

    async with session_factory() as session:
        resolved = await CompanyCEOService().resolve(session, company_id)
    assert resolved is not None
    assert (resolved.type, resolved.id) == (RoleHolderType.USER.value, person)


@pytest.mark.asyncio
async def test_a_contact_cannot_hold_the_position(session_factory):  # noqa: ANN001
    company_id = await _seed_company_without_ceo(session_factory)
    async with session_factory() as session:
        with pytest.raises(ValueError):
            await CompanyCEOService().set_ceo(session, company_id, RoleHolderType.CONTACT.value, uuid.uuid4())


@pytest.mark.asyncio
async def test_a_deleted_ceo_agent_reports_absence_rather_than_crashing(session_factory):  # noqa: ANN001
    """AC: a company with no CEO reports that state explicitly and renders.

    A dangling designation must not be reported as a CEO, and must not promote
    some other node to fill the gap -- an arbitrary promotion is a silent wrong
    answer to "who runs this company".
    """
    company_id = await _seed_company_without_ceo(session_factory)

    async with session_factory() as session:
        row = await CompanyCEOService().provision_default(session, company_id)
        agent_pk = row.holder_agent_id
        await session.commit()

    async with session_factory() as session:
        agent = await session.get(AgentOrgNode, agent_pk)
        await session.delete(agent)
        await session.commit()

    async with session_factory() as session:
        service = CompanyCEOService()
        # The row is still there ...
        assert await service.designation(session, company_id) is not None
        # ... and resolution still reports absence.
        assert await service.resolve(session, company_id) is None


@pytest.mark.asyncio
async def test_clearing_the_designation_reports_whether_there_was_one(session_factory):  # noqa: ANN001
    company_id = await _seed_company_without_ceo(session_factory)

    async with session_factory() as session:
        assert await CompanyCEOService().clear(session, company_id) is False

    async with session_factory() as session:
        await CompanyCEOService().provision_default(session, company_id)
        await session.commit()

    async with session_factory() as session:
        assert await CompanyCEOService().clear(session, company_id) is True
        await session.commit()

    async with session_factory() as session:
        assert await CompanyCEOService().designation(session, company_id) is None


# ---------------------------------------------------------------------------
# The default chain, which is why the designation exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_chain_reaches_the_ceo_when_no_explicit_line_exists(session_factory):  # noqa: ANN001
    """The whole point: an absent reporting line resolves through the CEO."""
    company_id = await _seed_company_without_ceo(session_factory)
    owner = await _seed_owner(session_factory, company_id)
    subject = await _seed_agent(session_factory, company_id, "worker-a")

    async with session_factory() as session:
        ceo_row = await CompanyCEOService().provision_default(session, company_id)
        ceo_agent_pk = ceo_row.holder_agent_id
        await session.commit()

    async with session_factory() as session:
        chain = await ReportingLineService().chain_up(
            session, company_id, Holder(type=RoleHolderType.AGENT.value, id=subject)
        )

    assert chain.ended is ChainEnd.OWNER
    assert chain.managers[0] == Holder(type=RoleHolderType.AGENT.value, id=ceo_agent_pk)
    assert Holder(type=RoleHolderType.USER.value, id=owner) in chain.managers


@pytest.mark.asyncio
async def test_the_chain_still_reports_no_ceo_when_there_is_none(session_factory):  # noqa: ANN001
    """The pre-#15770 behaviour must survive for a company without a CEO."""
    company_id = await _seed_company_without_ceo(session_factory)
    await _seed_owner(session_factory, company_id)
    subject = await _seed_agent(session_factory, company_id, "worker-b")

    async with session_factory() as session:
        chain = await ReportingLineService().chain_up(
            session, company_id, Holder(type=RoleHolderType.AGENT.value, id=subject)
        )

    assert chain.ended is ChainEnd.NO_CEO


@pytest.mark.asyncio
async def test_the_chain_reaches_a_human_ceo_too(session_factory):  # noqa: ANN001
    """A person holding the position must resolve like an agent does."""
    company_id = await _seed_company_without_ceo(session_factory)
    owner = await _seed_owner(session_factory, company_id)
    # A member, not a bare UUID: a human CEO must belong to the company, which
    # is the boundary `_require_in_company` enforces.
    human_ceo = await _seed_member(session_factory, company_id)
    subject = await _seed_agent(session_factory, company_id, "worker-c")

    async with session_factory() as session:
        await CompanyCEOService().set_ceo(session, company_id, RoleHolderType.USER.value, human_ceo)
        await session.commit()

    async with session_factory() as session:
        chain = await ReportingLineService().chain_up(
            session, company_id, Holder(type=RoleHolderType.AGENT.value, id=subject)
        )

    assert chain.managers[0] == Holder(type=RoleHolderType.USER.value, id=human_ceo)
    assert chain.ended is ChainEnd.OWNER
    assert Holder(type=RoleHolderType.USER.value, id=owner) in chain.managers


@pytest.mark.asyncio
async def test_one_ceo_per_company_is_enforced_by_the_schema(session_factory):  # noqa: ANN001
    """Not merely by the service: a rule only in code holds until the second writer."""
    company_id = await _seed_company_without_ceo(session_factory)
    async with session_factory() as session:
        session.add(LLCCompanyCEO(company_id=company_id, holder_type="agent", holder_agent_id=uuid.uuid4()))
        await session.commit()

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        async with session_factory() as session:
            session.add(LLCCompanyCEO(company_id=company_id, holder_type="agent", holder_agent_id=uuid.uuid4()))
            await session.commit()


@pytest.mark.asyncio
async def test_creating_a_company_provisions_an_agent_ceo(session_factory):  # noqa: ANN001
    """AC: a new company is provisioned with an agent CEO by default.

    This is the half a creation-only implementation gets right. It is here so
    the *other* tests -- the ones starting from a company with no designation --
    are demonstrably testing something this one does not cover.
    """
    from llc.models.company import CompanyCreate
    from llc.services.company import CompanyService

    async with session_factory() as session:
        org = await CompanyService(session).create(CompanyCreate(name="Acme", slug="acme"))
        await session.commit()
        company_id = org.id

    async with session_factory() as session:
        resolved = await CompanyCEOService().resolve(session, company_id)

    assert resolved is not None
    assert resolved.type == RoleHolderType.AGENT.value


# ---------------------------------------------------------------------------
# The backfill, which these tests cannot execute
# ---------------------------------------------------------------------------
#
# The migration's provisioning is Postgres-only (``gen_random_uuid()``), and
# this suite runs on in-memory SQLite. These assertions are therefore
# *structural*: they read the migration source. They prove the backfill targets
# every existing company and is re-runnable; they do NOT prove it executes
# correctly against a real database. That is CI's job, and the PR says so.


def _migration_source() -> str:
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "20260906_088_llc_company_ceos.py"
    return path.read_text(encoding="utf-8")


def test_the_backfill_targets_existing_companies_not_only_new_ones():
    """The creation-only failure mode, as a test.

    A backfill that selected from anything other than the companies table would
    provision for whatever set it named -- and the set that matters is "every
    company that exists right now".
    """
    source = _migration_source()
    # Both statements, not just one: a mutation that re-pointed only the agent
    # insert left the designation insert intact and passed a presence check.
    assert source.count("FROM organizations o") == 2
    assert source.count("o.llc_status IS NOT NULL") == 2, "both statements must scope to LLC companies"


def test_the_backfill_is_rerunnable():
    """`upgrade` always reaches the backfill, so a re-run must be a no-op.

    Both inserts are guarded, and the guard is on the CEO row rather than on the
    agent: an interrupted run that created the agent but not the designation has
    to be completable.
    """
    source = _migration_source()
    assert source.count("NOT EXISTS (SELECT 1 FROM llc_company_ceos c WHERE c.company_id = o.id)") == 2
    assert "NOT EXISTS (SELECT 1 FROM agent_org_nodes a WHERE a.agent_id = 'ceo-' || o.id::text)" in source


def test_the_backfill_slug_matches_the_service():
    """One slug rule, not two.

    If the migration and the service disagreed, a backfilled company would get a
    second CEO agent the first time the service provisioned for it.
    """
    source = _migration_source()
    assert "'ceo-' || o.id::text" in source
    assert default_ceo_slug(uuid.UUID(int=0)) == f"ceo-{uuid.UUID(int=0)}"


# ---------------------------------------------------------------------------
# Company boundary (CWE-639) -- review findings on #15856
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agent_from_another_company_cannot_be_made_ceo(session_factory):  # noqa: ANN001
    """`set_ceo` took any UUID the caller supplied.

    Installing another tenant's agent at the top of this chart would let the
    upward walk traverse into a company the caller has no access to.
    """
    company_id = await _seed_company_without_ceo(session_factory)
    other_company = await _seed_company_without_ceo(session_factory)
    foreign_agent = await _seed_agent(session_factory, other_company, "foreign-agent")

    async with session_factory() as session:
        with pytest.raises(ValueError):
            await CompanyCEOService().set_ceo(session, company_id, RoleHolderType.AGENT.value, foreign_agent)


@pytest.mark.asyncio
async def test_a_person_from_another_company_cannot_be_made_ceo(session_factory):  # noqa: ANN001
    """The same boundary on the user side, where membership is the test."""
    company_id = await _seed_company_without_ceo(session_factory)
    other_company = await _seed_company_without_ceo(session_factory)
    outsider = await _seed_owner(session_factory, other_company)

    async with session_factory() as session:
        with pytest.raises(ValueError):
            await CompanyCEOService().set_ceo(session, company_id, RoleHolderType.USER.value, outsider)


@pytest.mark.asyncio
async def test_resolution_drops_a_holder_that_left_the_company(session_factory):  # noqa: ANN001
    """Read-side scope, not just write-side.

    A row can predate the write-side check, so resolution must refuse it too --
    otherwise the guard only protects rows written after this change.
    """
    company_id = await _seed_company_without_ceo(session_factory)
    other_company = await _seed_company_without_ceo(session_factory)
    foreign_agent = await _seed_agent(session_factory, other_company, "foreign-ceo")

    # Written directly, bypassing the service, as a pre-existing row would be.
    async with session_factory() as session:
        session.add(
            LLCCompanyCEO(
                company_id=company_id,
                holder_type=RoleHolderType.AGENT.value,
                holder_agent_id=foreign_agent,
            )
        )
        await session.commit()

    async with session_factory() as session:
        assert await CompanyCEOService().resolve(session, company_id) is None


@pytest.mark.asyncio
async def test_provisioning_refuses_a_slug_held_by_another_company(session_factory):  # noqa: ANN001
    """Adoption is company-scoped.

    `agent_org_nodes.agent_id` is globally unique (#15812), so this slug can
    already exist under a different company. Adopting it would install a foreign
    agent as CEO; raising is recoverable, a cross-tenant CEO is not.
    """
    company_id = await _seed_company_without_ceo(session_factory)
    other_company = await _seed_company_without_ceo(session_factory)
    await _seed_agent(session_factory, other_company, default_ceo_slug(company_id))

    async with session_factory() as session:
        # Matched on message: a bare `ValueError` is also raised by
        # `_require_in_company`, so an unmatched assertion passes even when the
        # slug-ownership guard is gone.
        with pytest.raises(ValueError, match="already held by another company"):
            await CompanyCEOService().provision_default(session, company_id)


def test_the_backfill_join_is_scoped_to_the_company():
    """Structural: the designation insert must match on company as well as slug.

    Matching on slug alone, a slug owned by another company is skipped by the
    first insert's guard and then adopted by the second.
    """
    source = _migration_source()
    assert "JOIN agent_org_nodes a ON a.agent_id = 'ceo-' || o.id::text AND a.company_id = o.id" in source


@pytest.mark.asyncio
async def test_pointing_the_ceo_at_someone_who_defaults_back_is_refused(session_factory):  # noqa: ANN001
    """The default chain can now close a loop, which it could not before.

    `_would_cycle` walks explicit edges only, and its docstring justifies that
    by saying the defaults cannot form a cycle "because owners terminate". That
    was true while `_resolve_ceo` returned None: the default chain went straight
    from anyone to the owners, and owners have no manager.

    Designating a CEO inserts a middle step. Now:

        CEO --explicit--> Y        (the edge under test)
        Y   --default---> CEO      (Y has no explicit line, so Y reports to the CEO)

    which is a loop, and an explicit-only walk cannot see it: walking up from Y
    finds no explicit manager and stops.
    """
    company_id = await _seed_company_without_ceo(session_factory)
    await _seed_owner(session_factory, company_id)
    worker = await _seed_agent(session_factory, company_id, "worker-loop")

    async with session_factory() as session:
        ceo_row = await CompanyCEOService().provision_default(session, company_id)
        ceo_agent = ceo_row.holder_agent_id
        await session.commit()

    service = ReportingLineService()
    async with session_factory() as session:
        with pytest.raises(ValueError):
            await service.set_line(
                session,
                company_id=company_id,
                subject=Holder(type=RoleHolderType.AGENT.value, id=ceo_agent),
                manager=Holder(type=RoleHolderType.AGENT.value, id=worker),
                actor_user_id=await _seed_owner(session_factory, company_id),
            )


@pytest.mark.asyncio
async def test_an_ordinary_reporting_line_is_still_accepted(session_factory):  # noqa: ANN001
    """The contrast case for the cycle walk, and it is not decoration.

    Following the default edge means the walk now reaches the CEO on almost
    every check. If it does not stop there, the CEO is seen twice and reported
    as a loop -- so the guard that refuses cycles would refuse nearly every
    legitimate edge instead. A suite that only tests refusal cannot tell the
    two apart: both look like "raises ValueError".
    """
    company_id = await _seed_company_without_ceo(session_factory)
    await _seed_owner(session_factory, company_id)
    actor = await _seed_owner(session_factory, company_id)
    manager = await _seed_agent(session_factory, company_id, "team-lead")
    report = await _seed_agent(session_factory, company_id, "team-member")

    async with session_factory() as session:
        await CompanyCEOService().provision_default(session, company_id)
        await session.commit()

    async with session_factory() as session:
        line = await ReportingLineService().set_line(
            session,
            company_id=company_id,
            subject=Holder(type=RoleHolderType.AGENT.value, id=report),
            manager=Holder(type=RoleHolderType.AGENT.value, id=manager),
            actor_user_id=actor,
        )
        await session.commit()

    assert line.subject_agent_id == report
    assert line.manager_agent_id == manager
