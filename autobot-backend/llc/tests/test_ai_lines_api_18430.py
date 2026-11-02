# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The AI-lines API and the approval that changes a line, end to end (#18430).

Real routes, a real (in-memory) store and the real LLC decide route. What each test pins:

* reading and proposing are company-scoped (another company's caller gets 404);
* an agent credential cannot propose a change (403) and a proposal changes NOTHING by itself;
* a line moves only when an owner or admin of THAT company approves the request;
* the approval is decided through the LLC route, which now runs what the approval proposed.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api.ai_lines import router as ai_lines_router
from llc.api.approvals import router as approvals_router
from llc.deps import get_session
from llc.models.activity import LLCActivityLog
from llc.models.ai_line import LLCAiLine
from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.tests import _e2e_harness as harness
from models.agent_org import AgentOrgNode
from models.approval import Approval, ApprovalComment, TaskApprovalLink
from user_management.models.base import Base
from user_management.services import TenantContext

COMPANY, OTHER = uuid.uuid4(), uuid.uuid4()
OWNER, MEMBER, AGENT, ADMIN2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
AGENT_USER = uuid.uuid4()  # a signed-in person who is nobody's victim
PERSON = {"auth_method": "session"}
AGENT_CREDENTIAL = {"auth_method": "run_jwt", "username": "run:abc"}


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    tables = [
        LLCActivityLog.__table__,  # #8214: every decision writes an activity row
        Approval.__table__,
        ApprovalComment.__table__,
        TaskApprovalLink.__table__,
        LLCAiLine.__table__,
        LLCCompanyMembership.__table__,
        AgentOrgNode.__table__,  # #19582: a decision wakes the requesting agent, looked up here
    ]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as session:
        for user, role in ((OWNER, MembershipRole.OWNER), (MEMBER, MembershipRole.MEMBER)):
            session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=COMPANY, user_id=user, role=role.value))
        await session.commit()
    yield maker
    await engine.dispose()


def _client(factory, *, user: uuid.UUID, org: uuid.UUID = COMPANY, credential: dict = PERSON) -> TestClient:
    app = FastAPI()
    app.include_router(ai_lines_router, prefix="/api/llc")
    app.include_router(approvals_router, prefix="/api/llc")

    async def _session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user), "username": "person", **credential}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(org_id=org, user_id=user)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _outside_world(factory):
    audit = AsyncMock(return_value=True)
    with (
        patch("services.ai_line_change_proposal.get_async_session_factory", lambda: factory),
        patch("services.ai_line_change_action.audit_log", audit),
        patch("services.ai_line_view.gated_categories", AsyncMock(return_value=["writing files"])),
        patch("events.bus.publish_event", AsyncMock()),
        patch("llc.api.approvals.ApprovalService.publish_decided", AsyncMock()),
        patch("llc.api.approvals.ApprovalService.log_decision_to_kb", AsyncMock()),
    ):
        yield audit


async def _rows(factory, model):
    async with factory() as session:
        return list((await session.execute(sa.select(model))).scalars().all())


def _propose(client, key="crm:send", line="autonomous", company=COMPANY):
    return client.post(f"/api/llc/ai-lines/{company}/changes", json={"action_key": key, "line": line})


def _decide(client, approval_id: str, decision="approved"):
    return client.post(f"/api/llc/approvals/{approval_id}/decide", json={"decision": decision})


# -- read ----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reading_the_lines_shows_every_mutating_tool_as_line_two_and_a_stored_line(factory):
    async with factory() as session:
        session.add(LLCAiLine(id=uuid.uuid4(), company_id=COMPANY, action_key="crm:read", line="autonomous"))
        session.add(LLCAiLine(id=uuid.uuid4(), company_id=OTHER, action_key="crm:delete", line="never"))
        await session.commit()
    body = _client(factory, user=OWNER).get(f"/api/llc/ai-lines/{COMPANY}").json()
    by_key = {e["action_key"]: e for e in body["entries"]}
    assert body["default_line"] == "draft_then_send"
    assert by_key["crm:read"]["effective_line"] == "autonomous" and by_key["crm:read"]["is_set"]
    assert by_key["write_file"]["effective_line"] == "draft_then_send" and not by_key["write_file"]["is_set"]
    assert "crm:delete" not in by_key  # another company's line


