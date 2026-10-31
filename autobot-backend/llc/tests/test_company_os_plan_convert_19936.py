# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A Workflow Plan's gate, preview, approval and conversion into Company OS rows, end to end (#19936).

Real routers, services and tables on SQLite; only the session factory, the auth dependencies and the
approvals store's session factory are replaced. Rows are counted after a request, never mocked.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import llc.api.company_os_plans as plans_api
import llc.services.company_os.plan_convert as convert_mod
from api.user_management.dependencies import get_current_user, require_org_context
from llc.api.company_os import router as company_os_router
from llc.api.company_os_plans import router as plans_router
from llc.deps import get_session
from llc.models.ai_line import LLCAiLine
from llc.models.company_os import LLCProcess, LLCRoleSkill, LLCWorkflowNode, LLCWorkflowTransition
from llc.models.company_os_plan import CompanyOsWorkflowPlan
from llc.models.enums import MembershipRole, RoleHolderType
from llc.models.goal import LLCGoal
from llc.models.membership import LLCCompanyMembership
from llc.models.role_assignment import LLCRoleAssignment
from llc.services.company_os.errors import GraphInvalid
from llc.services.company_os.graph_types import GraphReport
from llc.services.company_os.graphs import GraphService
from llc.services.goal import GoalService
from llc.tests import _e2e_harness as harness
from models.approval import Approval, ApprovalComment, TaskApprovalLink
from models.workflow import Workflow
from user_management.models.base import Base
from user_management.models.role import Role
from user_management.services import TenantContext

COMPANY_A, COMPANY_B = uuid.uuid4(), uuid.uuid4()
ADMIN_A, ADMIN_B, MEMBER_A = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
PREFIX = "/api/llc/company-os/workflow-plans"
PERSON = {"auth_method": "session", "username": "person"}
_TABLES = [
    Role.__table__,
    LLCCompanyMembership.__table__,
    LLCRoleAssignment.__table__,
    LLCGoal.__table__,
    CompanyOsWorkflowPlan.__table__,
    Workflow.__table__,
    LLCProcess.__table__,
    LLCWorkflowNode.__table__,
    LLCWorkflowTransition.__table__,
    LLCRoleSkill.__table__,
    Approval.__table__,
    ApprovalComment.__table__,
    TaskApprovalLink.__table__,
    LLCAiLine.__table__,
]


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    for table in _TABLES:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    maker = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as s:
        for company, user, role in (
            (COMPANY_A, ADMIN_A, MembershipRole.ADMIN),
            (COMPANY_B, ADMIN_B, MembershipRole.ADMIN),
            (COMPANY_A, MEMBER_A, MembershipRole.MEMBER),
        ):
            s.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=company, user_id=user, role=role.value))
        await s.commit()
    yield maker
    await engine.dispose()


@pytest.fixture(autouse=True)
def _outside_world(monkeypatch, factory):
    monkeypatch.setattr(plans_api, "is_feature_enabled", lambda name: True)
    monkeypatch.setattr(GoalService, "_schedule_post_commit_index", lambda *a, **k: None)
    monkeypatch.setattr("services.ai_line_change_proposal.get_async_session_factory", lambda: factory)


def _client(maker, company: uuid.UUID, user: uuid.UUID, credential: dict = PERSON) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(plans_router, prefix="/api/llc")
    app.include_router(company_os_router, prefix="/api/llc")

    async def _session():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user), **credential}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=company, user_id=user, is_platform_admin=False
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _role(maker, company: uuid.UUID, name: str, holder: str | None = "user") -> uuid.UUID:
    async with maker() as s:
        role = Role(id=uuid.uuid4(), org_id=company, name=name)
        s.add(role)
        if holder is not None:
            s.add(
                LLCRoleAssignment(
                    id=uuid.uuid4(),
                    company_id=company,
                    role_id=role.id,
                    holder_type=holder,
                    holder_user_id=uuid.uuid4() if holder == RoleHolderType.USER.value else None,
                    holder_agent_id=uuid.uuid4() if holder == RoleHolderType.AGENT.value else None,
                )
            )
        await s.commit()
        return role.id


async def _count(maker, model, company: uuid.UUID | None = COMPANY_A) -> int:
    """Rows of *model* in *company*; ``None`` counts every company's."""
    async with maker() as s:
        col = getattr(model, "company_id", None)
        stmt = select(func.count()).select_from(model)
        scoped = company is not None and col is not None
        return (await s.execute(stmt.where(col == company) if scoped else stmt)).scalar_one()


