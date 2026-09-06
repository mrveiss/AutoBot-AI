# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reporting-line writes are scoped to the caller's company (#15794, CWE-862).

``require_reporting_line_write`` answers "may this caller edit reporting lines".
It cannot answer **whose**. ``AgentOrgService.get_node`` looks the target up by
``agent_id`` alone and ``reports_to`` was accepted as given, so an authorised
caller could re-parent an agent in any company and name a manager from another.

Found in review on #15798, and it was an acceptance criterion of #15794 that the
first cut did not meet: the routes were gated for *authentication* and
*permission* and still not for *tenancy*. Authorisation has two halves and
passing one reads exactly like passing both.

A foreign agent is reported as **not found** rather than forbidden: a distinct
error would tell a caller that an agent exists in a company they cannot see.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Imported for its side effect: it registers the SQLite compile shims for
# postgresql JSONB / UUID, which agent_org_nodes.adapter_config needs to render
# on the in-memory database. Without it the table cannot be created at all.
from llc.tests import _e2e_harness as harness  # noqa: F401
from models.agent_org import AgentOrgNode
from services.agent_org_service import AgentOrgService
from user_management.models.base import Base


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    table = AgentOrgNode.__table__
    harness._scrub_pg_server_defaults(table)
    harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[table]))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


async def _seed(session_factory, company: uuid.UUID, agent_id: str) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session.add(
            AgentOrgNode(
                id=uuid.uuid4(),
                agent_id=agent_id,
                name=agent_id,
                org_role="worker",
                company_id=company,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_cannot_reparent_an_agent_in_another_company(session_factory):  # noqa: ANN001
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, theirs, "their-agent")
    await _seed(session_factory, mine, "my-manager")

    async with session_factory() as session:
        with pytest.raises(ValueError, match="not found in org hierarchy"):
            await AgentOrgService(session).update_reporting_line(
                agent_id="their-agent", new_manager_id="my-manager", company_id=mine
            )


@pytest.mark.asyncio
async def test_cannot_name_a_manager_from_another_company(session_factory):  # noqa: ANN001
    """The other half: the target is mine, the manager is not.

    Scoping only the target would look correct and still let an authorised
    caller point one of their own agents at a manager they cannot see.
    """
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, mine, "my-agent")
    await _seed(session_factory, theirs, "their-manager")

    async with session_factory() as session:
        with pytest.raises(ValueError, match="Manager not in this company"):
            await AgentOrgService(session).update_reporting_line(
                agent_id="my-agent", new_manager_id="their-manager", company_id=mine
            )


@pytest.mark.asyncio
async def test_an_in_company_reparent_still_works(session_factory):  # noqa: ANN001
    """The guard must not break the legitimate case it exists to narrow."""
    mine = uuid.uuid4()
    await _seed(session_factory, mine, "my-agent")
    await _seed(session_factory, mine, "my-manager")

    async with session_factory() as session:
        node = await AgentOrgService(session).update_reporting_line(
            agent_id="my-agent", new_manager_id="my-manager", company_id=mine
        )
        assert node.reports_to == "my-manager"


@pytest.mark.asyncio
async def test_upsert_cannot_claim_an_agent_from_another_company(session_factory):  # noqa: ANN001
    """PUT has the same hole as PATCH and needs the same guard.

    Fixing only the one the review named would leave the other route as the
    easier path to the same write — the pattern this whole issue is about.
    """
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, theirs, "their-agent")

    async with session_factory() as session:
        with pytest.raises(ValueError, match="not found in org hierarchy"):
            await AgentOrgService(session).upsert_node(agent_id="their-agent", name="Renamed", company_id=mine)


@pytest.mark.asyncio
async def test_untenanted_callers_are_unaffected(session_factory):  # noqa: ANN001
    """Seeding and pre-tenancy callers pass no company and must keep working.

    The scoping is enforced only when a company is supplied. Making it
    unconditional would break every caller that legitimately has no tenant.
    """
    company = uuid.uuid4()
    await _seed(session_factory, company, "agent-a")
    await _seed(session_factory, company, "agent-b")

    async with session_factory() as session:
        node = await AgentOrgService(session).update_reporting_line(
            agent_id="agent-a", new_manager_id="agent-b", company_id=None
        )
        assert node.reports_to == "agent-b"


@pytest.mark.asyncio
async def test_upsert_cannot_name_a_manager_from_another_company(session_factory):  # noqa: ANN001
    """The `upsert_node` manager arm, which the target-arm test cannot reach.

    Flagged in review and confirmed by mutation: deleting the manager check from
    `upsert_node` left the entire suite green. `update_reporting_line` had a case
    per arm and `upsert_node` had only one, so half its guard was decorative —
    the same "two-armed guard, one arm tested" gap found in the LLC service's
    IDOR check on #15792.
    """
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, mine, "my-agent")
    await _seed(session_factory, theirs, "their-manager")

    async with session_factory() as session:
        with pytest.raises(ValueError, match="Manager not in this company"):
            await AgentOrgService(session).upsert_node(
                agent_id="my-agent", name="Mine", reports_to="their-manager", company_id=mine
            )


@pytest.mark.asyncio
async def test_a_string_company_id_is_accepted(session_factory):  # noqa: ANN001
    """A caller passing a string must not fail at the write.

    `AgentOrgNode.company_id` is `UUID(as_uuid=True)`, so assigning a plain
    string fails during binding at flush() — a valid caller with a valid id,
    failing at the write rather than at the door. The HTTP routes pass the
    tenant context's UUID; older in-process callers pass strings. Normalising
    once means the comparisons and the assignment agree by construction rather
    than because each site happened to call str().
    """
    company = uuid.uuid4()
    await _seed(session_factory, company, "agent-a")
    await _seed(session_factory, company, "agent-b")

    async with session_factory() as session:
        node = await AgentOrgService(session).update_reporting_line(
            agent_id="agent-a", new_manager_id="agent-b", company_id=str(company)
        )
        assert node.reports_to == "agent-b"
