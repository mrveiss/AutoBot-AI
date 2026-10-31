# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Workflow Planner plan model, API and server-computed status, end to end on SQLite (#19934).

Real routers, real services, real tables; only the session factory and the two auth
dependencies are replaced, as in ``test_company_os_api.py``.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import llc.api.company_os_plans as plans_api
from api.user_management.dependencies import get_current_user, require_org_context
from llc.api.company_os_plans import router as plans_router
from llc.deps import get_session
from llc.models.company_os_plan import CompanyOsWorkflowPlan
from llc.models.enums import MembershipRole
from llc.models.goal import LLCGoal
from llc.models.membership import LLCCompanyMembership
from llc.models.role_assignment import LLCRoleAssignment
from llc.services.company_os import plan_store
from llc.services.company_os.plan_gate import STATUS_LADDER, derive_handoffs, evaluate_plan_gate
from llc.services.company_os.plan_types import WorkflowPlanStatus
from llc.services.goal import GoalService
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.role import Role
from user_management.services import TenantContext

COMPANY_A, COMPANY_B = uuid.uuid4(), uuid.uuid4()
ADMIN_A, ADMIN_B, MEMBER_A, MEMBER_B = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
PREFIX = "/api/llc/company-os/workflow-plans"
_TABLES = [
    Role.__table__,
    LLCCompanyMembership.__table__,
    LLCRoleAssignment.__table__,
    LLCGoal.__table__,
    CompanyOsWorkflowPlan.__table__,
]


@pytest.fixture(autouse=True)
def _planner_on(monkeypatch):
    monkeypatch.setattr(plans_api, "is_feature_enabled", lambda name: True)
    monkeypatch.setattr(GoalService, "_schedule_post_commit_index", lambda *a, **k: None)


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
            (COMPANY_B, MEMBER_B, MembershipRole.MEMBER),
        ):
            s.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=company, user_id=user, role=role.value))
        await s.commit()
    yield maker
    await engine.dispose()


def _client(maker, company: uuid.UUID, user: uuid.UUID) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(plans_router, prefix="/api/llc")

    async def _session():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=company, user_id=user, is_platform_admin=False
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _role(maker, company: uuid.UUID, name: str) -> uuid.UUID:
    async with maker() as s:
        role = Role(id=uuid.uuid4(), org_id=company, name=name)
        s.add(role)
        await s.commit()
        return role.id


async def _count_roles(maker, company: uuid.UUID) -> int:
    async with maker() as s:
        return (await s.execute(select(func.count()).select_from(Role).where(Role.org_id == company))).scalar_one()


def _map(role_id, *, extra_step: bool = False) -> dict:
    steps = [
        {"key": "s1", "lane_key": "ops", "label": "Take the call"},
        {"key": "s2", "lane_key": "ops", "label": "Write it up"},
        {"key": "s3", "lane_key": "cust", "label": "Confirm"},
    ]
    if extra_step:
        steps.append({"key": "s4", "lane_key": "ops", "label": "Archive"})
    return {
        "lanes": [
            {"key": "ops", "name": "Operations", "holder_kind": "user", "role_id": str(role_id)},
            {"key": "cust", "name": "Customer", "holder_kind": "customer"},
        ],
        "steps": steps,
        "edges": [{"from_step": "s1", "to_step": "s2"}, {"from_step": "s2", "to_step": "s3"}]
        + ([{"from_step": "s3", "to_step": "s4"}] if extra_step else []),
    }


