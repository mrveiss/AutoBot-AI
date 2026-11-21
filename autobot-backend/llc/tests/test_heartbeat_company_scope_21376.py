# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The heartbeat routes are scoped to the company that owns the agent (#21376).

The real router, the real scope dependencies and a real membership table; only the runtime-state store, the
scheduler and the audit writer are faked, so a request that reaches them is the thing under test.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import heartbeat, heartbeat_controls
from api.heartbeat_scope import AgentScope, may_see_user
from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.tests import test_llc_org_chart as _org_chart
from models.agent_org import AgentOrgNode
from models.heartbeat import HeartbeatStatus
from services.audit import outcome
from user_management.models.organization import Organization

# The org-chart suite's in-memory schema fixtures, registered here by name.
engine = _org_chart.engine
session_factory = _org_chart.session_factory

_STAMP = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
_COMPANY_A = uuid.uuid4()
_COMPANY_B = uuid.uuid4()
_COMPANY_DELETED = uuid.uuid4()


def _state(agent_id: str, status: HeartbeatStatus = HeartbeatStatus.ACTIVE, paused_by: str | None = None):
    return SimpleNamespace(
        agent_id=agent_id,
        heartbeat_enabled=status == HeartbeatStatus.ACTIVE,
        status=status.value,
        paused_reason=None,
        paused_at=None,
        paused_by=paused_by,
        error_detail=None,
        error_at=None,
        error_code=None,
        heartbeat_interval_seconds=60,
        max_run_duration_seconds=3600,
        current_task_id=None,
        last_heartbeat_at=_STAMP,
        session_params={},
        extra=None,
        created_at=_STAMP,
        updated_at=_STAMP,
    )


async def _seed(session_factory):  # noqa: ANN001
    """Two companies with an agent each, a platform agent, and an admin and a plain member of company A."""
    admin_a, member_a = uuid.uuid4(), uuid.uuid4()
    async with session_factory() as session:
        session.add_all(
            Organization(id=cid, name=f"Co {i}", slug=f"co-{i}", deleted_at=deleted)
            for i, (cid, deleted) in enumerate(((_COMPANY_A, None), (_COMPANY_B, None), (_COMPANY_DELETED, _STAMP)))
        )
        session.add_all(
            [
                AgentOrgNode(id=uuid.uuid4(), agent_id="agent-gone", name="g", company_id=_COMPANY_DELETED),
                AgentOrgNode(id=uuid.uuid4(), agent_id="agent-a", name="a", company_id=_COMPANY_A),
                AgentOrgNode(id=uuid.uuid4(), agent_id="agent-b", name="b", company_id=_COMPANY_B),
                AgentOrgNode(id=uuid.uuid4(), agent_id="platform-agent", name="p", company_id=None),
            ]
        )
        for user, role in ((admin_a, MembershipRole.ADMIN), (member_a, MembershipRole.MEMBER)):
            session.add(
                LLCCompanyMembership(id=uuid.uuid4(), company_id=_COMPANY_DELETED, user_id=user, role=role.value)
            )
            session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=_COMPANY_A, user_id=user, role=role.value))
        await session.commit()
    return admin_a, member_a


@pytest.fixture
def harness(session_factory, monkeypatch):  # noqa: ANN001
    caller = {"user": None}
    audits: list = []
    states: dict = {}

    async def _record(event):
        audits.append((event.action, event.outcome))
        return True

    async def _state_for(_session, agent_id, **_kw):
        return states.setdefault(agent_id, _state(agent_id))

    async def _session():
        async with session_factory() as session:
            yield session

    async def _write(_session, state, changes):
        for column, value in changes.items():  # the state store is fake, so there is no row to commit or refresh
            setattr(state, column, value)

    get_state = AsyncMock(side_effect=_state_for)
    monkeypatch.setattr(heartbeat_controls, "_commit_changes", _write)
    names = AsyncMock(return_value="Alice A")
    monkeypatch.setattr(outcome, "record_committed", _record)
    monkeypatch.setattr(heartbeat, "_get_or_create_state", get_state)
    monkeypatch.setattr(heartbeat, "_paused_by_name", names)
    scheduler = MagicMock(disable_agent=AsyncMock(), enable_agent=AsyncMock())
    app = FastAPI()
    app.include_router(heartbeat.router, prefix="/api/heartbeat")
    app.dependency_overrides[heartbeat.get_current_user] = lambda: caller["user"]
    app.dependency_overrides[heartbeat.get_db_session] = _session
    app.dependency_overrides[heartbeat._get_scheduler] = lambda: scheduler
    return SimpleNamespace(
        client=TestClient(app),
        caller=caller,
        audits=audits,
        states=states,
        get_state=get_state,
        names=names,
        scheduler=scheduler,
    )


def _as(harness, user_id: uuid.UUID | None, role: str = "user") -> None:  # noqa: ANN001
    harness.caller["user"] = {"id": str(user_id or uuid.uuid4()), "username": "u", "role": role}


_WRITES = [
    pytest.param("pause", {"reason": "r"}, id="pause"),
    pytest.param("resume", {}, id="resume"),
    pytest.param("terminate", {"reason": "r"}, id="terminate"),
    pytest.param("error", {"error_detail": "d"}, id="error"),
    pytest.param("recover", {}, id="recover"),
]


