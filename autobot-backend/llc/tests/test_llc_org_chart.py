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
from unittest.mock import AsyncMock, patch

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
        session_factory,
        company_id,
        name="Manager",
        role=OrgRole.MANAGER.value,
        title="VP Eng",
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
    assert set(status_by_id) == {
        timeout_agent,
        completed_agent,
        running_agent,
        no_run_agent,
    }

    assert status_by_id[timeout_agent] == "error", "timeout must map to error, not idle"
    assert status_by_id[completed_agent] == "idle"
    assert status_by_id[running_agent] == "active"
    # No heartbeat run at all → idle.
    assert status_by_id[no_run_agent] == "idle"


# ---------------------------------------------------------------------------
# 2b. Pause/terminate survive a reload (#14108) — the persisted lifecycle
# state must win over a stale/live heartbeat run, not merely be writable.
# ---------------------------------------------------------------------------


def _mock_redis() -> AsyncMock:
    """A permissive Redis stand-in for ControlsService's best-effort flag set.

    ``get_async_redis_client`` is itself ``async def``, so ``patch(...)``
    replaces it with an ``AsyncMock`` automatically (autodetected from the
    patched target) — this helper only needs to be the *return value* of
    that awaited call, matching ``llc/tests/test_controls.py``'s pattern.
    """
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


def _mock_activity_log() -> AsyncMock:
    """``llc_activity_log`` FKs to ``organizations``, which this module's
    minimal loop schema (``harness.create_loop_schema``) never creates —
    mocked out exactly like ``llc/tests/test_controls.py``'s
    ``_activity_log_mock``, since activity logging is not what these tests
    exercise.
    """
    from llc.services.activity_log import LLCActivityLogService

    log = AsyncMock(spec=LLCActivityLogService)
    log.record = AsyncMock()
    return log


@pytest.mark.asyncio
async def test_org_chart_pause_survives_reload(app, client, session_factory):  # noqa: ANN001
    """Pause an agent via the real ControlsService, then reload the org
    chart: the node must still read "paused", not the heartbeat-derived
    status of a "running" run recorded before the pause (#14108).

    Drives the same code path production traffic uses — ControlsService
    against a real (SQLite) session — rather than asserting the response
    schema, per the issue's acceptance criteria.
    """
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    agent_id = await _seed_org_node(session_factory, company_id, name="Worker")
    # A "running" heartbeat run would derive "active" if nothing overrode it.
    await _seed_run(session_factory, company_id, agent_id, LLCRunStatus.RUNNING.value)

    from llc.services.controls_service import ControlsService

    with patch(
        "llc.services.controls_service.get_async_redis_client",
        return_value=_mock_redis(),
    ):
        async with session_factory() as session:
            # .hex, not str(): SQLite stores UUIDs as 32-char hex (#10032 pattern,
            # see test_agent_id_keyspace.py); ControlsService's raw SQL WHERE
            # would not match the dashed form under the SQLite test engine.
            await ControlsService(activity_log=_mock_activity_log()).pause_agent(
                session,
                company_id.hex,
                agent_id,
                actor_user_id=str(_FIXED_USER_ID),
                reason="test pause",
            )
            await session.commit()

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["status"] == "paused", "a paused agent must not read back as the derived heartbeat status"


@pytest.mark.asyncio
async def test_org_chart_terminate_survives_reload(app, client, session_factory):  # noqa: ANN001
    """Terminate an agent via the real ControlsService, then reload: the
    node must still read "terminated" (#14108), never "active"/"idle" from
    a stale run.
    """
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    agent_id = await _seed_org_node(session_factory, company_id, name="Worker")
    await _seed_run(session_factory, company_id, agent_id, LLCRunStatus.RUNNING.value)

    from llc.services.controls_service import ControlsService

    with patch(
        "llc.services.controls_service.get_async_redis_client",
        return_value=_mock_redis(),
    ):
        async with session_factory() as session:
            # .hex — see the pause test above for why.
            await ControlsService(activity_log=_mock_activity_log()).terminate_agent(
                session,
                company_id.hex,
                agent_id,
                actor_user_id=str(_FIXED_USER_ID),
                reason="test terminate",
            )
            await session.commit()

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["status"] == "terminated", "a terminated agent must never read back as active/idle"