def _plan_body(role_id, key: str = "intake", entry_point: str = "org_chart", **map_kw) -> dict:
    return {
        "key": key,
        "name": "Client intake",
        "entry_point": entry_point,
        "starts_at": "A client calls",
        "ends_at": "The client confirms",
        **_map(role_id, **map_kw),
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
BREAKDOWN = {
    "sub_steps": [
        {"key": "c1", "label": "Listen", "state": "current"},
        {"key": "p1", "label": "Draft the note", "state": "proposed", "replaces": ["c1"]},
        {"key": "p2", "label": "Send the note", "state": "proposed"},
    ],
    "edge_cases": [
        {"key": "e1", "description": "Caller is angry", "classification": "by_hand", "handling": "Phone back"}
    ],
}


@pytest_asyncio.fixture
async def ctx(factory):
    role = await _role(factory, COMPANY_A, "Operator")
    admin = _client(factory, COMPANY_A, ADMIN_A)
    resp = await admin.post(PREFIX, json=_plan_body(role))
    assert resp.status_code == 201, resp.text
    return admin, role, factory


async def _measure(admin) -> None:
    for step in ("s1", "s2", "s3"):
        assert (await admin.put(f"{PREFIX}/intake/steps/{step}/metric", json=METRIC)).status_code == 200
    assert (await admin.put(f"{PREFIX}/intake/one-number", json=ONE)).status_code == 200


async def _label(admin) -> dict:
    assert (await admin.put(f"{PREFIX}/intake/steps/s2/breakdown", json=BREAKDOWN)).status_code == 200
    for key, label in (("p1", "ai"), ("p2", "automation")):
        r = await admin.patch(f"{PREFIX}/intake/sub-steps/{key}", json={"classification": label})
        assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------- flag and entry (FR-0.1)


async def test_flag_off_every_route_is_404(factory, monkeypatch):
    monkeypatch.setattr(plans_api, "is_feature_enabled", lambda name: False)
    c = _client(factory, COMPANY_A, ADMIN_A)
    assert (await c.get(PREFIX)).status_code == 404
    assert (await c.post(PREFIX, json={})).status_code == 404


def test_flag_defaults_off_in_ssot():
    from autobot_shared.ssot_config import FeatureConfig

    field = FeatureConfig.model_fields["company_os_workflow_planner_enabled"]
    assert field.default is False
    assert field.alias == "AUTOBOT_FEATURE_COMPANY_OS_WORKFLOW_PLANNER"


@pytest.mark.parametrize("entry", ["org_chart", "wizard_exit", "workflow_area"])
async def test_each_entry_point_is_stored(factory, entry):
    role = await _role(factory, COMPANY_A, "Operator")
    c = _client(factory, COMPANY_A, ADMIN_A)
    assert (await c.post(PREFIX, json=_plan_body(role, "k-" + entry, entry))).status_code == 201
    assert (await c.get(f"{PREFIX}/k-{entry}")).json()["entry_point"] == entry


# ------------------------------------------------------------- map (FR-1)


async def test_create_returns_201_and_get_keeps_authoring_order(ctx):
    admin, role, _ = ctx
    body = _plan_body(role)
    got = (await admin.get(f"{PREFIX}/intake")).json()
    assert [s["key"] for s in got["steps"]] == ["s1", "s2", "s3"]
    assert [s["position"] for s in got["steps"]] == [0, 1, 2]
    assert [ln["key"] for ln in got["lanes"]] == ["ops", "cust"]
    assert [(e["from_step"], e["to_step"]) for e in got["edges"]] == [("s1", "s2"), ("s2", "s3")]
    assert got["starts_at"] == body["starts_at"] and got["status"] == "draft"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.update(lanes=[]),
        lambda b: b.update(steps=b["steps"][:1]),
        lambda b: b.update(edges=[]),
    ],
)
async def test_create_needs_a_lane_two_steps_and_an_edge(factory, mutate):
    role = await _role(factory, COMPANY_A, "Operator")
    body = _plan_body(role)
    mutate(body)
    r = await _client(factory, COMPANY_A, ADMIN_A).post(PREFIX, json=body)
    assert r.status_code == 422, r.text


async def test_customer_lane_creates_no_role_row(factory):
    role = await _role(factory, COMPANY_A, "Operator")
    before = await _count_roles(factory, COMPANY_A)
    assert (await _client(factory, COMPANY_A, ADMIN_A).post(PREFIX, json=_plan_body(role))).status_code == 201
    assert await _count_roles(factory, COMPANY_A) == before


async def test_role_of_another_company_is_404_not_403(factory):
    foreign = await _role(factory, COMPANY_B, "Theirs")
    r = await _client(factory, COMPANY_A, ADMIN_A).post(PREFIX, json=_plan_body(foreign))
    assert r.status_code == 404


async def test_lane_rules_follow_holder_kind(factory):
    role = await _role(factory, COMPANY_A, "Operator")
    c = _client(factory, COMPANY_A, ADMIN_A)
    body = _plan_body(role)
    body["lanes"][1]["role_id"] = str(role)  # a customer lane links no role
    assert (await c.post(PREFIX, json=body)).status_code == 422
    body = _plan_body(role)
    del body["lanes"][0]["role_id"]  # a user lane needs one
    assert (await c.post(PREFIX, json=body)).status_code == 422