def _map(role_id, office_role=None) -> dict:
    steps = [
        {"key": "s1", "lane_key": "ops", "label": "Take the call"},
        {"key": "s2", "lane_key": "ops", "label": "Write it up"},
        {"key": "s3", "lane_key": "cust", "label": "Confirm"},
    ]
    lanes = [
        {"key": "ops", "name": "Operations", "holder_kind": "user", "role_id": str(role_id)},
        {"key": "cust", "name": "Customer", "holder_kind": "customer"},
    ]
    if office_role is not None:
        lanes.append({"key": "office", "name": "Office", "holder_kind": "user", "role_id": str(office_role)})
    return {
        "lanes": lanes,
        "steps": steps,
        "edges": [{"from_step": "s1", "to_step": "s2"}, {"from_step": "s2", "to_step": "s3"}],
    }


METRIC = {"frequency": {"value": 5, "unit": "per_week"}, "duration": {"value": 2, "unit": "hours"}}
ONE = {
    "title": "Hours to confirm",
    "step_key": "s2",
    "return_kind": "hours_back",
    "direction": "down",
    "unit": "hours",
    "baseline_value": 2,
}
SUB = {
    "p1": {
        "key": "p1",
        "label": "Draft the quote",
        "state": "proposed",
        "classification": "ai",
        "tool_action": "mail:draft",
    },
    "p2": {
        "key": "p2",
        "label": "Price it",
        "state": "proposed",
        "classification": "automation",
        "tool_action": "pricing:calc",
    },
    "p3": {"key": "p3", "label": "Owner approves", "state": "proposed", "classification": "by_hand"},
}
CASES = [
    {"key": "e1", "description": "No photos attached", "classification": "automation", "handling": "Stop and ask"},
    {
        "key": "e2",
        "description": "Price looks off",
        "classification": "by_hand",
        "handling": "Owner checks",
        "sub_step_key": "p3",
    },
]
POLICY = {"policies": [{"key": "gate-1", "sub_step_keys": ["p1"], "on_timeout": "remind", "wait_limit": True}]}


def _breakdown(order=("p1", "p3", "p2")) -> dict:
    subs = [{"key": "c1", "label": "Listen", "state": "current"}]
    subs += [dict(SUB[k], replaces=["c1"] if i == 0 else []) for i, k in enumerate(order)]
    return {"sub_steps": subs, "edge_cases": CASES}


async def _labeled(admin, role, *, order=("p1", "p3", "p2"), office_role=None) -> None:
    body = {
        "key": "intake",
        "name": "Client intake",
        "entry_point": "org_chart",
        "starts_at": "A call",
        "ends_at": "A yes",
    }
    assert (await admin.post(PREFIX, json={**body, **_map(role, office_role)})).status_code == 201
    for step in ("s1", "s2", "s3"):
        assert (await admin.put(f"{PREFIX}/intake/steps/{step}/metric", json=METRIC)).status_code == 200
    assert (await admin.put(f"{PREFIX}/intake/one-number", json=ONE)).status_code == 200
    r = await admin.put(f"{PREFIX}/intake/steps/s2/breakdown", json=_breakdown(order))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "labeled"


async def _people_safe(admin) -> None:
    assert (await admin.put(f"{PREFIX}/intake/approval-policies", json=POLICY)).status_code == 200
    assert (await admin.post(f"{PREFIX}/intake/by-hand-acknowledgement")).status_code == 200


async def _approved(admin, role, **kw) -> dict:
    await _labeled(admin, role, **kw)
    await _people_safe(admin)
    pv = await admin.post(f"{PREFIX}/intake/convert/preview")
    assert pv.status_code == 200, pv.text
    r = await admin.post(f"{PREFIX}/intake/approve")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    return pv.json()


@pytest_asyncio.fixture
async def ctx(factory):
    role = await _role(factory, COMPANY_A, "Operator")
    return _client(factory, COMPANY_A, ADMIN_A), role, factory


# ------------------------------------------------------------------ the gate (FR-6.3)


