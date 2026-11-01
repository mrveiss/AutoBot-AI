# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every inserter, requester and post-commit step around the #8214 approval gate (review of 93ac3b8c71)."""

# flake8: noqa: F811 -- fixtures imported from the support module are re-bound as parameters
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.enums import ApprovalStatus, ApprovalType
from llc.services.approval import ApprovalHookError, ApprovalService
from llc.tests.approval_enforcement_support_test import _edges  # noqa: F401 -- autouse fixture
from llc.tests.approval_enforcement_support_test import activity  # noqa: F401 -- fixture
from llc.tests.approval_enforcement_support_test import session_factory  # noqa: F401 -- fixture
from llc.tests.approval_enforcement_support_test import (  # noqa: F401
    _BOARD,
    _ORG,
    _app,
    _board_app,
    _budget,
    _decide,
    _hire,
    _member,
    _post,
    _request,
    _rows,
)
from models.agent_org import AgentOrgNode
from models.approval import Approval
from user_management.models.organization import Organization

# ---------------------------------------------------------------------------
# Every other way an agent node can appear (review of 93ac3b8c71)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_new_org_node_in_a_gated_company_is_refused_but_a_reporting_line_edit_is_not(
    session_factory,
) -> None:  # noqa: ANN001
    from llc.services.agent_hire_service import HireApprovalRequiredError
    from services.agent_org_service import AgentOrgService

    async with session_factory() as session:
        svc = AgentOrgService(session)
        with pytest.raises(HireApprovalRequiredError):
            await svc.upsert_node("sneaky", "Sneaky", company_id=_ORG)
        assert await _rows(session_factory, AgentOrgNode) == []

        session.add(AgentOrgNode(id=uuid.uuid4(), agent_id="boss", name="Boss", company_id=_ORG))
        session.add(AgentOrgNode(id=uuid.uuid4(), agent_id="dev", name="Dev", company_id=_ORG))
        await session.flush()
        with patch("llc.kb.AgentCapabilityIndexer"):
            node = await svc.upsert_node("dev", "Dev", reports_to="boss", company_id=_ORG)
    assert node.reports_to == "boss"


@pytest.mark.asyncio
async def test_a_new_org_node_in_an_ungated_company_is_still_created(session_factory) -> None:  # noqa: ANN001
    from services.agent_org_service import AgentOrgService

    async with session_factory() as session:
        await session.execute(update(Organization).values(require_approval_for_hires=False))
        with patch("llc.kb.AgentCapabilityIndexer"):
            node = await AgentOrgService(session).upsert_node("fresh", "Fresh", company_id=_ORG)
    assert node.agent_id == "fresh"