async def test_handoffs_are_derived_and_only_for_cross_lane_edges(ctx):
    admin, _, _ = ctx
    got = (await admin.get(f"{PREFIX}/intake")).json()
    assert [(h["key"], h["from_lane"], h["to_lane"]) for h in got["handoffs"]] == [("s2->s3", "ops", "cust")]


async def test_client_cannot_send_handoffs(factory):
    role = await _role(factory, COMPANY_A, "Operator")
    body = _plan_body(role)
    body["handoffs"] = []
    assert (await _client(factory, COMPANY_A, ADMIN_A).post(PREFIX, json=body)).status_code == 422


async def test_wait_note_is_the_only_annotation_and_survives_a_map_replace(ctx):
    admin, role, _ = ctx
    r = await admin.patch(f"{PREFIX}/intake/handoffs/s2->s3", json={"wait_note": "waits for the client"})
    assert r.json()["handoffs"][0]["wait_note"] == "waits for the client"
    assert (await admin.patch(f"{PREFIX}/intake/handoffs/s1->s2", json={"wait_note": "x"})).status_code == 404
    assert (await admin.patch(f"{PREFIX}/intake/handoffs/s2->s3", json={"from_lane": "x"})).status_code == 422
    put = (await admin.put(f"{PREFIX}/intake/map", json=_map(role))).json()
    assert put["plan"]["handoffs"][0]["wait_note"] == "waits for the client"


async def test_gate_fails_a_planted_missing_handoff_negative_control(ctx):
    _, _, factory = ctx
    async with factory() as s:
        plan = plan_store.read_plan(await plan_store.load_row(s, COMPANY_A, "intake"))
    assert not [m for m in evaluate_plan_gate(plan).missing if "handoffs mismatch" in m.message]
    planted = plan.model_copy(update={"handoffs": []})
    assert [m for m in evaluate_plan_gate(planted).missing if "handoffs mismatch" in m.message]
    assert derive_handoffs(plan.steps, plan.edges)[0].key == "s2->s3"


async def test_map_validate_is_a_dry_run_in_the_graph_validation_shape(ctx):
    admin, role, _ = ctx
    bad = _map(role)
    bad["edges"].append({"from_step": "s1", "to_step": "nope"})
    r = await admin.post(f"{PREFIX}/intake/map/validate", json=bad)
    assert r.status_code == 200 and set(r.json()) == {"errors", "warnings"}
    assert any("nope" in e for e in r.json()["errors"])
    ok = await admin.post(f"{PREFIX}/intake/map/validate", json=_map(role, extra_step=True))
    assert ok.json()["errors"] == []
    assert len((await admin.get(f"{PREFIX}/intake")).json()["steps"]) == 3  # nothing was written


async def test_put_map_rejects_a_bad_map_with_the_error_list(ctx):
    admin, role, _ = ctx
    bad = _map(role)
    bad["steps"][0]["lane_key"] = "ghost"
    r = await admin.put(f"{PREFIX}/intake/map", json=bad)
    assert r.status_code == 422 and r.json()["detail"]["errors"]


# ------------------------------------------------------------- measure (FR-2, FR-3)


@pytest.mark.parametrize(
    "metric",
    [
        {"frequency": {"value": 5, "unit": "hours"}, "duration": {"value": 2, "unit": "hours"}},
        {"frequency": {"value": 5, "unit": "per_week"}, "duration": {"value": 2, "unit": "percent"}},
        {"frequency": {"value": 5, "unit": "per_week"}, "duration": {"value": 2, "unit": "per_week"}},
    ],
)
async def test_other_units_are_rejected(ctx, metric):
    admin, _, _ = ctx
    assert (await admin.put(f"{PREFIX}/intake/steps/s1/metric", json=metric)).status_code == 422


async def test_every_stored_measurement_carries_a_source(ctx):
    admin, _, _ = ctx
    await _measure(admin)
    got = (await admin.get(f"{PREFIX}/intake")).json()
    m = got["step_metrics"][0]
    assert m["frequency"]["source"] == m["duration"]["source"] == "self_reported"
    assert got["one_number"]["baseline"]["source"] == "self_reported"
    body = {**METRIC, "frequency": {**METRIC["frequency"], "source": "email"}}
    assert (await admin.put(f"{PREFIX}/intake/steps/s1/metric", json=body)).status_code == 422


