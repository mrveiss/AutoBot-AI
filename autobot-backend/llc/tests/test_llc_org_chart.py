# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Behaviour lock for GET /api/llc/companies/{company_id}/org-chart (GH#9861).

This module mounts the REAL companies router over the same minimal-mount
harness used by ``test_llc_e2e_loop.py`` (in-memory SQLite, dependency
overrides for the session/auth/tenant). It locks the three review-fix bugs
plus the tenant gate of ``get_org_chart``:

  1. Forest shape — a manager (reports_to=None) and its report assemble into a
     single root whose ``children`` holds the report.
  2. Status mapping (H1) — the LATEST heartbeat run per agent maps onto the
     org-chart status vocabulary: ``timeout``→"error" (NOT "idle"; the enum has
     no ``timed_out``), ``completed``→"idle", ``running``→"active".
  3. Cycle safety (H2) — A.reports_to=B and B.reports_to=A still returns 200
     with BOTH agents present exactly once (the cycle is broken into roots,
     no infinite recursion).
  4. Tenant gate (C1) — a non-platform-admin whose ``org_id`` != company_id is
     403; a platform admin or a matching ``org_id`` is 200. Uses the REAL
     ``TenantContext`` field name ``is_platform_admin``.

Determinism: no network, no Postgres, no Redis — identical to the e2e harness.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator, Optional

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.budget import LLCAgentBudget
from llc.models.enums import HeartbeatInvocationSource, LLCRunStatus
from llc.models.heartbeat_run import LLCHeartbeatRun

# Importing the harness registers the SQLite compile shims and all loop models
# (including AgentOrgNode + LLCHeartbeatRun + LLCAgentBudget) on Base.metadata.
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode, OrgRole

_FIXED_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


# ---------------------------------------------------------------------------
# Fixtures (mirror the e2e harness; the tenant context is mutable per-test).
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    return async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )


@pytest_asyncio.fixture
async def app(session_factory):  # noqa: ANN001, ANN201
    """Minimal FastAPI mounting the REAL companies router under /api/llc.

    ``app.state.tenant`` is a mutable holder the test sets before each request
    so the tenant gate (org_id / is_platform_admin) can be exercised both ways.
    """
    from fastapi import FastAPI

    from llc.api import companies as companies_api
    from user_management.database import get_async_session
    from user_management.services import TenantContext

    application = FastAPI()
    application.include_router(companies_api.router, prefix="/api/llc")

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_async_session] = _override_session

    # Mutable tenant holder — the test rewrites it to flip org_id / admin flag.
    tenant = {"org_id": None, "is_platform_admin": True}

    def _override_current_user() -> dict:
        return {
            "id": str(_FIXED_USER_ID),
            "user_id": str(_FIXED_USER_ID),
            "username": "admin",
            "role": "admin",
            "is_platform_admin": tenant["is_platform_admin"],
        }

    def _override_tenant() -> TenantContext:
        org = uuid.UUID(tenant["org_id"]) if tenant["org_id"] else None
        return TenantContext(
            org_id=org,
            user_id=_FIXED_USER_ID,
            is_platform_admin=tenant["is_platform_admin"],
        )

    from api.user_management.dependencies import (
        get_current_user,
        get_tenant_context,
        require_org_context,
    )

    application.dependency_overrides[get_current_user] = _override_current_user
    application.dependency_overrides[get_tenant_context] = _override_tenant
    application.dependency_overrides[require_org_context] = _override_tenant

    application.state.tenant = tenant
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:  # noqa: ANN001
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Direct-seed helpers (no public POST creates org/heartbeat rows on this schema).
# ---------------------------------------------------------------------------


async def _seed_org_node(
    session_factory,  # noqa: ANN001
    company_id: uuid.UUID,
    *,
    name: str,
    role: str = OrgRole.WORKER.value,
    title: Optional[str] = None,
    reports_to: Optional[str] = None,
) -> str:
    """Seed one AgentOrgNode and return its agent_id."""
    agent_id = str(uuid.uuid4())
    async with session_factory() as session:
        session.add(
            AgentOrgNode(
                id=uuid.uuid4(),
                agent_id=agent_id,
                name=name,
                org_role=role,
                title=title,
                reports_to=reports_to,
                company_id=company_id,
            )
        )
        await session.commit()
    return agent_id


async def _seed_run(
    session_factory,  # noqa: ANN001
    company_id: uuid.UUID,
    agent_id: str,
    status_value: str,
) -> None:
    """Seed a single LLCHeartbeatRun (becomes the agent's latest run)."""
    async with session_factory() as session:
        session.add(
            LLCHeartbeatRun(
                id=uuid.uuid4(),
                company_id=company_id,
                agent_id=agent_id,
                invocation_source=HeartbeatInvocationSource.SCHEDULER.value,
                status=status_value,
            )
        )
        await session.commit()


async def _seed_budget(
    session_factory,  # noqa: ANN001
    company_id: uuid.UUID,
    agent_id: str,
    *,
    limit: str,
    spent: str,
) -> None:
    async with session_factory() as session:
        session.add(
            LLCAgentBudget(
                id=uuid.uuid4(),
                company_id=str(company_id),
                agent_id=agent_id,
                budget_mode="dollars",
                budget_limit=Decimal(limit),
                budget_spent=Decimal(spent),
                tokens_spent=0,
                alert_threshold=0.8,
            )
        )
        await session.commit()