@pytest.mark.asyncio
async def test_a_stored_autonomous_line_in_a_baseline_category_is_shown_as_line_two_with_the_reason(factory):
    async with factory() as session:
        session.add(LLCAiLine(id=uuid.uuid4(), company_id=COMPANY, action_key="write_file", line="autonomous"))
        await session.commit()
    entry = next(
        e
        for e in _client(factory, user=OWNER).get(f"/api/llc/ai-lines/{COMPANY}").json()["entries"]
        if e["action_key"] == "write_file"
    )
    assert entry["stored_line"] == "autonomous" and entry["effective_line"] == "draft_then_send"
    assert entry["floor_category"] == "writing files" and "baseline" in entry["reason"]


@pytest.mark.asyncio
async def test_another_companys_caller_cannot_read_the_lines(factory):
    assert _client(factory, user=OWNER, org=OTHER).get(f"/api/llc/ai-lines/{COMPANY}").status_code == 404


# -- propose ------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_proposal_files_an_approval_and_changes_nothing(factory):
    resp = _propose(_client(factory, user=MEMBER))
    assert resp.status_code == 202 and resp.json()["status"] == "pending"
    [approval] = await _rows(factory, Approval)
    assert approval.company_id == COMPANY and approval.context["line"] == "autonomous"
    assert await _rows(factory, LLCAiLine) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("credential", [AGENT_CREDENTIAL, {"auth_method": "api_key"}, {"service": True}])
async def test_an_agent_credential_cannot_propose_a_line_change(factory, credential):
    resp = _propose(_client(factory, user=AGENT, credential=credential))
    assert resp.status_code == 403
    assert await _rows(factory, Approval) == [] and await _rows(factory, LLCAiLine) == []


@pytest.mark.asyncio
async def test_a_proposal_for_another_company_is_refused(factory):
    assert _propose(_client(factory, user=OWNER, org=OTHER)).status_code == 404
    assert await _rows(factory, Approval) == []


@pytest.mark.asyncio
async def test_a_malformed_key_or_unknown_line_is_rejected(factory):
    client = _client(factory, user=OWNER)
    assert _propose(client, key="crm send!").status_code == 422
    assert _propose(client, line="allow-all").status_code == 422
    assert await _rows(factory, Approval) == []


# -- approve: the only way a line moves --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_owners_approval_sets_the_line(factory):
    approval_id = _propose(_client(factory, user=MEMBER)).json()["approval_id"]
    assert _decide(_client(factory, user=OWNER), approval_id).status_code == 200
    [row] = await _rows(factory, LLCAiLine)
    assert (row.company_id, row.action_key, row.line) == (COMPANY, "crm:send", "autonomous")
    assert row.decided_by == str(OWNER) and str(row.approval_id) == approval_id
    entries = _client(factory, user=OWNER).get(f"/api/llc/ai-lines/{COMPANY}").json()["entries"]
    entry = next(e for e in entries if e["action_key"] == "crm:send")
    assert entry["is_set"] and entry["effective_line"] == "autonomous"


@pytest.mark.asyncio
async def test_a_rejected_proposal_changes_nothing(factory):
    approval_id = _propose(_client(factory, user=MEMBER)).json()["approval_id"]
    assert _decide(_client(factory, user=OWNER), approval_id, "rejected").status_code == 200
    assert await _rows(factory, LLCAiLine) == []


@pytest.mark.asyncio
async def test_a_plain_member_approving_does_not_move_the_line(factory):
    approval_id = _propose(_client(factory, user=MEMBER)).json()["approval_id"]
    assert _decide(_client(factory, user=MEMBER), approval_id).status_code == 403  # #8214: decide is board-only
    assert await _rows(factory, LLCAiLine) == []