async def test_member_writes_a_metric_only_for_their_own_lane(ctx):
    admin, role, factory = ctx
    async with factory() as s:
        s.add(
            LLCRoleAssignment(
                id=uuid.uuid4(), company_id=COMPANY_A, role_id=role, holder_type="user", holder_user_id=MEMBER_A
            )
        )
        await s.commit()
    member = _client(factory, COMPANY_A, MEMBER_A)
    assert (await member.put(f"{PREFIX}/intake/steps/s1/metric", json=METRIC)).status_code == 200
    assert (await member.put(f"{PREFIX}/intake/steps/s3/metric", json=METRIC)).status_code == 403  # customer lane
    assert (await member.put(f"{PREFIX}/intake/one-number", json=ONE)).status_code == 403
    assert (await member.put(f"{PREFIX}/intake/map", json=_map(role))).status_code == 403


async def test_member_without_the_lane_role_cannot_write_a_metric(ctx):
    _, _, factory = ctx
    member = _client(factory, COMPANY_A, MEMBER_A)
    assert (await member.put(f"{PREFIX}/intake/steps/s1/metric", json=METRIC)).status_code == 403


async def test_no_one_number_exists_until_an_admin_sets_it_and_target_stays_null(ctx):
    admin, _, _ = ctx
    for step in ("s1", "s2", "s3"):
        await admin.put(f"{PREFIX}/intake/steps/{step}/metric", json=METRIC)
    assert (await admin.get(f"{PREFIX}/intake")).json()["one_number"] is None
    got = (await admin.put(f"{PREFIX}/intake/one-number", json=ONE)).json()
    assert got["one_number"]["target_value"] is None


async def test_one_number_creates_a_key_result_goal_the_tree_shows(ctx):
    admin, _, factory = ctx
    await _measure(admin)
    one = (await admin.get(f"{PREFIX}/intake")).json()["one_number"]
    async with factory() as s:
        goals = await GoalService().list_all_by_company(s, str(COMPANY_A))
    # GoalService.list_all_by_company is the query behind GET /llc/goals/tree
    assert [(str(g.id), g.level, g.title) for g in goals] == [(one["goal_id"], "key_result", ONE["title"])]
    again = (await admin.put(f"{PREFIX}/intake/one-number", json={**ONE, "title": "Renamed"})).json()
    assert again["one_number"]["goal_id"] == one["goal_id"]  # linked, not duplicated


async def test_one_number_cannot_link_another_companys_goal(ctx):
    admin, _, factory = ctx
    async with factory() as s:
        goal = LLCGoal(id=uuid.uuid4(), company_id=str(COMPANY_B), title="Theirs", level="key_result", status="draft")
        s.add(goal)
        await s.commit()
    r = await admin.put(f"{PREFIX}/intake/one-number", json={**ONE, "goal_id": str(goal.id)})
    assert r.status_code == 404


# ------------------------------------------------------------- break down and label (FR-4, FR-5)


async def test_breakdown_needs_the_one_number_on_that_step_first(ctx):
    admin, _, _ = ctx
    assert (await admin.put(f"{PREFIX}/intake/steps/s2/breakdown", json=BREAKDOWN)).status_code == 409


async def test_breakdown_rejects_a_bad_replaces_and_misordered_current(ctx):
    admin, _, _ = ctx
    await _measure(admin)
    bad = {
        "sub_steps": [
            *BREAKDOWN["sub_steps"][:1],
            {**BREAKDOWN["sub_steps"][1], "replaces": ["p2"]},
            BREAKDOWN["sub_steps"][2],
        ]
    }
    r = await admin.put(f"{PREFIX}/intake/steps/s2/breakdown", json=bad)
    assert r.status_code == 422 and any("not a current" in e for e in r.json()["detail"]["errors"])
    late = {"sub_steps": [BREAKDOWN["sub_steps"][1], BREAKDOWN["sub_steps"][0]]}
    assert (await admin.put(f"{PREFIX}/intake/steps/s2/breakdown", json=late)).status_code == 422


async def test_edge_case_requires_a_classification(ctx):
    admin, _, _ = ctx
    await _measure(admin)
    case = {k: v for k, v in BREAKDOWN["edge_cases"][0].items() if k != "classification"}
    r = await admin.put(f"{PREFIX}/intake/steps/s2/breakdown", json={**BREAKDOWN, "edge_cases": [case]})
    assert r.status_code == 422