@pytest.mark.asyncio
async def test_the_org_route_answers_409_for_a_new_node_in_a_gated_company(session_factory) -> None:  # noqa: ANN001
    from fastapi import FastAPI

    from api import agent_org
    from api.user_management.dependencies import get_db_session, require_reporting_line_write
    from user_management.services import TenantContext

    app = FastAPI()
    app.include_router(agent_org.router, prefix="/api/agents")

    async def _session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _session
    app.dependency_overrides[agent_org.get_current_user] = lambda: {"id": str(_BOARD)}
    app.dependency_overrides[require_reporting_line_write] = lambda: TenantContext(
        org_id=_ORG, user_id=_BOARD, is_platform_admin=False
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put("/api/agents/sneaky/org", json={"name": "Sneaky", "org_role": "worker"})
    assert resp.status_code == 409, resp.text
    assert "agent-hires" in resp.json()["detail"]


def _template(agents: list, *, require: bool) -> dict:
    return {
        "schema_version": "1.0",
        "company": {"name": "Imp", "slug": "imp", "require_approval_for_hires": require},
        "agents": agents,
        "goals": [],
        "projects": [],
        "work_items": [],
    }


def _import_patches():  # noqa: ANN202
    """The import's agent insert is raw Postgres SQL; stub the insert and the CEO/link steps around it."""
    from contextlib import ExitStack

    stack = ExitStack()
    insert = stack.enter_context(
        patch("llc.services.portability.PortabilityService._import_agent", new=AsyncMock(return_value="new-agent"))
    )
    stack.enter_context(patch("llc.services.portability.mint_agent_ids", new=AsyncMock(return_value={})))
    stack.enter_context(patch("llc.services.portability.settle_imported_ceo", new=AsyncMock()))
    stack.enter_context(patch("llc.services.portability.PortabilityService._link_reporting_lines", new=AsyncMock()))
    return stack, insert


@pytest.mark.asyncio
async def test_an_import_that_creates_its_own_gated_company_is_the_bootstrap_and_is_allowed(
    session_factory,
) -> None:  # noqa: ANN001
    from llc.services.portability import PortabilityService

    stack, insert = _import_patches()
    async with session_factory() as session:
        with stack:
            result = await PortabilityService(session=session).execute_import(
                _template([{"name": "A", "agent_id": "a"}], require=True)
            )
    insert.assert_awaited_once()
    assert result["created_entities"]["agents"] == ["new-agent"]


@pytest.mark.asyncio
async def test_an_import_of_agents_into_an_existing_gated_company_is_refused(session_factory) -> None:  # noqa: ANN001
    from llc.services.portability import ImportNeedsApprovalError, PortabilityService

    stack, insert = _import_patches()
    stack.enter_context(patch.object(PortabilityService, "_agent_names_exist", AsyncMock(return_value=[])))
    async with session_factory() as session:
        with stack, pytest.raises(ImportNeedsApprovalError):
            await PortabilityService(session=session).execute_import(
                _template([{"name": "A", "agent_id": "a"}], require=False), target_company_id=_ORG
            )
        insert.assert_not_awaited()
        # no agents in the template: nothing to approve, so it is not refused
        with stack:
            await PortabilityService(session=session).execute_import(
                _template([], require=False), target_company_id=_ORG
            )


@pytest.mark.asyncio
async def test_the_default_ceo_is_exempt_from_the_hire_gate(session_factory) -> None:  # noqa: ANN001
    from llc.services.company_ceo import CompanyCEOService

    async with session_factory() as session:
        agent = await CompanyCEOService()._get_or_create_default_agent(session, _ORG)
    assert agent.company_id == _ORG


# ---------------------------------------------------------------------------
# Requesters: one validation for every caller
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_approval_refuses_a_payload_that_could_never_be_executed(session_factory) -> None:  # noqa: ANN001
    async with session_factory() as session:
        for gate, payload in (
            (ApprovalType.HIRE, {"summary": "hire a CTO"}),
            (ApprovalType.BUDGET_OVERRIDE, {"agent_id": "a1"}),
            (ApprovalType.SPRINT_CLOSE, {"sprint_id": "not-a-uuid"}),
        ):
            with pytest.raises(ApprovalHookError):
                await ApprovalService().request_approval(
                    session, company_id=_ORG, gate_type=gate, payload=payload, requested_by="x"
                )
    assert await _rows(session_factory, Approval) == []


@pytest.mark.asyncio
async def test_the_chat_tool_cannot_request_a_gate_that_executes(session_factory) -> None:  # noqa: ANN001
    from llc.agent_tools import LLCToolError, _request_approval

    async with session_factory() as session:
        for gate in ("hire", "budget_override", "sprint_close"):
            with pytest.raises(LLCToolError, match="cannot be requested from chat"):
                await _request_approval(session, str(_ORG), str(_BOARD), {"summary": "do it", "gate_type": gate})
        ok = await _request_approval(session, str(_ORG), str(_BOARD), {"summary": "pivot", "gate_type": "strategy"})
    assert ok["entity_type"] == "approval"


@pytest.mark.asyncio
async def test_a_hire_without_a_verified_user_is_refused_not_attributed_to_none(
    session_factory,
) -> None:  # noqa: ANN001
    from api.user_management.dependencies import require_org_context
    from user_management.services import TenantContext

    app = _app(session_factory)
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_ORG, user_id=None, is_platform_admin=False
    )
    with (
        patch("llc.api.agent_hires.adapter_unavailable_reason", return_value=None),
        patch("llc.api.agent_hires.registered_adapter_types", return_value=["claude_code"]),
    ):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(f"/api/llc/companies/{_ORG}/agent-hires", json={"agent_name": "X"})
    assert resp.status_code == 403
    assert await _rows(session_factory, Approval) == []