@pytest.mark.asyncio
async def test_cross_company_read_is_404(harness, session_factory):  # noqa: ANN001
    _admin, member_a = await _seed(session_factory)
    _as(harness, member_a)
    response = harness.client.get("/api/heartbeat/agent-b/config")
    assert response.status_code == 404
    harness.get_state.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("action", "payload"), _WRITES)
async def test_cross_company_control_is_404_even_for_an_admin_of_another_company(
    harness, session_factory, action, payload  # noqa: ANN001
):
    admin_a, _member = await _seed(session_factory)
    _as(harness, admin_a)
    response = harness.client.post(f"/api/heartbeat/agent-b/{action}", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found"
    harness.get_state.assert_not_awaited()
    assert harness.audits == []
    harness.scheduler.disable_agent.assert_not_awaited()
    harness.scheduler.enable_agent.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("agent", ["no-such-agent", "platform-agent"])
async def test_unknown_and_platform_agents_are_404_for_a_company_admin(harness, session_factory, agent):  # noqa: ANN001
    admin_a, _member = await _seed(session_factory)
    _as(harness, admin_a)
    assert harness.client.get(f"/api/heartbeat/{agent}/config").status_code == 404
    assert harness.client.post(f"/api/heartbeat/{agent}/terminate", json={}).status_code == 404
    harness.get_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_platform_admin_reaches_a_platform_agent_and_any_company(harness, session_factory):  # noqa: ANN001
    await _seed(session_factory)
    _as(harness, None, role="admin")
    for agent in ("platform-agent", "agent-b"):
        assert harness.client.get(f"/api/heartbeat/{agent}/config").status_code == 200
    assert harness.client.post("/api/heartbeat/agent-b/pause", json={"reason": "r"}).status_code == 200


@pytest.mark.asyncio
async def test_same_company_admin_can_pause_resume_and_terminate(harness, session_factory):  # noqa: ANN001
    admin_a, _member = await _seed(session_factory)
    _as(harness, admin_a)
    assert harness.client.post("/api/heartbeat/agent-a/pause", json={"reason": "r"}).status_code == 200
    assert harness.client.post("/api/heartbeat/agent-a/resume", json={}).status_code == 200
    assert harness.client.post("/api/heartbeat/agent-a/terminate", json={"reason": "r"}).status_code == 200
    assert [a for a, o in harness.audits if o == "success"] == ["agent.pause", "agent.resume", "agent.terminate"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("action", "payload"), _WRITES)
async def test_a_plain_member_can_read_but_not_control(harness, session_factory, action, payload):  # noqa: ANN001
    _admin, member_a = await _seed(session_factory)
    _as(harness, member_a)
    assert harness.client.get("/api/heartbeat/agent-a/config").status_code == 200
    harness.get_state.reset_mock()
    response = harness.client.post(f"/api/heartbeat/agent-a/{action}", json=payload)
    assert response.status_code == 403
    harness.get_state.assert_not_awaited()
    assert harness.audits == []


@pytest.mark.asyncio
async def test_paused_by_name_is_shown_only_for_a_user_the_caller_may_see(harness, session_factory):  # noqa: ANN001
    admin_a, member_a = await _seed(session_factory)
    _as(harness, member_a)
    harness.states["agent-a"] = _state("agent-a", HeartbeatStatus.PAUSED, paused_by=str(admin_a))
    assert harness.client.get("/api/heartbeat/agent-a/config").json()["paused_by_name"] == "Alice A"
    harness.states["agent-a"] = _state("agent-a", HeartbeatStatus.PAUSED, paused_by=str(uuid.uuid4()))
    harness.names.reset_mock()
    assert harness.client.get("/api/heartbeat/agent-a/config").json()["paused_by_name"] is None
    harness.names.assert_not_awaited()


@pytest.mark.asyncio
async def test_may_see_user_rule(session_factory):  # noqa: ANN001
    admin_a, member_a = await _seed(session_factory)
    async with session_factory() as session:
        scope = AgentScope(company_id=_COMPANY_A, platform_admin=False)
        assert await may_see_user(session, scope, str(admin_a)) is True
        assert await may_see_user(session, scope, str(uuid.uuid4())) is False
        assert await may_see_user(session, scope, "system:budget") is False
        assert await may_see_user(session, scope, None) is False
        assert await may_see_user(session, AgentScope(None, False), str(member_a)) is False
        assert await may_see_user(session, AgentScope(None, True), str(uuid.uuid4())) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["config", "pause"])
async def test_members_of_a_soft_deleted_company_get_404(harness, session_factory, action):  # noqa: ANN001
    admin_a, member_a = await _seed(session_factory)  # both also hold a membership of the deleted company
    for user in (admin_a, member_a):
        _as(harness, user)
        if action == "config":
            response = harness.client.get("/api/heartbeat/agent-gone/config")
        else:
            response = harness.client.post("/api/heartbeat/agent-gone/pause", json={"reason": "r"})
        assert response.status_code == 404
    harness.get_state.assert_not_awaited()
    assert harness.audits == []


@pytest.mark.asyncio
async def test_platform_admin_keeps_access_to_a_soft_deleted_companys_agent(harness, session_factory):  # noqa: ANN001
    await _seed(session_factory)
    _as(harness, None, role="admin")
    assert harness.client.get("/api/heartbeat/agent-gone/config").status_code == 200
    assert harness.client.post("/api/heartbeat/agent-gone/pause", json={"reason": "r"}).status_code == 200