async def test_unlabelled_proposed_sub_step_blocks_labeled_then_labels_earn_it(ctx):
    admin, _, _ = ctx
    await _measure(admin)
    assert (await admin.get(f"{PREFIX}/intake")).json()["status"] == "measured"
    await admin.put(f"{PREFIX}/intake/steps/s2/breakdown", json=BREAKDOWN)
    gate_now = (await admin.get(f"{PREFIX}/intake/gate")).json()
    assert gate_now["status"] == "measured" and gate_now["next_status"] == "labeled"
    assert {m["gate"] for m in gate_now["missing"]} == {"G4"}
    assert (await _label(admin))["status"] == "labeled"
    gate_after = (await admin.get(f"{PREFIX}/intake/gate")).json()
    # labeled is no longer the top (#19936): what is left is the next rung's G5-G7, never G1-G4
    assert gate_after["next_status"] == "approved" and {m["gate"] for m in gate_after["missing"]} == {"G5", "G6", "G7"}


async def test_a_current_sub_step_takes_no_label(ctx):
    admin, _, _ = ctx
    await _measure(admin)
    await admin.put(f"{PREFIX}/intake/steps/s2/breakdown", json=BREAKDOWN)
    r = await admin.patch(f"{PREFIX}/intake/sub-steps/c1", json={"classification": "ai"})
    assert r.status_code == 422


# ------------------------------------------------------------- status (FR-0.3, FR-0.4, D14)


async def test_removing_a_metric_from_a_labeled_plan_demotes_it_with_history(ctx):
    admin, _, _ = ctx
    await _measure(admin)
    labeled = await _label(admin)
    assert [(h["from_status"], h["to_status"]) for h in labeled["status_history"]] == [
        (None, "draft"),
        ("draft", "measured"),
        ("measured", "labeled"),
    ]
    r = await admin.delete(f"{PREFIX}/intake/steps/s1/metric")
    body = r.json()
    assert body["status"] == "draft"
    last = body["status_history"][-1]
    assert (last["from_status"], last["to_status"]) == ("labeled", "draft")
    assert "s1" in last["reason"] and last["by"] == str(ADMIN_A)
    async with ctx[2]() as s:  # the status column agrees with the document
        assert (await s.execute(select(CompanyOsWorkflowPlan.status))).scalar_one() == "draft"


async def test_adding_a_step_without_metrics_demotes_a_labeled_plan(ctx):
    admin, role, _ = ctx
    await _measure(admin)
    await _label(admin)
    r = await admin.put(f"{PREFIX}/intake/map", json=_map(role, extra_step=True))
    assert r.json()["plan"]["status"] == "draft"


async def test_status_in_a_patch_body_is_422_and_changes_nothing(ctx):
    admin, _, _ = ctx
    assert (await admin.patch(f"{PREFIX}/intake", json={"status": "converted"})).status_code == 422
    assert (await admin.patch(f"{PREFIX}/intake", json={"name": "Renamed", "status": "labeled"})).status_code == 422
    got = (await admin.get(f"{PREFIX}/intake")).json()
    assert got["status"] == "draft" and got["name"] == "Client intake"
    assert (await admin.patch(f"{PREFIX}/intake", json={"name": "Renamed"})).json()["name"] == "Renamed"


async def test_status_is_never_taken_from_the_create_body(factory):
    role = await _role(factory, COMPANY_A, "Operator")
    r = await _client(factory, COMPANY_A, ADMIN_A).post(PREFIX, json={**_plan_body(role), "status": "labeled"})
    assert r.status_code == 422


