# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Board approvals are enforced, not only recorded (GH#8214).

Runs the real hire route, ``ApprovalService`` and hooks against in-memory SQLite (the shared
LLC harness). Redis and the scheduler are patched at their edges.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.activity import ActorType
from llc.models.budget import LLCAgentBudget
from llc.models.enums import ApprovalStatus, ApprovalType
from llc.services.approval import ApprovalHookError, ApprovalService, ApprovalStateError
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode
from models.approval import Approval
from user_management.models.organization import Organization

_ORG = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_BOARD = uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest_asyncio.fixture
async def session_factory():  # noqa: ANN201
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    from user_management.models.base import Base

    tables = harness.loop_tables() + [Approval.__table__]
    harness._clientside_timestamps(Approval.__table__)
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        eng, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as session:
        session.add(Organization(id=_ORG, name="Co", slug="co", require_approval_for_hires=True))
        await session.commit()
    yield factory
    await eng.dispose()


class _ActivityRecorder:
    """Stands in for ``LLCActivityLogService``: the SQL write is covered by the activity-log tests (#20150)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def record(
        self, session, company_id, actor_type, actor_id, event_type, entity_type, entity_id, **kw
    ):  # noqa: ANN001, ANN201
        self.calls.append((event_type.value, actor_type, actor_id, entity_type, entity_id))


@pytest.fixture
def activity():  # noqa: ANN201
    recorder = _ActivityRecorder()
    with patch("llc.services.approval_hooks._activity", recorder):
        yield recorder


@pytest.fixture(autouse=True)
def _edges(activity):  # noqa: ANN001, ANN201
    """No Redis, no scheduler: the database effects are what these tests are about."""
    with (
        patch("llc.services.approval.get_async_redis_client", new=AsyncMock(return_value=None)),
        patch("llc.services.activity_log.get_async_redis_client", new=AsyncMock(return_value=None)),
        patch("llc.scheduler.schedule_entry.schedule_heartbeat", new_callable=AsyncMock) as sched,
    ):
        yield sched


def _app(session_factory, *, require: bool = True):  # noqa: ANN001, ANN201
    from fastapi import FastAPI

    from api.user_management.dependencies import get_current_user, require_org_context
    from llc.api import agent_hires
    from user_management.database import get_async_session
    from user_management.services import TenantContext

    app = FastAPI()
    app.include_router(agent_hires.router, prefix="/api/llc")

    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_BOARD), "auth_method": "session"}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_ORG, user_id=_BOARD, is_platform_admin=False
    )
    return app


async def _hire(session_factory, name: str = "Newbie"):  # noqa: ANN001, ANN202
    transport = httpx.ASGITransport(app=_app(session_factory))
    with (
        patch("llc.api.agent_hires.adapter_unavailable_reason", return_value=None),
        patch("llc.api.agent_hires.registered_adapter_types", return_value=["claude_code"]),
    ):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            return await client.post(
                f"/api/llc/companies/{_ORG}/agent-hires",
                json={"agent_name": name, "heartbeat_enabled": True, "heartbeat_cron": "* * * * *"},
            )


async def _rows(session_factory, model):  # noqa: ANN001, ANN202
    async with session_factory() as session:
        return list((await session.execute(select(model))).scalars().all())


async def _decide(session_factory, approval_id, decision):  # noqa: ANN001, ANN202
    """What the decide route does: decide, then commit; roll back on any failure."""
    async with session_factory() as session:
        try:
            approval = await ApprovalService().decide(
                session, approval_id=approval_id, decision=decision, decided_by=_BOARD
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await ApprovalService().finish_decision(approval)
    return approval


@pytest.mark.asyncio
async def test_hire_with_the_setting_on_creates_no_agent(session_factory, _edges) -> None:  # noqa: ANN001
    resp = await _hire(session_factory)
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "pending_approval"
    assert await _rows(session_factory, AgentOrgNode) == []
    assert await _rows(session_factory, LLCAgentBudget) == []
    _edges.assert_not_awaited()
    (approval,) = await _rows(session_factory, Approval)
    assert (approval.approval_type, approval.status) == ("hire", "pending")


@pytest.mark.asyncio
async def test_approved_hire_activates_the_agent_once(session_factory, _edges) -> None:  # noqa: ANN001
    approval_id = uuid.UUID((await _hire(session_factory)).json()["approval_id"])
    await _decide(session_factory, approval_id, ApprovalStatus.APPROVED)
    (agent,) = await _rows(session_factory, AgentOrgNode)
    assert agent.name == "Newbie" and agent.company_id == _ORG and agent.status == "available"
    assert len(await _rows(session_factory, LLCAgentBudget)) == 1
    _edges.assert_awaited_once()
    with pytest.raises(ApprovalStateError):  # a retried or double decide cannot apply it twice
        await _decide(session_factory, approval_id, ApprovalStatus.APPROVED)
    assert len(await _rows(session_factory, AgentOrgNode)) == 1


@pytest.mark.asyncio
async def test_rejected_hire_is_never_created(session_factory, _edges) -> None:  # noqa: ANN001
    approval_id = uuid.UUID((await _hire(session_factory)).json()["approval_id"])
    await _decide(session_factory, approval_id, ApprovalStatus.REJECTED)
    assert await _rows(session_factory, AgentOrgNode) == []
    _edges.assert_not_awaited()
    (approval,) = await _rows(session_factory, Approval)
    assert approval.status == "rejected"


@pytest.mark.asyncio
async def test_hire_with_the_setting_off_is_unchanged(session_factory, _edges) -> None:  # noqa: ANN001
    async with session_factory() as session:
        await session.execute(update(Organization).values(require_approval_for_hires=False))
        await session.commit()
    resp = await _hire(session_factory)
    assert resp.status_code == 201, resp.text
    assert len(await _rows(session_factory, AgentOrgNode)) == 1
    assert await _rows(session_factory, Approval) == []
    _edges.assert_awaited_once()


async def _request(session_factory, gate, payload):  # noqa: ANN001, ANN202
    async with session_factory() as session:
        approval = await ApprovalService().request_approval(
            session, company_id=_ORG, gate_type=gate, payload=payload, requested_by="agent-x", actor_user_id=_BOARD
        )
        await session.commit()
    return approval.id


async def _budget(session_factory, limit: str) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session.add(LLCAgentBudget(company_id=str(_ORG), agent_id="a1", budget_limit=Decimal(limit)))
        await session.commit()


@pytest.mark.asyncio
async def test_approved_budget_override_raises_the_limit(session_factory) -> None:  # noqa: ANN001
    await _budget(session_factory, "10")
    aid = await _request(session_factory, ApprovalType.BUDGET_OVERRIDE, {"agent_id": "a1", "budget_limit": "50"})
    with patch("llc.services.budget.BudgetService.invalidate_cache", new_callable=AsyncMock) as inval:
        await _decide(session_factory, aid, ApprovalStatus.APPROVED)
    (row,) = await _rows(session_factory, LLCAgentBudget)
    assert Decimal(str(row.budget_limit)) == Decimal("50")
    inval.assert_awaited_once_with("a1", str(_ORG))


@pytest.mark.asyncio
async def test_rejected_budget_override_changes_nothing(session_factory) -> None:  # noqa: ANN001
    await _budget(session_factory, "10")
    aid = await _request(session_factory, ApprovalType.BUDGET_OVERRIDE, {"agent_id": "a1", "budget_limit": "50"})
    await _decide(session_factory, aid, ApprovalStatus.REJECTED)
    (row,) = await _rows(session_factory, LLCAgentBudget)
    assert Decimal(str(row.budget_limit)) == Decimal("10")


@pytest.mark.asyncio
async def test_a_failing_hook_leaves_the_approval_pending(session_factory) -> None:  # noqa: ANN001
    # No budget row for the agent: the hook cannot apply, so the decision must not be recorded.
    aid = await _request(session_factory, ApprovalType.BUDGET_OVERRIDE, {"agent_id": "ghost", "budget_limit": "50"})
    with pytest.raises(ApprovalHookError):
        await _decide(session_factory, aid, ApprovalStatus.APPROVED)
    (approval,) = await _rows(session_factory, Approval)
    assert approval.status == "pending" and approval.decided_by_user is None


@pytest.mark.asyncio
async def test_sprint_close_approval_runs_the_close_flow(session_factory) -> None:  # noqa: ANN001
    sprint_id = uuid.uuid4()
    aid = await _request(session_factory, ApprovalType.SPRINT_CLOSE, {"sprint_id": str(sprint_id)})
    with patch("llc.services.sprint_autoclose.SprintAutoCloseService.execute_close", new_callable=AsyncMock) as close:
        await _decide(session_factory, aid, ApprovalStatus.APPROVED)
    close.assert_awaited_once()
    assert close.call_args.kwargs == {"sprint_id": sprint_id, "approval_id": aid, "decided_by": _BOARD}


@pytest.mark.asyncio
async def test_rejected_sprint_close_does_not_close(session_factory) -> None:  # noqa: ANN001
    aid = await _request(session_factory, ApprovalType.SPRINT_CLOSE, {"sprint_id": str(uuid.uuid4())})
    with patch("llc.services.sprint_autoclose.SprintAutoCloseService.execute_close", new_callable=AsyncMock) as close:
        await _decide(session_factory, aid, ApprovalStatus.REJECTED)
    close.assert_not_awaited()


@pytest.mark.asyncio
async def test_every_approval_mutation_writes_an_activity_row_with_the_verified_actor(
    session_factory, activity
) -> None:  # noqa: ANN001
    approval_id = uuid.UUID((await _hire(session_factory)).json()["approval_id"])
    await _decide(session_factory, approval_id, ApprovalStatus.APPROVED)
    events = {call[0]: call for call in activity.calls}
    assert {"approval.requested", "approval.approved", "agent.hired"} <= set(events)
    for event in ("approval.requested", "approval.approved", "agent.hired"):
        assert events[event][1:3] == (ActorType.USER, str(_BOARD)), event
    assert events["approval.approved"][3:] == ("approval", str(approval_id))


@pytest.mark.asyncio
async def test_a_system_request_is_the_systems_act_not_the_claimed_requesters(
    session_factory, activity
) -> None:  # noqa: ANN001
    async with session_factory() as session:
        await ApprovalService().request_approval(
            session, company_id=_ORG, gate_type=ApprovalType.STRATEGY, payload={}, requested_by=uuid.uuid4()
        )
        await session.commit()
    assert [(c[0], c[1], c[2]) for c in activity.calls] == [("approval.requested", ActorType.SYSTEM, None)]


def _board_app(session_factory, *, user_id: uuid.UUID):  # noqa: ANN001, ANN202
    """The approvals router with a real database and a real membership check."""
    from fastapi import FastAPI

    from api.user_management.dependencies import get_current_user, require_org_context
    from llc.api import approvals
    from llc.deps import get_session
    from user_management.services import TenantContext

    app = FastAPI()
    app.include_router(approvals.router, prefix="/api/llc")

    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user_id), "auth_method": "session"}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_ORG, user_id=user_id, is_platform_admin=False
    )
    return app


async def _post(app, path: str, body: dict):  # noqa: ANN001, ANN202
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        return await client.post(path, json=body)


async def _member(session_factory, user_id: uuid.UUID, role: str) -> None:  # noqa: ANN001
    from llc.models.membership import LLCCompanyMembership

    async with session_factory() as session:
        session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=_ORG, user_id=user_id, role=role))
        await session.commit()


@pytest.mark.asyncio
async def test_only_a_company_admin_may_decide(session_factory) -> None:  # noqa: ANN001
    await _budget(session_factory, "10")
    aid = await _request(session_factory, ApprovalType.BUDGET_OVERRIDE, {"agent_id": "a1", "budget_limit": "50"})
    member = uuid.uuid4()
    await _member(session_factory, member, "member")
    denied = await _post(
        _board_app(session_factory, user_id=member), f"/api/llc/approvals/{aid}/decide", {"decision": "approved"}
    )
    assert denied.status_code == 403, denied.text
    (approval,) = await _rows(session_factory, Approval)
    assert approval.status == "pending"
    (row,) = await _rows(session_factory, LLCAgentBudget)
    assert Decimal(str(row.budget_limit)) == Decimal("10")

    await _member(session_factory, _BOARD, "admin")
    with patch("llc.services.budget.BudgetService.invalidate_cache", new_callable=AsyncMock):
        ok = await _post(
            _board_app(session_factory, user_id=_BOARD), f"/api/llc/approvals/{aid}/decide", {"decision": "approved"}
        )
    assert ok.status_code == 200, ok.text
    (row,) = await _rows(session_factory, LLCAgentBudget)
    assert Decimal(str(row.budget_limit)) == Decimal("50")


@pytest.mark.asyncio
async def test_a_hook_failure_over_the_route_is_409_and_leaves_it_pending(session_factory) -> None:  # noqa: ANN001
    await _member(session_factory, _BOARD, "owner")
    aid = await _request(session_factory, ApprovalType.BUDGET_OVERRIDE, {"agent_id": "ghost", "budget_limit": "50"})
    resp = await _post(
        _board_app(session_factory, user_id=_BOARD), f"/api/llc/approvals/{aid}/decide", {"decision": "approved"}
    )
    assert resp.status_code == 409, resp.text
    (approval,) = await _rows(session_factory, Approval)
    assert approval.status == "pending"


@pytest.mark.asyncio
async def test_the_create_route_cannot_forge_what_is_executed_on_approval(session_factory) -> None:  # noqa: ANN001
    app = _board_app(session_factory, user_id=_BOARD)
    base = {"company_id": str(_ORG), "requested_by_agent_id": str(uuid.uuid4())}
    hire = await _post(app, "/api/llc/approvals", {**base, "type": "hire", "payload": {"agent_name": "x"}})
    bad = await _post(app, "/api/llc/approvals", {**base, "type": "budget_override", "payload": {"agent_id": "a1"}})
    assert (hire.status_code, bad.status_code) == (422, 422)
    assert await _rows(session_factory, Approval) == []