@pytest.mark.asyncio
async def test_an_agent_credential_cannot_decide_the_proposal(factory):
    approval_id = _propose(_client(factory, user=OWNER)).json()["approval_id"]
    assert _decide(_client(factory, user=AGENT, credential=AGENT_CREDENTIAL), approval_id).status_code == 403
    assert await _rows(factory, LLCAiLine) == []


@pytest.mark.asyncio
async def test_approving_twice_does_not_rewrite_or_duplicate_the_line(factory):
    client = _client(factory, user=OWNER)
    approval_id = _propose(client).json()["approval_id"]
    assert _decide(client, approval_id).status_code == 200
    assert _decide(client, approval_id).status_code == 409
    assert len(await _rows(factory, LLCAiLine)) == 1


# -- four eyes (owner decision, #18430) ------------------------------------------------------------------------


async def _add_admin(factory, user, role=MembershipRole.ADMIN):
    async with factory() as session:
        session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=COMPANY, user_id=user, role=role.value))
        await session.commit()


@pytest.mark.asyncio
async def test_a_self_approval_with_two_or_more_admins_is_refused(factory):
    await _add_admin(factory, ADMIN2)
    owner = _client(factory, user=OWNER)
    approval_id = _propose(owner).json()["approval_id"]
    assert _decide(owner, approval_id).status_code == 200  # the decision is recorded ...
    assert await _rows(factory, LLCAiLine) == []  # ... the line does not move
    assert any("did not complete" in c.body for c in await _rows(factory, ApprovalComment))


@pytest.mark.asyncio
async def test_a_self_approval_by_the_only_admin_is_allowed_and_flagged(factory, _outside_world):
    owner = _client(factory, user=OWNER)  # the fixture company has exactly one owner/admin
    approval_id = _propose(owner).json()["approval_id"]
    assert _decide(owner, approval_id).status_code == 200
    [row] = await _rows(factory, LLCAiLine)
    assert row.decided_by == str(OWNER)
    assert _outside_world.await_args.kwargs["details"]["self_approval"] is True
    assert any("self-approved" in c.body for c in await _rows(factory, ApprovalComment))


@pytest.mark.asyncio
async def test_another_admin_approving_is_allowed_and_not_flagged(factory, _outside_world):
    await _add_admin(factory, ADMIN2)
    approval_id = _propose(_client(factory, user=OWNER)).json()["approval_id"]
    assert _decide(_client(factory, user=ADMIN2), approval_id).status_code == 200
    assert len(await _rows(factory, LLCAiLine)) == 1
    assert _outside_world.await_args.kwargs["details"]["self_approval"] is False


# -- the decide route runs the AI-line change and nothing else (#17161) --------------------------------------------


@pytest.mark.asyncio
async def test_the_decide_route_does_not_execute_any_other_registered_action(factory):
    from services.approval_execution import _PROPOSERS, _REGISTRY, register_post_approval_action

    ran = AsyncMock()
    register_post_approval_action("test.other_action_18430", ran, proposed_by="test")
    try:
        async with factory() as session:
            other = Approval(
                title="x", approval_type="workflow_gate", status="pending", company_id=COMPANY, requested_by_agent="x",
                context={"action": "test.other_action_18430"},
            )  # fmt: skip
            session.add(other)
            await session.commit()
            approval_id = str(other.id)
        assert _decide(_client(factory, user=OWNER), approval_id).status_code == 200
    finally:
        _REGISTRY.pop("test.other_action_18430", None)
        _PROPOSERS.pop("test.other_action_18430", None)
    ran.assert_not_awaited()
    assert any("only its allowed actions" in c.body for c in await _rows(factory, ApprovalComment))


# -- personal lines: a user with no company (owner decision, #18430) ---------------------------------------------


def _me_client(factory, user: uuid.UUID, credential: dict = PERSON) -> TestClient:
    """A person with NO org context: only authentication, no company."""
    app = FastAPI()
    app.include_router(ai_lines_router, prefix="/api/llc")
    app.dependency_overrides[get_session] = _session_for(factory)
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user), "username": str(user), **credential}
    return TestClient(app)