def _collect_ids(nodes: list) -> list:
    """Walk the forest (nodes + children) and collect every node id in order."""
    ids: list = []
    for node in nodes:
        ids.append(node["id"])
        ids.extend(_collect_ids(node.get("children", [])))
    return ids


# ---------------------------------------------------------------------------
# 1. Forest shape + budget composition.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_chart_forest_shape_and_budget(app, client, session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False  # matching org_id → allowed

    manager_id = await _seed_org_node(
        session_factory, company_id, name="Manager", role=OrgRole.MANAGER.value, title="VP Eng"
    )
    report_id = await _seed_org_node(session_factory, company_id, name="Report", reports_to=manager_id)

    # Budget composition (optional assert): manager carries a budget row.
    await _seed_budget(session_factory, company_id, manager_id, limit="100.000000", spent="42.500000")

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    nodes = body["nodes"]

    # Exactly ONE root: the manager.
    assert len(nodes) == 1, nodes
    root = nodes[0]
    assert root["id"] == manager_id
    assert root["name"] == "Manager"
    assert root["title"] == "VP Eng"
    assert root["parent_id"] is None

    # The report is the manager's single child.
    assert len(root["children"]) == 1, root
    child = root["children"][0]
    assert child["id"] == report_id
    assert child["parent_id"] == manager_id
    assert child["children"] == []

    # Budget composition reflects the seeded row.
    assert root["budget_total"] == 100.0
    assert root["budget_spent"] == 42.5
    # Report has no budget row → zeroed.
    assert child["budget_total"] == 0.0
    assert child["budget_spent"] == 0.0


# ---------------------------------------------------------------------------
# 2. Status mapping (H1): timeout→error, completed→idle, running→active.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_chart_status_mapping(app, client, session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    timeout_agent = await _seed_org_node(session_factory, company_id, name="Timeout Agent")
    completed_agent = await _seed_org_node(session_factory, company_id, name="Completed Agent")
    running_agent = await _seed_org_node(session_factory, company_id, name="Running Agent")
    no_run_agent = await _seed_org_node(session_factory, company_id, name="No Run Agent")

    # H1: enum value is "timeout" (NOT "timed_out") and must map to error.
    await _seed_run(session_factory, company_id, timeout_agent, LLCRunStatus.TIMEOUT.value)
    await _seed_run(session_factory, company_id, completed_agent, LLCRunStatus.COMPLETED.value)
    await _seed_run(session_factory, company_id, running_agent, LLCRunStatus.RUNNING.value)

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]

    status_by_id = {n["id"]: n["status"] for n in nodes}
    # All four are roots (no reports_to).
    assert set(status_by_id) == {timeout_agent, completed_agent, running_agent, no_run_agent}

    assert status_by_id[timeout_agent] == "error", "timeout must map to error, not idle"
    assert status_by_id[completed_agent] == "idle"
    assert status_by_id[running_agent] == "active"
    # No heartbeat run at all → idle.
    assert status_by_id[no_run_agent] == "idle"


# ---------------------------------------------------------------------------
# 3. Cycle safety (H2): A→B→A returns 200 with both agents present once.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_chart_cycle_safety(app, client, session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    # Seed A and B first without the cyclic edge (reports_to is a free string),
    # then patch each to point at the other so neither resolves to a real root.
    agent_a = await _seed_org_node(session_factory, company_id, name="Agent A")
    agent_b = await _seed_org_node(session_factory, company_id, name="Agent B")

    from sqlalchemy import update

    async with session_factory() as session:
        await session.execute(update(AgentOrgNode).where(AgentOrgNode.agent_id == agent_a).values(reports_to=agent_b))
        await session.execute(update(AgentOrgNode).where(AgentOrgNode.agent_id == agent_b).values(reports_to=agent_a))
        await session.commit()

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    # Must NOT infinitely recurse / 500 — returns 200.
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]

    all_ids = _collect_ids(nodes)
    # Both agents appear exactly once across the whole forest.
    assert sorted(all_ids) == sorted([agent_a, agent_b]), all_ids
    assert len(all_ids) == len(set(all_ids)), f"duplicated node in cycle output: {all_ids}"


# ---------------------------------------------------------------------------
# 4. Tenant gate (C1): mismatched org_id + non-admin → 403; admin/match → 200.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_chart_tenant_403_for_mismatched_non_admin(app, client, session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    await _seed_org_node(session_factory, company_id, name="Solo")

    # Tenant belongs to a DIFFERENT org and is NOT a platform admin → forbidden.
    app.state.tenant["org_id"] = str(uuid.uuid4())
    app.state.tenant["is_platform_admin"] = False

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_org_chart_platform_admin_allowed(app, client, session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    await _seed_org_node(session_factory, company_id, name="Solo")

    # Platform admin from an unrelated org is allowed (cross-tenant by design).
    app.state.tenant["org_id"] = str(uuid.uuid4())
    app.state.tenant["is_platform_admin"] = True

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_org_chart_matching_org_allowed(app, client, session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    await _seed_org_node(session_factory, company_id, name="Solo")

    # Non-admin but org_id matches the requested company → allowed.
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