async def test_convert_before_the_gates_pass_is_409_with_the_unmet_items(ctx):
    admin, role, factory = ctx
    body = {"key": "intake", "name": "n", "entry_point": "org_chart", "starts_at": "a", "ends_at": "b", **_map(role)}
    assert (await admin.post(PREFIX, json=body)).status_code == 201
    r = await admin.post(f"{PREFIX}/intake/convert")
    assert r.status_code == 409
    missing = r.json()["detail"]["missing"]
    assert missing and all(set(m) == {"gate", "message", "step"} for m in missing)
    assert {m["gate"] for m in missing} >= {"G2"}
    assert await _count(factory, Workflow) == 0 and await _count(factory, LLCProcess) == 0


async def test_labeled_but_unapproved_lists_g5_g6_g7_and_creates_nothing(ctx):
    admin, role, factory = ctx
    await _labeled(admin, role)
    r = await admin.post(f"{PREFIX}/intake/convert")
    assert r.status_code == 409
    assert {m["gate"] for m in r.json()["detail"]["missing"]} == {"G5", "G6", "G7"}
    assert (await admin.get(f"{PREFIX}/intake/gate")).json()["next_status"] == "approved"
    assert await _count(factory, Workflow) == 0


async def test_converted_without_approval_negative_control(ctx):
    admin, role, factory = ctx
    await _labeled(admin, role)
    await _people_safe(admin)
    assert (await admin.post(f"{PREFIX}/intake/convert/preview")).status_code == 200
    r = await admin.post(f"{PREFIX}/intake/convert")  # a preview, but nobody approved it
    assert r.status_code == 409 and [m["gate"] for m in r.json()["detail"]["missing"]] == ["G7"]
    assert await _count(factory, Workflow) == 0


async def test_approve_without_a_preview_or_with_g5_open_is_409(ctx):
    admin, role, _ = ctx
    await _labeled(admin, role)
    r = await admin.post(f"{PREFIX}/intake/approve")
    assert r.status_code == 409 and "preview" in r.text
    assert (await admin.post(f"{PREFIX}/intake/convert/preview")).status_code == 200
    r = await admin.post(f"{PREFIX}/intake/approve")
    assert r.status_code == 409 and {m["gate"] for m in r.json()["detail"]["missing"]} == {"G5"}


# ------------------------------------------------------------------ approval policies (FR-6.2)


async def test_an_uncovered_ai_sub_step_fails_g5_and_send_is_not_a_value(ctx):
    admin, role, _ = ctx
    await _labeled(admin, role)
    gate = (await admin.get(f"{PREFIX}/intake/gate")).json()
    assert any("p1" in m["message"] and m["gate"] == "G5" for m in gate["missing"])
    bad = {"policies": [{"key": "g", "sub_step_keys": ["p1"], "on_timeout": "send"}]}
    assert (await admin.put(f"{PREFIX}/intake/approval-policies", json=bad)).status_code == 422
    other = {"policies": [{"key": "g", "sub_step_keys": ["p1"], "approval_type": "plain"}]}
    assert (await admin.put(f"{PREFIX}/intake/approval-policies", json=other)).status_code == 422
    ghost = {"policies": [{"key": "g", "sub_step_keys": ["nope"]}]}
    assert (await admin.put(f"{PREFIX}/intake/approval-policies", json=ghost)).status_code == 422
    await _people_safe(admin)
    gate = (await admin.get(f"{PREFIX}/intake/gate")).json()
    assert not [m for m in gate["missing"] if m["gate"] == "G5"]


# ------------------------------------------------------------------ preview (FR-6.1, FR-6.4, D8)


async def test_preview_drafts_one_workflow_with_one_start_and_a_failure_path_per_node(ctx):
    admin, role, _ = ctx
    await _labeled(admin, role)
    await _people_safe(admin)
    conv = (await admin.post(f"{PREFIX}/intake/convert/preview")).json()
    assert conv["status"] == "preview" and conv["turn_on"] == "not_available"
    assert conv["preview_errors"] == [] and conv["contract_errors"] == []
    (wf,) = conv["workflows"]
    assert wf["workflow_id"] == "intake.ops" and wf["trigger_type"] == "manual"
    assert [n["kind"] for n in wf["nodes"]].count("start") == 1
    assert [p["process_key"] for p in conv["processes"]] == ["intake.p1", "intake.p3", "intake.p2"]
    failures = {t["from_node"] for t in wf["transitions"] if t["kind"] == "failure"}
    assert failures == {"p1", "p2", "p3"}
    assert wf["approval_policy_keys"] == ["gate-1"]
    assert {(t["tool_action"], t["line"]) for t in conv["ai_line_proposals"]} == {
        ("mail:draft", "draft_then_send"),
        ("pricing:calc", "autonomous"),
    }
    assert {(t["handoff_key"], t["treatment"]) for t in conv["handoff_treatments"]} == {("s2->s3", "end")}
    assert {(t["edge_case_key"], t["treatment"]) for t in conv["edge_case_treatments"]} == {
        ("e1", "branch"),
        ("e2", "handled_in_step"),
    }