def _session_for(factory):
    async def _session():
        async with factory() as session:
            yield session

    return _session


def _gates_client(factory, user: uuid.UUID, username: str | None = None) -> TestClient:
    """The generic approvals route, which decides UNSCOPED approvals (a personal change is one)."""
    import api.approval_gates as gates
    from api.user_management.dependencies import get_db_session

    app = FastAPI()
    app.include_router(gates.router, prefix="/api")
    app.dependency_overrides[get_db_session] = _session_for(factory)
    app.dependency_overrides[gates.get_current_user] = lambda: {
        "id": str(user),
        "username": username or str(user),
        **PERSON,
    }
    return TestClient(app)


def _propose_mine(client, key="write_file", line="autonomous"):
    return client.post("/api/llc/ai-lines/me/changes", json={"action_key": key, "line": line})


def _approve(client, approval_id: str):
    return client.post(f"/api/approval-gates/{approval_id}/approve", json={})


@pytest.mark.asyncio
async def test_a_user_with_no_company_reads_their_own_lines_with_the_unset_default(factory):
    body = _me_client(factory, MEMBER).get("/api/llc/ai-lines/me").json()
    by_key = {e["action_key"]: e for e in body["entries"]}
    assert body["default_line"] == "draft_then_send" and body["company_id"] == str(MEMBER)
    assert by_key["write_file"]["effective_line"] == "draft_then_send" and not by_key["write_file"]["is_set"]


@pytest.mark.asyncio
async def test_a_personal_proposal_is_an_unscoped_approval_and_changes_nothing(factory):
    resp = _propose_mine(_me_client(factory, MEMBER))
    assert resp.status_code == 202
    [approval] = await _rows(factory, Approval)
    assert approval.company_id is None and approval.context["scope_kind"] == "user"
    assert approval.context["scope_id"] == str(MEMBER)
    assert await _rows(factory, LLCAiLine) == []


@pytest.mark.asyncio
async def test_the_person_can_approve_their_own_personal_change_and_it_is_flagged(factory, _outside_world):
    approval_id = _propose_mine(_me_client(factory, MEMBER)).json()["approval_id"]
    assert _approve(_gates_client(factory, MEMBER), approval_id).status_code == 200
    [row] = await _rows(factory, LLCAiLine)
    assert (row.scope_kind, row.company_id, row.action_key, row.line) == ("user", MEMBER, "write_file", "autonomous")
    assert _outside_world.await_args.kwargs["details"]["self_approval"] is True
    mine = _me_client(factory, MEMBER).get("/api/llc/ai-lines/me").json()["entries"]
    assert next(e for e in mine if e["action_key"] == "write_file")["is_set"]
    # ... and it is not on anyone else's page or any company's.
    other = _me_client(factory, OWNER).get("/api/llc/ai-lines/me").json()["entries"]
    assert not next(e for e in other if e["action_key"] == "write_file")["is_set"]


@pytest.mark.asyncio
async def test_nobody_else_can_approve_a_personal_change(factory):
    approval_id = _propose_mine(_me_client(factory, MEMBER)).json()["approval_id"]
    assert _approve(_gates_client(factory, OWNER), approval_id).status_code == 200  # decision recorded ...
    assert await _rows(factory, LLCAiLine) == []  # ... the personal line does not move
    assert any("did not complete" in c.body for c in await _rows(factory, ApprovalComment))


@pytest.mark.asyncio
async def test_an_agent_credential_cannot_propose_a_personal_change(factory):
    resp = _propose_mine(_me_client(factory, AGENT, credential=AGENT_CREDENTIAL))
    assert resp.status_code == 403 and await _rows(factory, Approval) == []


@pytest.mark.asyncio
async def test_me_is_not_parsed_as_a_company_id(factory):
    assert _me_client(factory, MEMBER).get("/api/llc/ai-lines/me").status_code == 200


# -- the four-eyes bypass and the username collision (round 9c) --------------------------------------------------