@pytest.mark.asyncio
async def test_org_chart_resume_falls_back_to_heartbeat(app, client, session_factory):  # noqa: ANN001
    """After resume, the persisted status is no longer a stop state, so the
    org chart falls back to the heartbeat-derived status again (#14108) —
    resume does not freeze the node at "paused" nor invent a display status
    of its own.
    """
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    agent_id = await _seed_org_node(session_factory, company_id, name="Worker")
    await _seed_run(session_factory, company_id, agent_id, LLCRunStatus.COMPLETED.value)

    from llc.services.controls_service import ControlsService

    svc = ControlsService(activity_log=_mock_activity_log())
    with patch(
        "llc.services.controls_service.get_async_redis_client",
        return_value=_mock_redis(),
    ):
        async with session_factory() as session:
            await svc.pause_agent(session, company_id.hex, agent_id, actor_user_id=str(_FIXED_USER_ID))
            await session.commit()
        async with session_factory() as session:
            await svc.resume_agent(session, company_id.hex, agent_id, actor_user_id=str(_FIXED_USER_ID))
            await session.commit()

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]
    assert nodes[0]["status"] == "idle"  # heartbeat-derived, not stuck at "paused"


# ---------------------------------------------------------------------------
# 2c. adapter_type is honest, not org_role (#14109).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_chart_adapter_type_is_the_real_adapter(app, client, session_factory):  # noqa: ANN001
    """The response's ``adapter_type`` must carry ``agent_org_nodes.adapter_type``,
    not ``org_role``. Seeds a node whose role and adapter deliberately differ
    (a test asserting only "non-empty" would pass on the pre-fix payload)."""
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    agent_id = str(uuid.uuid4())
    async with session_factory() as session:
        session.add(
            AgentOrgNode(
                id=uuid.uuid4(),
                agent_id=agent_id,
                name="Coordinator with a Claude adapter",
                org_role=OrgRole.COORDINATOR.value,
                adapter_type="claude_code",
                company_id=company_id,
            )
        )
        await session.commit()

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    node = resp.json()["nodes"][0]
    assert node["adapter_type"] == "claude_code"
    assert node["adapter_type"] != OrgRole.COORDINATOR.value


@pytest.mark.asyncio
async def test_org_chart_adapter_type_null_is_empty_not_role(app, client, session_factory):  # noqa: ANN001
    """A NULL ``adapter_type`` renders as "" — the documented fallback — never
    the role (#14109's fix must not reintroduce the role as a fallback)."""
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    agent_id = await _seed_org_node(session_factory, company_id, name="No Adapter", role=OrgRole.SPECIALIST.value)

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    node = next(n for n in resp.json()["nodes"] if n["id"] == agent_id)
    assert node["adapter_type"] == ""


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


# ---------------------------------------------------------------------------
# Reporting lines place people and agents in ONE hierarchy (#15763).
# ---------------------------------------------------------------------------


async def _seed_person(session_factory, company_id: uuid.UUID, role: str = "member") -> uuid.UUID:  # noqa: ANN001
    """Seed one company membership and return its user id."""
    from llc.models.membership import LLCCompanyMembership

    user_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=company_id, user_id=user_id, role=role))
        await session.commit()
    return user_id


