# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Two concurrent moves of one organization leave its CEO consistent (#15907 review).

``CompanyService.move`` reads the org row ``FOR UPDATE``. Without the lock, a
demotion and a promotion racing on a top-level company both read "top level":
the demotion retires the CEO, the promotion sees no position change and
provisions nothing, and the promotion's later commit leaves a top-level company
with no CEO.

Real Postgres only -- SQLite has no row locks, so this lives on the
migration-gate path with its siblings (``AUTOBOT_MIGRATION_TEST_ADMIN_URL``).
"""

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.asyncio, pytest.mark.migration_gate, requires_postgres]

#: Long enough that a move which is NOT waiting on the lock has finished.
_BLOCKED_PROBE_SECONDS = 1.0


@pytest.fixture()
async def maker(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed(maker, *, start_as_sub_org: bool) -> tuple[uuid.UUID, uuid.UUID]:  # noqa: ANN001
    from llc.models.company import CompanyCreate
    from llc.services.company import CompanyService

    tag = uuid.uuid4().hex[:6]
    async with maker() as session:
        svc = CompanyService(session)
        parent = await svc.create(CompanyCreate(name=f"Parent {tag}", slug=f"parent-{tag}"))
        org = await svc.create(CompanyCreate(name=f"Acme {tag}", slug=f"acme-{tag}"))
        if start_as_sub_org:
            await svc.move(org.id, parent.id)
        await session.commit()
        return parent.id, org.id


async def _race(maker, org_id: uuid.UUID, first, second) -> None:  # noqa: ANN001
    """Move *first* holding the lock; *second* must wait for it, then see its result."""
    from llc.services.company import CompanyService

    async with maker() as a, maker() as b:
        await CompanyService(a).move(org_id, first)
        late = asyncio.create_task(CompanyService(b).move(org_id, second))
        done, _ = await asyncio.wait({late}, timeout=_BLOCKED_PROBE_SECONDS)
        assert not done, "the second move did not wait for the first one's row lock"
        await a.commit()
        await late
        await b.commit()


async def _ceo_state(maker, org_id: uuid.UUID) -> tuple:  # noqa: ANN001
    from llc.services.company_ceo import CompanyCEOService, default_ceo_slug
    from models.agent_org import AgentOrgNode
    from user_management.models.organization import Organization

    async with maker() as session:
        org = await session.get(Organization, org_id)
        designation = await CompanyCEOService().designation(session, org_id)
        nodes = (
            (await session.execute(sa.select(AgentOrgNode).where(AgentOrgNode.agent_id == default_ceo_slug(org_id))))
            .scalars()
            .all()
        )
    return org.parent_org_id, designation, list(nodes)


async def test_demote_then_promote_ends_top_level_with_exactly_one_ceo(maker):  # noqa: ANN001
    parent_id, org_id = await _seed(maker, start_as_sub_org=False)

    await _race(maker, org_id, parent_id, None)

    parent, designation, nodes = await _ceo_state(maker, org_id)
    assert parent is None
    assert designation is not None
    assert len(nodes) == 1
    assert designation.holder_agent_id == nodes[0].id


async def test_promote_then_demote_ends_a_sub_org_with_no_ceo(maker):  # noqa: ANN001
    parent_id, org_id = await _seed(maker, start_as_sub_org=True)

    await _race(maker, org_id, None, parent_id)

    parent, designation, nodes = await _ceo_state(maker, org_id)
    assert parent == parent_id
    assert designation is None
    assert len(nodes) == 1  # kept, never deleted (migration 090's rule)
    assert nodes[0].status == "inactive"
    assert nodes[0].heartbeat_enabled is False