@pytest.mark.asyncio
async def test_a_set_line_approval_cannot_be_created_through_the_llc_route_naming_someone_else_as_requester(factory):
    """Admin A forges {"action": "ai_line.set_line"} naming admin B as the requester: refused at create."""
    await _add_admin(factory, ADMIN2)
    forged = {
        "company_id": str(COMPANY),
        "type": "workflow_gate",
        "requested_by_agent_id": str(ADMIN2),
        "payload": {"action": "ai_line.set_line", "action_key": "crm:send", "line": "autonomous"},
    }
    resp = _client(factory, user=OWNER).post("/api/llc/approvals", json=forged)
    assert resp.status_code == 403
    assert await _rows(factory, Approval) == []


@pytest.mark.asyncio
async def test_a_set_line_approval_cannot_be_created_through_the_generic_route(factory):
    body = {
        "title": "forged",
        "approval_type": "workflow_gate",
        "requested_by_agent": str(ADMIN2),
        "context": {"action": "ai_line.set_line", "action_key": "crm:send", "line": "autonomous"},
    }
    resp = _gates_client(factory, OWNER).post("/api/approval-gates", json=body)
    assert resp.status_code == 403 and await _rows(factory, Approval) == []
    # Contrast: an ordinary payload passes the same check.
    from api.approval_gates import _reject_unregistered_action

    assert _reject_unregistered_action({}) is None and _reject_unregistered_action(None) is None


@pytest.mark.asyncio
async def test_a_decision_on_an_approval_with_no_parseable_requester_is_refused(factory):
    """Even if one reached the table, an unidentifiable requester must not read as 'not the decider'."""
    await _add_admin(factory, ADMIN2)
    async with factory() as session:
        row = Approval(
            title="x", approval_type="workflow_gate", status="pending", company_id=COMPANY,
            requested_by_agent="not-a-person",
            context={"action": "ai_line.set_line", "action_key": "crm:send", "line": "autonomous"},
        )  # fmt: skip
        session.add(row)
        await session.commit()
        approval_id = str(row.id)
    assert _decide(_client(factory, user=ADMIN2), approval_id).status_code == 200  # recorded ...
    assert await _rows(factory, LLCAiLine) == []  # ... but the line did not move
    assert any("did not complete" in c.body for c in await _rows(factory, ApprovalComment))


@pytest.mark.asyncio
async def test_the_handler_refuses_without_a_verified_decider_or_requester(factory):
    from llc.services.authz import NotAuthorisedError
    from services.ai_line_change_action import ACTION, execute_line_change
    from services.approval_execution import set_verified_decider

    def row(requester):
        return Approval(
            title="x", approval_type="workflow_gate", status="approved", company_id=COMPANY,
            requested_by_agent=requester, decided_by_user="someone",
            context={"action": ACTION, "action_key": "crm", "line": "autonomous"},
        )  # fmt: skip

    async with factory() as session:
        no_decider, no_requester = row(f"ai-line-change:{MEMBER}"), row(None)
        set_verified_decider(no_requester, OWNER)
        for approval in (no_decider, no_requester):
            with pytest.raises((ValueError, NotAuthorisedError)):
                await execute_line_change(approval, session)
    assert await _rows(factory, LLCAiLine) == []


@pytest.mark.asyncio
async def test_a_username_that_spells_another_users_id_does_not_decide_that_users_personal_lines(factory):
    """The collision: attacker's username is victim's undashed UUID; the comparison is of VERIFIED ids only."""
    victim = uuid.uuid4()
    approval_id = _propose_mine(_me_client(factory, victim)).json()["approval_id"]
    attacker = _gates_client(factory, AGENT_USER, username=victim.hex)
    assert _approve(attacker, approval_id).status_code == 200  # decision recorded ...
    assert await _rows(factory, LLCAiLine) == []  # ... the victim's line does not move
    # Contrast: the victim themself, whatever their username, can decide it.
    assert _approve(_gates_client(factory, victim, username="victim-name"), approval_id).status_code in (200, 400)