async def _seed_reporting_line(  # noqa: ANN001
    session_factory,
    company_id: uuid.UUID,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    manager_type: str,
    manager_id: uuid.UUID,
) -> None:
    from llc.models.reporting_line import LLCReportingLine

    async with session_factory() as session:
        session.add(
            LLCReportingLine(
                id=uuid.uuid4(),
                company_id=company_id,
                subject_type=subject_type,
                subject_user_id=subject_id if subject_type == "user" else None,
                subject_agent_id=subject_id if subject_type == "agent" else None,
                manager_type=manager_type,
                manager_user_id=manager_id if manager_type == "user" else None,
                manager_agent_id=manager_id if manager_type == "agent" else None,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_a_person_is_placed_under_their_manager_not_appended_as_a_root(  # noqa: ANN001
    app, client, session_factory
):
    """People join the hierarchy instead of sitting beside it (#15763).

    Before this, memberships carried no reporting edge and every person was
    appended as a root — a company with twenty people rendered twenty roots
    with the agent hierarchy alongside, unconnected.

    The manager here is an **agent** and the report is a **person**, which is
    the combination that was previously unrepresentable in either direction:
    ``agent_org_nodes.reports_to`` holds an agent slug and could never name a
    person, and nothing placed a person at all.
    """
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    agent_slug = await _seed_org_node(session_factory, company_id, name="Chief Agent")
    async with session_factory() as session:
        from sqlalchemy import select as _select  # noqa: PLC0415

        row = (await session.execute(_select(AgentOrgNode).where(AgentOrgNode.agent_id == agent_slug))).scalar_one()
        agent_pk = row.id

    person_id = await _seed_person(session_factory, company_id)
    await _seed_reporting_line(
        session_factory,
        company_id,
        subject_type="user",
        subject_id=person_id,
        manager_type="agent",
        manager_id=agent_pk,
    )

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]

    # One root, not two: the person is under the agent rather than beside it.
    assert len(nodes) == 1, nodes
    root = nodes[0]
    assert root["id"] == agent_slug
    assert len(root["children"]) == 1, root
    child = root["children"][0]
    assert child["id"] == f"user:{person_id}"
    assert child["is_human"] is True
    # The parent is the DISPLAY id. The reporting row stores the assignment
    # keyspace (AgentOrgNode.id), so a parent map built from that raw uuid
    # would render a node whose parent matches nothing and silently re-root it.
    assert child["parent_id"] == agent_slug


@pytest.mark.asyncio
async def test_a_person_with_no_reporting_line_still_appears(app, client, session_factory):  # noqa: ANN001
    """No line is not the same as no node.

    Until a CEO exists (#15770) an unplaced person has nothing to default to,
    and dropping them would lose the person entirely rather than showing them
    unplaced.
    """
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    person_id = await _seed_person(session_factory, company_id)

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]

    assert [n["id"] for n in nodes] == [f"user:{person_id}"]
    assert nodes[0]["parent_id"] is None


@pytest.mark.asyncio
async def test_another_companys_reporting_line_does_not_reparent_anyone(app, client, session_factory):  # noqa: ANN001
    """The reporting-line query is company-scoped.

    Without the filter, a line belonging to another company is loaded and
    applied here. It only bites when both ends happen to resolve in this
    chart — which is exactly what a shared user id across two companies
    produces, and it re-parents a real person using a relationship from a
    company the caller cannot see.
    """
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    app.state.tenant["org_id"] = str(mine)
    app.state.tenant["is_platform_admin"] = False

    boss_id = await _seed_person(session_factory, mine)
    # The same person is a member of both companies — the ordinary case for a
    # user who belongs to more than one.
    subject_id = await _seed_person(session_factory, mine)
    async with session_factory() as session:
        from llc.models.membership import LLCCompanyMembership

        session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=theirs, user_id=subject_id, role="member"))
        session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=theirs, user_id=boss_id, role="member"))
        await session.commit()

    # The line exists only in the OTHER company.
    await _seed_reporting_line(
        session_factory,
        theirs,
        subject_type="user",
        subject_id=subject_id,
        manager_type="user",
        manager_id=boss_id,
    )

    resp = await client.get(f"/api/llc/companies/{mine}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]

    # Both people are roots here: this company records no reporting line.
    assert {n["id"] for n in nodes} == {f"user:{boss_id}", f"user:{subject_id}"}
    assert all(n["parent_id"] is None for n in nodes), nodes
