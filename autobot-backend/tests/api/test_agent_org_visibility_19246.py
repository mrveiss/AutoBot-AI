# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent org router answers each caller with their own view only (#19246, CWE-862).

Every read returned every company's agents and every delegation write crossed companies.
Rule (owner decision on #19246): a platform admin sees and acts on all; anyone else sees the
agents of their member companies plus platform agents (no company), and acts on their member
companies' agents only. Outside the view an agent is "not found" (404), as in #15794.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.agent_org import router
from api.agent_org_visibility import AgentVisibility, get_agent_visibility
from api.user_management.dependencies import get_db_session, get_optional_db_session

# Registers the SQLite shims for JSONB / UUID (see test_agent_org_tenant_scope.py).
from llc.tests import _e2e_harness as harness  # noqa: F401
from models.agent_org import AgentOrgNode
from models.task_delegation import TaskDelegation
from user_management.models.base import Base

COMPANY_A = uuid.uuid4()
COMPANY_B = uuid.uuid4()
MEMBER_OF_A = AgentVisibility(is_platform_admin=False, company_ids=frozenset({COMPANY_A}))
ADMIN = AgentVisibility(is_platform_admin=True)


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [AgentOrgNode.__table__, TaskDelegation.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    made = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with made() as session:
        for agent_id, company, reports_to, role in [
            ("platform", None, None, "manager"),
            ("a-mgr", COMPANY_A, None, "manager"),
            ("a-rep", COMPANY_A, "a-mgr", "worker"),
            ("b-mgr", COMPANY_B, None, "manager"),
            ("b-rep", COMPANY_B, "b-mgr", "worker"),
        ]:
            session.add(
                AgentOrgNode(
                    id=uuid.uuid4(),
                    agent_id=agent_id,
                    name=agent_id,
                    org_role=role,
                    company_id=company,
                    reports_to=reports_to,
                )
            )
        session.add(
            TaskDelegation(id=B_DELEGATION, delegator_id="b-mgr", assignee_id="b-rep", task_description="b work")
        )
        await session.commit()
    yield made
    await engine.dispose()


B_DELEGATION = uuid.uuid4()


def _client(factory, visibility: AgentVisibility) -> httpx.AsyncClient:  # noqa: ANN001
    app = FastAPI()
    app.include_router(router, prefix="/agents")

    async def _session():  # noqa: ANN202
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _session
    app.dependency_overrides[get_optional_db_session] = _session
    app.dependency_overrides[get_agent_visibility] = lambda: visibility
    from api.user_management.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {"user_id": str(uuid.uuid4())}
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _tree_ids(nodes) -> set:  # noqa: ANN001
    return {n["agent_id"] for n in nodes} | {i for n in nodes for i in _tree_ids(n["children"])}


@pytest.mark.asyncio
async def test_status_shows_a_member_their_companies_and_platform_agents_only(factory):  # noqa: ANN001
    async with _client(factory, MEMBER_OF_A) as client:
        agents = (await client.get("/agents/status")).json()["agents"]
    assert {a["id"] for a in agents} == {"platform", "a-mgr", "a-rep"}


@pytest.mark.asyncio
async def test_status_and_tree_show_an_admin_everything(factory):  # noqa: ANN001
    async with _client(factory, ADMIN) as client:
        assert {a["id"] for a in (await client.get("/agents/status")).json()["agents"]} == {
            "platform",
            "a-mgr",
            "a-rep",
            "b-mgr",
            "b-rep",
        }
        assert _tree_ids((await client.get("/agents/org")).json()) == {"platform", "a-mgr", "a-rep", "b-mgr", "b-rep"}


@pytest.mark.asyncio
async def test_org_tree_keeps_the_members_branch_and_drops_the_other_company(factory):  # noqa: ANN001
    async with _client(factory, MEMBER_OF_A) as client:
        tree = (await client.get("/agents/org")).json()
    assert _tree_ids(tree) == {"platform", "a-mgr", "a-rep"}
    a_mgr = next(n for n in tree if n["agent_id"] == "a-mgr")
    assert [c["agent_id"] for c in a_mgr["children"]] == ["a-rep"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["chain", "reports", "activity", "delegations"])
async def test_per_agent_reads_answer_404_outside_the_view(factory, path):  # noqa: ANN001
    async with _client(factory, MEMBER_OF_A) as client:
        assert (await client.get(f"/agents/b-mgr/{path}")).status_code == 404
        assert (await client.get(f"/agents/a-mgr/{path}")).status_code == 200


@pytest.mark.asyncio
async def test_a_member_cannot_delegate_in_another_company_or_on_a_platform_agent(factory):  # noqa: ANN001
    body = {"assignee_id": "b-rep", "task_description": "x"}
    async with _client(factory, MEMBER_OF_A) as client:
        assert (await client.post("/agents/b-mgr/delegate", json=body)).status_code == 404
        cross = {"assignee_id": "b-rep", "task_description": "x"}
        assert (await client.post("/agents/a-mgr/delegate", json=cross)).status_code == 404
        on_platform = {"assignee_id": "a-rep", "task_description": "x"}
        assert (await client.post("/agents/platform/delegate", json=on_platform)).status_code == 404


@pytest.mark.asyncio
async def test_a_member_passes_the_gate_inside_their_company(factory):  # noqa: ANN001
    body = {"assignee_id": "a-rep", "task_description": "x"}
    async with _client(factory, MEMBER_OF_A) as client:
        response = await client.post("/agents/a-mgr/delegate", json=body)
    # Past the visibility gate, the delegation service's own rules decide (201, or its 400).
    assert response.status_code in (201, 400)


@pytest.mark.asyncio
async def test_a_member_cannot_escalate_or_update_another_companys_delegation(factory):  # noqa: ANN001
    async with _client(factory, MEMBER_OF_A) as client:
        assert (await client.post(f"/agents/delegations/{B_DELEGATION}/escalate")).status_code == 404
        update = await client.patch(f"/agents/delegations/{B_DELEGATION}/status", json={"status": "completed"})
        assert update.status_code == 404


@pytest.mark.asyncio
async def test_an_admin_may_update_any_delegation(factory):  # noqa: ANN001
    async with _client(factory, ADMIN) as client:
        update = await client.patch(f"/agents/delegations/{B_DELEGATION}/status", json={"status": "completed"})
    assert update.status_code == 200


# -- resolving the caller's view ------------------------------------------------------


@pytest.mark.asyncio
async def test_service_credentials_are_refused():
    with pytest.raises(HTTPException) as refused:
        await get_agent_visibility(current_user={"service": True, "role": "admin"}, session=None)
    assert refused.value.status_code == 403


@pytest.mark.asyncio
async def test_the_membership_read_transaction_is_ended_before_returning(monkeypatch):  # noqa: ANN001
    """CodeRabbit on #19286: the dependency's own session must not stay checked out after the query."""
    from testkit.fake_async_session import FakeAsyncSession

    session = FakeAsyncSession()
    commits_at_query: list = []

    async def memberships(self, session_arg, user_id):  # noqa: ANN001, ANN202
        commits_at_query.append(session_arg.commits)
        return {COMPANY_A}

    from llc.services.membership_service import MembershipService

    monkeypatch.setattr(MembershipService, "list_member_company_ids", memberships)
    await get_agent_visibility(current_user={"user_id": str(uuid.uuid4()), "role": "user"}, session=session)
    # The query ran on an open transaction, and the dependency committed after it.
    assert commits_at_query == [0] and session.commits == 1


@pytest.mark.asyncio
async def test_a_member_sees_their_memberships(monkeypatch):  # noqa: ANN001
    async def memberships(self, session, user_id):  # noqa: ANN001, ANN202
        return {COMPANY_A}

    from llc.services.membership_service import MembershipService

    monkeypatch.setattr(MembershipService, "list_member_company_ids", memberships)
    from testkit.fake_async_session import FakeAsyncSession

    view = await get_agent_visibility(
        current_user={"user_id": str(uuid.uuid4()), "role": "user"}, session=FakeAsyncSession()
    )
    assert view == MEMBER_OF_A
    assert view.can_see(None) and view.can_see(COMPANY_A) and not view.can_see(COMPANY_B)
    assert view.can_act(COMPANY_A) and not view.can_act(None) and not view.can_act(COMPANY_B)


@pytest.mark.asyncio
async def test_without_a_database_a_member_sees_platform_agents_only():
    view = await get_agent_visibility(current_user={"user_id": str(uuid.uuid4()), "role": "user"}, session=None)
    assert view.company_ids == frozenset() and view.can_see(None) and not view.can_see(COMPANY_A)


# -- review of #19269: the escalation target, limits and counts ---------------------


async def _add(factory, *rows) -> None:  # noqa: ANN001
    async with factory() as session:
        session.add_all(rows)
        await session.commit()


def _node(agent_id: str, company, reports_to: str | None) -> AgentOrgNode:  # noqa: ANN001
    return AgentOrgNode(
        id=uuid.uuid4(), agent_id=agent_id, name=agent_id, org_role="manager", company_id=company, reports_to=reports_to
    )


@pytest.mark.asyncio
async def test_a_member_cannot_escalate_to_a_platform_manager_and_nothing_is_written(factory):  # noqa: ANN001
    delegation = uuid.uuid4()
    await _add(
        factory,
        _node("a-ceo", COMPANY_A, "platform"),
        TaskDelegation(id=delegation, delegator_id="a-ceo", assignee_id="a-mgr", task_description="t"),
    )
    async with _client(factory, MEMBER_OF_A) as client:
        assert (await client.post(f"/agents/delegations/{delegation}/escalate")).status_code == 404
    async with factory() as session:
        stored = await session.get(TaskDelegation, delegation)
    assert stored.escalated_to is None
    async with _client(factory, ADMIN) as client:
        response = await client.post(f"/agents/delegations/{delegation}/escalate")
    assert response.status_code == 200
    assert response.json()["escalated_to"] == "platform"


@pytest.mark.asyncio
async def test_the_delegation_page_limit_counts_visible_rows_only(factory):  # noqa: ANN001
    # A legacy cross-company row is the newest; filtering after LIMIT 1 returned an empty page.
    await _add(
        factory, TaskDelegation(id=uuid.uuid4(), delegator_id="a-mgr", assignee_id="a-rep", task_description="mine")
    )
    await _add(
        factory, TaskDelegation(id=uuid.uuid4(), delegator_id="a-mgr", assignee_id="b-rep", task_description="legacy")
    )
    async with _client(factory, MEMBER_OF_A) as client:
        page = (await client.get("/agents/a-mgr/delegations", params={"limit": 1})).json()
    assert [d["assignee_id"] for d in page] == ["a-rep"]


@pytest.mark.asyncio
async def test_the_activity_summary_counts_visible_assignees_only(factory):  # noqa: ANN001
    await _add(
        factory,
        TaskDelegation(id=uuid.uuid4(), delegator_id="a-mgr", assignee_id="a-rep", task_description="mine"),
        TaskDelegation(id=uuid.uuid4(), delegator_id="a-mgr", assignee_id="b-rep", task_description="legacy"),
    )
    async with _client(factory, MEMBER_OF_A) as client:
        assert (await client.get("/agents/a-mgr/activity")).json()["total_delegated"] == 1
    async with _client(factory, ADMIN) as client:
        assert (await client.get("/agents/a-mgr/activity")).json()["total_delegated"] == 2