async def test_preview_hands_back_the_validators_errors_and_warnings_unchanged(ctx, monkeypatch):
    admin, role, _ = ctx
    await _labeled(admin, role)
    await _people_safe(admin)
    planted = GraphReport(errors=["planted error"], warnings=["planted warning"])
    monkeypatch.setattr(convert_mod, "validate_graph", lambda spec, ctx: planted)
    conv = (await admin.post(f"{PREFIX}/intake/convert/preview")).json()
    assert conv["preview_errors"] == ["planted error"] and conv["preview_warnings"] == ["planted warning"]
    r = await admin.post(f"{PREFIX}/intake/approve")  # a validator error keeps G6 open
    assert r.status_code == 409 and any("planted error" in m["message"] for m in r.json()["detail"]["missing"])


async def test_a_by_hand_sub_step_is_a_person_node_inside_and_documentation_at_the_start(ctx):
    admin, role, _ = ctx
    await _labeled(admin, role)
    await _people_safe(admin)
    conv = (await admin.post(f"{PREFIX}/intake/convert/preview")).json()
    mid = {p["sub_step_key"]: p["executor"] for p in conv["processes"]}
    assert mid["p3"] == "person" and mid["p1"] == mid["p2"] == "role" and conv["documentation_only"] == []
    r = await admin.put(f"{PREFIX}/intake/steps/s2/breakdown", json=_breakdown(("p3", "p1", "p2")))
    assert r.status_code == 200
    await _people_safe(admin)
    conv = (await admin.post(f"{PREFIX}/intake/convert/preview")).json()
    assert [d["sub_step_key"] for d in conv["documentation_only"]] == ["p3"]
    assert "p3" not in {p["sub_step_key"] for p in conv["processes"]}
    assert all(t["from_node"] != "p3" for w in conv["workflows"] for t in w["transitions"])


async def test_a_by_hand_node_in_a_role_nobody_human_holds_is_refused(factory):
    role = await _role(factory, COMPANY_A, "Bot desk", holder=RoleHolderType.AGENT.value)
    admin = _client(factory, COMPANY_A, ADMIN_A)
    await _labeled(admin, role)
    await _people_safe(admin)
    conv = (await admin.post(f"{PREFIX}/intake/convert/preview")).json()
    assert any("no person holder" in e for e in conv["contract_errors"])
    assert (await admin.post(f"{PREFIX}/intake/approve")).status_code == 409


async def test_existing_keys_are_never_updated_new_workflows_only(ctx):
    admin, role, factory = ctx
    await _labeled(admin, role)
    await _people_safe(admin)
    async with factory() as s:
        s.add(Workflow(workflow_id="intake.ops", company_id=COMPANY_A, name="old", status="planned"))
        await s.commit()
    conv = (await admin.post(f"{PREFIX}/intake/convert/preview")).json()
    assert any("already exists" in e for e in conv["contract_errors"])


# ------------------------------------------------------------------ commit (FR-6.5, FR-6.7)