# ---------------------------------------------------------------------------
# Sprint close: the KB step follows the commit; every hook failure is one path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sprint_kb_summary_runs_after_the_commit_not_in_the_decision(session_factory) -> None:  # noqa: ANN001
    aid = await _request(session_factory, ApprovalType.SPRINT_CLOSE, {"sprint_id": str(uuid.uuid4())})
    order: list[str] = []

    async def _close(*a, **kw):  # noqa: ANN002, ANN003
        order.append("close")

    async def _summary(self, sprint_id):  # noqa: ANN001
        order.append("summary")

    with (
        patch("llc.services.sprint_autoclose.SprintAutoCloseService.execute_close", new=_close),
        patch("llc.services.sprint_autoclose.SprintAutoCloseService.summarize_closed_sprint", new=_summary),
    ):
        async with session_factory() as session:
            await ApprovalService().decide(
                session, approval_id=aid, decision=ApprovalStatus.APPROVED, decided_by=_BOARD
            )
            assert order == ["close"]  # the decision alone never reaches the KB
            await session.rollback()
        (approval,) = await _rows(session_factory, Approval)
        assert approval.status == "pending" and order == ["close"]  # rolled back: no KB work happened
        await _decide(session_factory, aid, ApprovalStatus.APPROVED)
    await asyncio.sleep(0)  # the summary runs as a background task
    assert order == ["close", "close", "summary"]


@pytest.mark.asyncio
async def test_any_hook_failure_is_one_clear_error_and_leaves_the_approval_pending(
    session_factory,
) -> None:  # noqa: ANN001
    aid = await _request(session_factory, ApprovalType.SPRINT_CLOSE, {"sprint_id": str(uuid.uuid4())})
    boom = AsyncMock(side_effect=RuntimeError("kb down"))
    with patch("llc.services.sprint_autoclose.SprintAutoCloseService.execute_close", new=boom):
        with pytest.raises(ApprovalHookError, match="RuntimeError"):
            await _decide(session_factory, aid, ApprovalStatus.APPROVED)
    (approval,) = await _rows(session_factory, Approval)
    assert approval.status == "pending"


@pytest.mark.asyncio
async def test_execute_close_no_longer_summarises_in_the_close_transaction() -> None:
    import inspect

    from llc.services.sprint_autoclose import SprintAutoCloseService

    assert "summarize_and_merge" not in inspect.getsource(SprintAutoCloseService.execute_close)


# ---------------------------------------------------------------------------
# Pending count, and hire-type coverage at service and route level
# ---------------------------------------------------------------------------


async def _get(app, path: str):  # noqa: ANN001, ANN202
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_pending_count_counts_only_this_companys_pending_approvals(session_factory) -> None:  # noqa: ANN001
    await _request(session_factory, ApprovalType.STRATEGY, {})
    done = await _request(session_factory, ApprovalType.STRATEGY, {})
    await _decide(session_factory, done, ApprovalStatus.REJECTED)
    async with session_factory() as session:
        await ApprovalService().request_approval(
            session, company_id=uuid.uuid4(), gate_type=ApprovalType.STRATEGY, payload={}, requested_by="x"
        )
        await session.commit()
    app = _board_app(session_factory, user_id=_BOARD)
    ok = await _get(app, f"/api/llc/companies/{_ORG}/approvals/pending-count")
    assert ok.status_code == 200 and ok.json()["pending"] == 1, ok.text
    other = await _get(app, f"/api/llc/companies/{uuid.uuid4()}/approvals/pending-count")
    assert other.status_code == 404


@pytest.mark.asyncio
async def test_a_hire_approved_over_the_decide_route_is_activated_and_scheduled(
    session_factory, _edges
) -> None:  # noqa: ANN001
    approval_id = (await _hire(session_factory)).json()["approval_id"]
    await _member(session_factory, _BOARD, "owner")
    resp = await _post(
        _board_app(session_factory, user_id=_BOARD),
        f"/api/llc/approvals/{approval_id}/decide",
        {"decision": "approved"},
    )
    assert resp.status_code == 200, resp.text
    assert len(await _rows(session_factory, AgentOrgNode)) == 1
    _edges.assert_awaited_once()  # the real finish_decision ran: the schedule entry follows the commit


