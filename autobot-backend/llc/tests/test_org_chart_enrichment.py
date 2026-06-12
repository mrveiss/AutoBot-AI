# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Org-chart enrichment tests: assigned_item_count + budget_mode (GH#9861).

Uses the same in-memory SQLite harness as test_llc_org_chart.py.  Tests focus
on the two new fields added to OrgChartNode in this issue:
  - assigned_item_count: count of non-terminal work items assigned to each agent
  - budget_spent/budget_total: reflects token numbers for token-mode agents
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
from llc.models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem

# Importing the harness registers the SQLite compile shims (must happen before
# any model-level code runs, including the work_item import below).
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode, OrgRole

_FIXED_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


# ---------------------------------------------------------------------------
# Fixtures (identical to test_llc_org_chart.py, separate engine per test).
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def app(session_factory):  # noqa: ANN001, ANN201
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

    tenant = {"org_id": None, "is_platform_admin": True}

    def _override_current_user() -> dict:
        return {
            "id": str(_FIXED_USER_ID),
            "user_id": str(_FIXED_USER_ID),
            "username": "tester",
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
# Seed helpers
# ---------------------------------------------------------------------------


async def _seed_org_node(
    session_factory,  # noqa: ANN001
    company_id: uuid.UUID,
    *,
    name: str,
    reports_to: Optional[str] = None,
) -> tuple[str, str]:
    """Seed an AgentOrgNode and return ``(node_pk, agent_slug)``.

    The slug is deliberately a non-UUID string (hire-flow shape,
    ``assistant-...-{hex8}``) and DISTINCT from the PK, so a join that
    mistakenly matches ``assignee_agent_id`` against the slug column
    returns zero rows and fails the test (GH#10032 dual-keyspace trap).
    Work-item assignments must use the PK; budget rows, ``reports_to``
    and org-chart node ids use the slug.
    """
    node_id = uuid.uuid4()
    agent_slug = f"assistant-test-{node_id.hex[:8]}"
    async with session_factory() as session:
        session.add(
            AgentOrgNode(
                id=node_id,
                agent_id=agent_slug,
                name=name,
                org_role=OrgRole.WORKER.value,
                title=None,
                reports_to=reports_to,
                company_id=company_id,
            )
        )
        await session.commit()
    return str(node_id), agent_slug


_item_counter = 0


async def _seed_work_item(
    session_factory,  # noqa: ANN001
    company_id: uuid.UUID,
    *,
    assignee_agent_id: Optional[str] = None,
    status: str = WorkItemStatus.IN_PROGRESS.value,
) -> uuid.UUID:
    global _item_counter
    _item_counter += 1
    item_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            LLCWorkItem(
                id=item_id,
                company_id=company_id,
                identifier=f"WI-{_item_counter}",
                type=WorkItemType.TASK.value,
                title=f"Test item {_item_counter}",
                status=status,
                priority=WorkItemPriority.MEDIUM.value,
                version=1,
                labels=[],
                assignee_agent_id=uuid.UUID(assignee_agent_id) if assignee_agent_id else None,
            )
        )
        await session.commit()
    return item_id


async def _seed_budget(
    session_factory,  # noqa: ANN001
    company_id: uuid.UUID,
    agent_id: str,
    *,
    budget_mode: str = "dollars",
    budget_limit: str = "100.00",
    budget_spent: str = "0.00",
    token_limit: Optional[int] = None,
    tokens_spent: int = 0,
) -> None:
    async with session_factory() as session:
        session.add(
            LLCAgentBudget(
                id=uuid.uuid4(),
                company_id=str(company_id),
                agent_id=agent_id,
                budget_mode=budget_mode,
                budget_limit=Decimal(budget_limit),
                budget_spent=Decimal(budget_spent),
                token_limit=token_limit,
                tokens_spent=tokens_spent,
                alert_threshold=0.8,
            )
        )
        await session.commit()