async def test_convert_creates_the_rows_through_the_services_and_the_graph_is_readable(ctx):
    admin, role, factory = ctx
    await _approved(admin, role)
    r = await admin.post(f"{PREFIX}/intake/convert")
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["status"] == "converted" and plan["conversion"]["status"] == "committed"
    assert plan["conversion"]["turn_on"] == "not_available" and plan["conversion"]["turn_on_tracking_issue"]
    assert plan["conversion"]["converted_at"] and plan["conversion"]["converted_by"] == str(ADMIN_A)
    assert await _count(factory, LLCProcess) == 3 and await _count(factory, Workflow) == 1
    async with factory() as s:
        wf = (await s.execute(select(Workflow))).scalar_one()
    assert (wf.workflow_id, wf.kind, wf.owner_role_id, wf.status) == ("intake.ops", "workflow", role, "planned")
    g = (await admin.get("/api/llc/company-os/workflows/intake.ops/graph")).json()
    assert [n["key"] for n in g["graph"]["nodes"]] == ["_start", "p1", "p3", "p2", "_done", "_failed"]
    assert g["validation"]["errors"] == []
    kinds = {(t["from_node"], t["kind"], t["to_node"]) for t in g["graph"]["transitions"]}
    assert (
        ("_start", "if", "_failed") in kinds
        and ("_start", "else", "p1") in kinds
        and ("p2", "success", "_done") in kinds
    )
    timeouts = [t for t in g["graph"]["transitions"] if t["kind"] == "timeout"]
    assert [t["from_node"] for t in timeouts] == ["p1"] and timeouts[0][
        "timeout_seconds"
    ] == convert_mod.APPROVAL_WAIT_SECONDS


async def test_ai_line_changes_are_proposed_in_approvals_and_never_written(ctx):
    admin, role, factory = ctx
    await _approved(admin, role)
    assert (await admin.post(f"{PREFIX}/intake/convert")).status_code == 200
    async with factory() as s:
        rows = (await s.execute(select(Approval))).scalars().all()
    got = {(a.context["action_key"], a.context["line"]) for a in rows}
    assert got == {("mail:draft", "draft_then_send"), ("pricing:calc", "autonomous")}
    assert all(a.status == "pending" and a.company_id == COMPANY_A for a in rows)
    assert await _count(factory, LLCAiLine) == 0


async def test_the_wait_limit_comes_from_the_setting_not_the_plan(ctx, monkeypatch):
    admin, role, _ = ctx
    monkeypatch.setattr(convert_mod, "APPROVAL_WAIT_SECONDS", 4321)
    await _approved(admin, role)
    assert (await admin.post(f"{PREFIX}/intake/convert")).status_code == 200
    g = (await admin.get("/api/llc/company-os/workflows/intake.ops/graph")).json()
    assert [t["timeout_seconds"] for t in g["graph"]["transitions"] if t["kind"] == "timeout"] == [4321]


async def test_a_failure_in_the_graph_step_leaves_no_rows_and_the_plan_approved(ctx, monkeypatch):
    admin, role, factory = ctx
    await _approved(admin, role)

    async def _boom(self, *a, **k):
        raise GraphInvalid(["forced failure in step 3"])

    real_replace = GraphService.replace
    monkeypatch.setattr(GraphService, "replace", _boom)
    r = await admin.post(f"{PREFIX}/intake/convert")
    assert r.status_code == 422 and "forced failure" in r.text
    assert await _count(factory, LLCProcess) == 0 and await _count(factory, Workflow) == 0
    assert await _count(factory, LLCWorkflowNode) == 0 and await _count(factory, Approval, None) == 0
    plan = (await admin.get(f"{PREFIX}/intake")).json()
    assert plan["status"] == "approved" and plan["conversion"]["status"] == "preview"
    monkeypatch.setattr(GraphService, "replace", real_replace)
    assert (await admin.post(f"{PREFIX}/intake/convert")).status_code == 200  # the same plan converts afterwards


async def test_a_converted_plan_cannot_convert_or_change_again(ctx):
    admin, role, factory = ctx
    await _approved(admin, role)
    assert (await admin.post(f"{PREFIX}/intake/convert")).status_code == 200
    assert (await admin.post(f"{PREFIX}/intake/convert")).status_code == 409
    assert (await admin.put(f"{PREFIX}/intake/approval-policies", json=POLICY)).status_code == 409
    assert await _count(factory, Workflow) == 1


# ------------------------------------------------------------------ edits, lanes (FR-6.6)


async def test_any_edit_after_approval_clears_it_and_the_preview(ctx):
    admin, role, factory = ctx
    await _approved(admin, role)
    r = await admin.put(f"{PREFIX}/intake/approval-policies", json=POLICY)
    plan = r.json()
    assert plan["status"] == "labeled" and plan["approved_at"] is None and plan["conversion"] is None
    assert (await admin.post(f"{PREFIX}/intake/convert")).status_code == 409
    assert await _count(factory, Workflow) == 0