@pytest.mark.asyncio
async def test_a_hire_approval_of_another_company_is_not_found_for_a_foreign_board(
    session_factory,
) -> None:  # noqa: ANN001
    approval_id = (await _hire(session_factory)).json()["approval_id"]
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
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_BOARD), "auth_method": "session"}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.uuid4(), user_id=_BOARD, is_platform_admin=False
    )
    resp = await _post(app, f"/api/llc/approvals/{approval_id}/decide", {"decision": "approved"})
    assert resp.status_code == 404
    assert await _rows(session_factory, AgentOrgNode) == []


@pytest.mark.asyncio
async def test_a_service_level_hire_request_with_a_valid_payload_is_accepted(session_factory) -> None:  # noqa: ANN001
    payload = {
        "agent_id": str(uuid.uuid4()),
        "agent_name": "N",
        "org_role": "worker",
        "adapter_config": {},
        "model": "m",
        "instructions_file_path": "/x",
    }
    aid = await _request(session_factory, ApprovalType.HIRE, payload)
    assert aid is not None


@pytest.mark.asyncio
async def test_a_slow_kb_summary_does_not_hold_the_decision_open(session_factory) -> None:  # noqa: ANN001
    aid = await _request(session_factory, ApprovalType.SPRINT_CLOSE, {"sprint_id": str(uuid.uuid4())})
    release, finished = asyncio.Event(), asyncio.Event()

    async def _slow(self, sprint_id):  # noqa: ANN001
        await release.wait()
        finished.set()

    with (
        patch("llc.services.sprint_autoclose.SprintAutoCloseService.execute_close", new=AsyncMock()),
        patch("llc.services.sprint_autoclose.SprintAutoCloseService.summarize_closed_sprint", new=_slow),
    ):
        await asyncio.wait_for(_decide(session_factory, aid, ApprovalStatus.APPROVED), timeout=5)
        assert not finished.is_set()  # the decision returned while the summary is still running
        release.set()
        await asyncio.wait_for(finished.wait(), timeout=5)


def test_the_409_hint_names_the_company_not_a_template() -> None:
    from llc.services.agent_hire_service import HireApprovalRequiredError

    cid = uuid.uuid4()
    message = str(HireApprovalRequiredError(cid))
    assert f"/companies/{cid}/agent-hires" in message and "{company_id}" not in message


@pytest.mark.asyncio
async def test_a_token_limited_budget_cannot_take_a_dollar_override(session_factory) -> None:  # noqa: ANN001
    from llc.models.budget import LLCAgentBudget

    async with session_factory() as session:
        session.add(
            LLCAgentBudget(
                company_id=str(_ORG), agent_id="a1", budget_limit=Decimal("10"), budget_mode="tokens", token_limit=1000
            )
        )
        await session.commit()
    aid = await _request(session_factory, ApprovalType.BUDGET_OVERRIDE, {"agent_id": "a1", "budget_limit": "50"})
    with pytest.raises(ApprovalHookError, match="token-limited"):
        await _decide(session_factory, aid, ApprovalStatus.APPROVED)
    (approval,) = await _rows(session_factory, Approval)
    assert approval.status == "pending"


@pytest.mark.asyncio
async def test_an_import_whose_agents_all_exist_adds_no_hire_and_is_not_refused(
    session_factory,
) -> None:  # noqa: ANN001
    from llc.services.portability import ImportNeedsApprovalError, PortabilityService

    stack, insert = _import_patches()
    names = AsyncMock(return_value=["A"])
    async with session_factory() as session:
        svc = PortabilityService(session=session)
        with stack, patch.object(PortabilityService, "_agent_names_exist", names):
            await svc.execute_import(_template([{"name": "A", "agent_id": "a"}], require=False), target_company_id=_ORG)
            with pytest.raises(ImportNeedsApprovalError):  # one name is new: that one IS a hire
                await svc.execute_import(
                    _template([{"name": "A", "agent_id": "a"}, {"name": "B", "agent_id": "b"}], require=False),
                    target_company_id=_ORG,
                )