async def test_every_write_to_a_converted_revision_is_409_start_a_new_revision(ctx):
    admin, role, factory = ctx
    async with factory() as s:
        row = await plan_store.load_row(s, COMPANY_A, "intake")
        await s.execute(
            update(CompanyOsWorkflowPlan)
            .where(CompanyOsWorkflowPlan.id == row.id)
            .values(status="converted", document={**row.document, "status": "converted"})
        )
        await s.commit()
    calls = [
        admin.patch(f"{PREFIX}/intake", json={"name": "x"}),
        admin.put(f"{PREFIX}/intake/map", json=_map(role)),
        admin.patch(f"{PREFIX}/intake/handoffs/s2->s3", json={"wait_note": "x"}),
        admin.put(f"{PREFIX}/intake/steps/s1/metric", json=METRIC),
        admin.delete(f"{PREFIX}/intake/steps/s1/metric"),
        admin.put(f"{PREFIX}/intake/one-number", json=ONE),
        admin.put(f"{PREFIX}/intake/steps/s2/breakdown", json=BREAKDOWN),
        admin.patch(f"{PREFIX}/intake/sub-steps/p1", json={"rationale": "x"}),
        admin.post(f"{PREFIX}/intake/by-hand-acknowledgement"),
    ]
    for call in calls:
        r = await call
        assert r.status_code == 409 and "start a new revision" in r.json()["detail"], r.text
    assert (await admin.delete(PREFIX + "/intake")).status_code == 409
    assert (await admin.get(f"{PREFIX}/intake/revisions/1")).json()["status"] == "converted"


async def test_one_open_revision_per_plan_key(ctx):
    admin, role, factory = ctx
    assert (await admin.post(PREFIX, json=_plan_body(role))).status_code == 409
    async with factory() as s:
        s.add(CompanyOsWorkflowPlan(company_id=COMPANY_A, plan_key="intake", revision=2, name="n", document={}))
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_a_converted_revision_does_not_block_the_next_open_one(ctx):
    _, _, factory = ctx
    async with factory() as s:
        row = await plan_store.load_row(s, COMPANY_A, "intake")
        row.status = "converted"
        s.add(CompanyOsWorkflowPlan(company_id=COMPANY_A, plan_key="intake", revision=2, name="n", document={}))
        await s.commit()


async def test_approval_is_cleared_by_any_edit_but_not_by_the_acknowledgement(ctx):
    admin, _, factory = ctx
    stamp = "2026-10-30T10:00:00+00:00"
    async with factory() as s:
        row = await plan_store.load_row(s, COMPANY_A, "intake")
        row.document = {**row.document, "approved_at": stamp, "approved_by": str(ADMIN_A)}
        await s.commit()
    ack = (await admin.post(f"{PREFIX}/intake/by-hand-acknowledgement")).json()
    assert ack["approved_at"] is not None and ack["by_hand_acknowledged_at"] is not None
    edited = (await admin.patch(f"{PREFIX}/intake", json={"name": "Edited"})).json()
    assert edited["approved_at"] is None and edited["approved_by"] is None


def test_the_ladder_is_ordered_and_climbs_to_converted():
    order = list(WorkflowPlanStatus)
    earned = [status for status, _ in STATUS_LADDER]
    assert earned == sorted(earned, key=order.index)
    assert earned[-2:] == [WorkflowPlanStatus.APPROVED, WorkflowPlanStatus.CONVERTED]


# ------------------------------------------------------------- tenancy, list, delete


async def test_another_companys_plan_is_404_everywhere(ctx):
    _, _, factory = ctx
    other = _client(factory, COMPANY_B, ADMIN_B)
    assert (await other.get(f"{PREFIX}/intake")).status_code == 404
    assert (await other.get(f"{PREFIX}/intake/gate")).status_code == 404
    assert (await other.patch(f"{PREFIX}/intake", json={"name": "x"})).status_code == 404
    assert (await other.delete(f"{PREFIX}/intake")).status_code == 404
    assert (await other.get(PREFIX)).json() == []


async def test_plain_members_may_read_but_not_create_or_delete(ctx):
    _, role, factory = ctx
    member = _client(factory, COMPANY_A, MEMBER_A)
    assert (await member.get(f"{PREFIX}/intake")).status_code == 200
    assert (await member.post(PREFIX, json=_plan_body(role, "other"))).status_code == 403
    assert (await member.delete(f"{PREFIX}/intake")).status_code == 403


async def test_list_filters_by_status_and_delete_removes_the_plan(ctx):
    admin, role, _ = ctx
    await admin.post(PREFIX, json=_plan_body(role, "second"))
    assert {p["plan_key"] for p in (await admin.get(PREFIX)).json()} == {"intake", "second"}
    await _measure(admin)
    measured = (await admin.get(PREFIX, params={"status_filter": "measured"})).json()
    assert [p["plan_key"] for p in measured] == ["intake"]
    assert (await admin.delete(f"{PREFIX}/second")).status_code == 204
    assert (await admin.get(f"{PREFIX}/second")).status_code == 404