def _node_by_id(nodes: list, agent_id: str) -> dict:
    for node in nodes:
        if node["id"] == agent_id:
            return node
        try:
            return _node_by_id(node.get("children", []), agent_id)
        except KeyError:
            pass
    raise KeyError(f"agent_id {agent_id!r} not found in org-chart response")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assigned_item_count_reflects_active_assignments(app, client, session_factory):  # noqa: ANN001
    """assigned_item_count counts only non-terminal items assigned to the agent."""
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    node_pk, agent_id = await _seed_org_node(session_factory, company_id, name="Worker")

    # Two active items assigned to the agent.
    await _seed_work_item(session_factory, company_id, assignee_agent_id=node_pk, status="in_progress")
    await _seed_work_item(session_factory, company_id, assignee_agent_id=node_pk, status="ready")
    # One terminal item — must NOT count.
    await _seed_work_item(session_factory, company_id, assignee_agent_id=node_pk, status="done")

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]
    node = _node_by_id(nodes, agent_id)
    assert node["assigned_item_count"] == 2


@pytest.mark.asyncio
async def test_assigned_item_count_zero_for_unassigned_agent(app, client, session_factory):  # noqa: ANN001
    """An agent with no assigned items returns assigned_item_count=0."""
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    _node_pk, agent_id = await _seed_org_node(session_factory, company_id, name="Idle Worker")

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]
    node = _node_by_id(nodes, agent_id)
    assert node["assigned_item_count"] == 0


@pytest.mark.asyncio
async def test_assigned_item_count_no_cross_agent_contamination(app, client, session_factory):  # noqa: ANN001
    """Items assigned to agent A do not affect agent B's count."""
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    pk_a, agent_a = await _seed_org_node(session_factory, company_id, name="Agent A")
    _pk_b, agent_b = await _seed_org_node(session_factory, company_id, name="Agent B")

    # Three items for A, zero for B.
    for _ in range(3):
        await _seed_work_item(session_factory, company_id, assignee_agent_id=pk_a, status="in_progress")

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]

    assert _node_by_id(nodes, agent_a)["assigned_item_count"] == 3
    assert _node_by_id(nodes, agent_b)["assigned_item_count"] == 0


@pytest.mark.asyncio
async def test_token_mode_budget_exposes_token_numbers(app, client, session_factory):  # noqa: ANN001
    """For token-mode agents with token_limit set, budget fields expose token counts."""
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    _node_pk, agent_id = await _seed_org_node(session_factory, company_id, name="Token Agent")
    await _seed_budget(
        session_factory,
        company_id,
        agent_id,
        budget_mode="tokens",
        token_limit=50000,
        tokens_spent=12345,
        budget_limit="0.00",
        budget_spent="0.00",
    )

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]
    node = _node_by_id(nodes, agent_id)

    assert node["budget_total"] == 50000.0
    assert node["budget_spent"] == 12345.0


@pytest.mark.asyncio
async def test_dollar_mode_budget_preserves_dollar_amounts(app, client, session_factory):  # noqa: ANN001
    """For dollar-mode agents, budget_spent/budget_total are the dollar amounts."""
    company_id = uuid.uuid4()
    app.state.tenant["org_id"] = str(company_id)
    app.state.tenant["is_platform_admin"] = False

    _node_pk, agent_id = await _seed_org_node(session_factory, company_id, name="Dollar Agent")
    await _seed_budget(
        session_factory,
        company_id,
        agent_id,
        budget_mode="dollars",
        budget_limit="200.00",
        budget_spent="75.50",
        tokens_spent=99,
    )

    resp = await client.get(f"/api/llc/companies/{company_id}/org-chart")
    assert resp.status_code == 200, resp.text
    nodes = resp.json()["nodes"]
    node = _node_by_id(nodes, agent_id)

    assert node["budget_total"] == 200.0
    assert node["budget_spent"] == 75.5