async def test_two_lanes_make_two_workflows_created_target_first_with_a_handoff(factory):
    ops = await _role(factory, COMPANY_A, "Operator")
    office = await _role(factory, COMPANY_A, "Office")
    admin = _client(factory, COMPANY_A, ADMIN_A)
    await _labeled(admin, ops, office_role=office)
    async with factory() as s:  # the breakdown API pins sub-steps to the step's lane; a later edit may move one
        row = (await s.execute(select(CompanyOsWorkflowPlan))).scalar_one()
        doc = dict(row.document)
        doc["sub_steps"] = [dict(x, lane_key="office") if x["key"] == "p2" else x for x in doc["sub_steps"]]
        await s.execute(update(CompanyOsWorkflowPlan).where(CompanyOsWorkflowPlan.id == row.id).values(document=doc))
        await s.commit()
    await _people_safe(admin)
    conv = (await admin.post(f"{PREFIX}/intake/convert/preview")).json()
    assert conv["creation_order"] == ["intake.office", "intake.ops"]
    assert conv["preview_errors"] == [] and conv["contract_errors"] == []
    assert (await admin.post(f"{PREFIX}/intake/approve")).status_code == 200
    assert (await admin.post(f"{PREFIX}/intake/convert")).status_code == 200
    g = (await admin.get("/api/llc/company-os/workflows/intake.ops/graph")).json()["graph"]
    assert [(t["from_node"], t["handoff_workflow_id"]) for t in g["transitions"] if t["kind"] == "handoff"] == [
        ("_done", "intake.office")
    ]
    assert await _count(factory, Workflow) == 2


async def test_a_handoff_inside_one_role_is_refused_by_the_validator(factory):
    ops = await _role(factory, COMPANY_A, "Operator")
    admin = _client(factory, COMPANY_A, ADMIN_A)
    await _labeled(admin, ops, office_role=ops)  # the second lane holds the SAME role
    async with factory() as s:
        row = (await s.execute(select(CompanyOsWorkflowPlan))).scalar_one()
        doc = dict(row.document)
        doc["sub_steps"] = [dict(x, lane_key="office") if x["key"] == "p2" else x for x in doc["sub_steps"]]
        await s.execute(update(CompanyOsWorkflowPlan).where(CompanyOsWorkflowPlan.id == row.id).values(document=doc))
        await s.commit()
    await _people_safe(admin)
    conv = (await admin.post(f"{PREFIX}/intake/convert/preview")).json()
    assert any("must cross roles" in e for e in conv["preview_errors"])
    assert (await admin.post(f"{PREFIX}/intake/approve")).status_code == 409


# ------------------------------------------------------------------ who may (tenancy, flag)


@pytest.mark.parametrize("path", ["convert/preview", "approve", "convert"])
async def test_member_is_403_other_company_is_404_agent_credential_cannot_convert(ctx, path):
    admin, role, factory = ctx
    await _approved(admin, role)
    assert (await _client(factory, COMPANY_A, MEMBER_A).post(f"{PREFIX}/intake/{path}")).status_code == 403
    assert (await _client(factory, COMPANY_B, ADMIN_B).post(f"{PREFIX}/intake/{path}")).status_code == 404
    if path == "convert":
        agent = _client(factory, COMPANY_A, ADMIN_A, {"auth_method": "run_jwt", "username": "run:abc"})
        assert (await agent.post(f"{PREFIX}/intake/convert")).status_code == 403
    assert await _count(factory, Workflow) == 0


async def test_policies_route_is_admin_only_and_flag_off_hides_every_new_route(ctx, monkeypatch):
    admin, role, factory = ctx
    await _labeled(admin, role)
    assert (
        await _client(factory, COMPANY_A, MEMBER_A).put(f"{PREFIX}/intake/approval-policies", json=POLICY)
    ).status_code == 403
    assert (
        await _client(factory, COMPANY_B, ADMIN_B).put(f"{PREFIX}/intake/approval-policies", json=POLICY)
    ).status_code == 404
    monkeypatch.setattr(plans_api, "is_feature_enabled", lambda name: False)
    for method, path in (
        ("put", "approval-policies"),
        ("post", "convert/preview"),
        ("post", "approve"),
        ("post", "convert"),
    ):
        assert (await getattr(admin, method)(f"{PREFIX}/intake/{path}")).status_code == 404
