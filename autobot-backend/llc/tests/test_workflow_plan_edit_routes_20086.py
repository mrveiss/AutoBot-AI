# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Edit one lane, step, edge or edge case of a plan through the real routes (#20086).

Real routers, services and tables on SQLite. A converted revision is real (the plan is walked through the
gates and converted), and the second company is a real second admin, so 409 and 404 are not mocked.
"""

# flake8: noqa: F811 -- imported pytest fixtures are redefined as test arguments
from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api.company_os_plan_edit import router as edit_router
from llc.api.company_os_plans import router as plans_router
from llc.deps import get_session
from llc.tests.test_company_os_plan_convert_19936 import (  # noqa: F401 -- fixtures are used by name
    ADMIN_A,
    ADMIN_B,
    COMPANY_A,
    COMPANY_B,
    MEMBER_A,
    PERSON,
    POLICY,
    PREFIX,
    _approved,
    _labeled,
    _map,
    _outside_world,
    _people_safe,
    _role,
    ctx,
    factory,
)
from user_management.models.role import Role
from user_management.services import TenantContext

pytestmark = pytest.mark.asyncio

CASE = {"key": "e9", "description": "Caller hangs up", "classification": "by_hand", "handling": "Ring back"}
#: Every edit route: (verb, path, body, success status). Bodies fit the plan ``_labeled`` builds.
ROUTES = {
    "add_lane": ("post", "/lanes", {"key": "spare", "name": "Spare", "holder_kind": "customer"}, 201),
    "patch_lane": ("patch", "/lanes/cust", {"name": "Customers"}, 200),
    "delete_lane": ("delete", "/lanes/spare", None, 200),
    "add_step": ("post", "/steps", {"key": "s9", "lane_key": "ops", "label": "Archive"}, 201),
    "patch_step": ("patch", "/steps/s1", {"label": "Pick up"}, 200),
    "delete_step": ("delete", "/steps/s1", None, 200),
    "add_edge": ("post", "/edges", {"from_step": "s1", "to_step": "s3"}, 201),
    "patch_edge": ("patch", "/edges/s1/s2", {"condition": "if urgent"}, 200),
    "delete_edge": ("delete", "/edges/s1/s2", None, 200),
    "add_edge_case": ("post", "/steps/s2/edge-cases", CASE, 201),
    "patch_edge_case": ("patch", "/edge-cases/e1", {"handling": "Ask twice"}, 200),
    "delete_edge_case": ("delete", "/edge-cases/e1", None, 200),
}


def _client(maker, company: uuid.UUID, user: uuid.UUID, credential: dict = PERSON) -> httpx.AsyncClient:
    app = FastAPI()
    for router in (plans_router, edit_router):
        app.include_router(router, prefix="/api/llc")

    async def _session():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user), **credential}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=company, user_id=user, is_platform_admin=False
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _call(client, name: str, plan: str = "intake") -> httpx.Response:
    verb, path, body, _ = ROUTES[name]
    return await client.request(verb.upper(), f"{PREFIX}/{plan}{path}", json=body)


async def _get(client) -> dict:
    return (await client.get(f"{PREFIX}/intake")).json()


@pytest.fixture
async def edit(ctx):
    """A ``labeled`` plan with an acknowledged By Hand list, a spare lane, and a client that can edit it."""
    _, role, factory = ctx
    admin = _client(factory, COMPANY_A, ADMIN_A)
    await _labeled(admin, role)
    await _people_safe(admin)
    return admin, role, factory


# ------------------------------------------------------------------ add, edit, delete (AC 1)


@pytest.mark.parametrize("name", sorted(ROUTES))
async def test_each_route_does_its_one_edit_and_voids_the_acknowledgement(edit, name):
    admin, _, _ = edit
    if name != "add_lane":
        assert (await admin.post(f"{PREFIX}/intake/lanes", json=ROUTES["add_lane"][2])).status_code == 201
    assert (await admin.put(f"{PREFIX}/intake/approval-policies", json=POLICY)).status_code == 200
    assert (await admin.post(f"{PREFIX}/intake/by-hand-acknowledgement")).json()["by_hand_acknowledged_at"]
    r = await _call(admin, name)
    assert r.status_code == ROUTES[name][3], r.text
    assert r.json()["by_hand_acknowledged_at"] is None
    assert (await _get(admin))["by_hand_acknowledged_at"] is None  # stored, not just in the response


async def test_a_step_without_a_metric_drops_the_status_and_removing_it_restores_it(edit):
    admin, _, _ = edit
    added = (await _call(admin, "add_step")).json()
    assert added["status"] == "draft" and added["status_history"][-1]["to_status"] == "draft"
    assert "s9" in {s["key"] for s in added["steps"]}
    back = (await admin.delete(f"{PREFIX}/intake/steps/s9")).json()
    assert back["status"] == "labeled" and {s["key"] for s in back["steps"]} == {"s1", "s2", "s3"}


async def test_an_edge_between_lanes_derives_a_handoff_and_keeps_the_notes_of_the_others(edit):
    admin, _, _ = edit
    note = {"wait_note": "waits for the client"}
    assert (await admin.patch(f"{PREFIX}/intake/handoffs/s2->s3", json=note)).status_code == 200
    plan = (await _call(admin, "add_edge")).json()
    by_key = {h["key"]: h for h in plan["handoffs"]}
    assert set(by_key) == {"s1->s3", "s2->s3"}
    assert by_key["s2->s3"]["wait_note"] == "waits for the client"
    assert (by_key["s1->s3"]["from_lane"], by_key["s1->s3"]["to_lane"]) == ("ops", "cust")
    gone = (await admin.delete(f"{PREFIX}/intake/edges/s1/s3")).json()
    assert [h["key"] for h in gone["handoffs"]] == ["s2->s3"]


async def test_patching_an_edge_changes_its_condition_only(edit):
    admin, _, _ = edit
    plan = (await _call(admin, "patch_edge")).json()
    edge = next(e for e in plan["edges"] if (e["from_step"], e["to_step"]) == ("s1", "s2"))
    assert edge["condition"] == "if urgent" and len(plan["edges"]) == 2
    assert (await admin.patch(f"{PREFIX}/intake/edges/s1/s2", json={"to_step": "s3"})).status_code == 422


async def test_moving_a_step_to_another_lane_rederives_the_handoffs_and_moves_its_sub_steps(edit):
    admin, _, _ = edit
    plan = (await admin.patch(f"{PREFIX}/intake/steps/s2", json={"lane_key": "cust"})).json()
    assert {h["key"] for h in plan["handoffs"]} == {"s1->s2"}
    assert {s["lane_key"] for s in plan["sub_steps"]} == {"cust"}
    both = (await admin.patch(f"{PREFIX}/intake/steps/s3", json={"lane_key": "ops"})).json()
    assert {h["key"] for h in both["handoffs"]} == {"s1->s2", "s2->s3"}


async def test_removing_a_step_removes_its_edges_and_what_hangs_off_it(edit):
    admin, _, _ = edit
    plan = (await admin.delete(f"{PREFIX}/intake/steps/s3")).json()
    assert [(e["from_step"], e["to_step"]) for e in plan["edges"]] == [("s1", "s2")]
    assert plan["handoffs"] == [] and {m["step_key"] for m in plan["step_metrics"]} == {"s1", "s2"}


async def test_the_one_number_step_cannot_be_removed_and_leaves_the_plan_alone(edit):
    admin, _, _ = edit
    before = await _get(admin)
    r = await admin.delete(f"{PREFIX}/intake/steps/s2")
    assert r.status_code == 409 and "One Number" in r.text
    assert await _get(admin) == before


async def test_a_removed_steps_sub_steps_leave_the_approval_policies(edit):
    admin, _, _ = edit
    assert (await admin.put(f"{PREFIX}/intake/approval-policies", json=POLICY)).status_code == 200
    one = {"title": "Hours", "step_key": "s1", "return_kind": "hours_back", "direction": "down", "unit": "hours"}
    assert (await admin.put(f"{PREFIX}/intake/one-number", json={**one, "baseline_value": 1})).status_code == 200
    assert (await _call(admin, "add_edge")).status_code == 201  # s1 -> s3 keeps an edge once s2 and its edges go
    plan = (await admin.delete(f"{PREFIX}/intake/steps/s2")).json()
    assert plan["sub_steps"] == [] and plan["approval_policies"][0]["sub_step_keys"] == []


async def test_a_lane_that_still_holds_a_step_is_refused_and_an_empty_one_goes(edit):
    admin, _, _ = edit
    r = await admin.delete(f"{PREFIX}/intake/lanes/cust")
    assert r.status_code == 422 and "s3" in r.text
    await _call(admin, "add_lane")
    plan = (await _call(admin, "delete_lane")).json()
    assert {ln["key"] for ln in plan["lanes"]} == {"ops", "cust"}


async def test_a_lane_patch_is_checked_by_the_lane_rules_and_the_company_roles(edit):
    admin, role, factory = edit
    bad = await admin.patch(f"{PREFIX}/intake/lanes/ops", json={"holder_kind": "customer"})
    assert bad.status_code == 422  # a customer lane links no role
    foreign = await _role(factory, COMPANY_B, "Theirs")
    r = await admin.patch(f"{PREFIX}/intake/lanes/ops", json={"role_id": str(foreign)})
    assert r.status_code == 404
    ok = await admin.patch(f"{PREFIX}/intake/lanes/ops", json={"role_id": str(role), "name": "Ops"})
    assert ok.status_code == 200 and ok.json()["lanes"][0]["name"] == "Ops"
    assert (
        await admin.post(f"{PREFIX}/intake/lanes", json={"key": "x", "name": "X", "holder_kind": "user"})
    ).status_code == 422


async def test_the_map_rules_hold_for_a_single_edit(edit):
    admin, _, _ = edit
    dup = await admin.post(f"{PREFIX}/intake/steps", json={"key": "s1", "lane_key": "ops", "label": "Again"})
    assert dup.status_code == 422 and "duplicate step key" in dup.text
    nolane = await admin.post(f"{PREFIX}/intake/steps", json={"key": "s8", "lane_key": "nope", "label": "Lost"})
    assert nolane.status_code == 422
    self_loop = await admin.post(f"{PREFIX}/intake/edges", json={"from_step": "s1", "to_step": "s1"})
    assert self_loop.status_code == 422
    assert (await admin.post(f"{PREFIX}/intake/edges", json={"from_step": "s1", "to_step": "s2"})).status_code == 422
    assert (await admin.post(f"{PREFIX}/intake/edges", json={"from_step": "s1", "to_step": "zz"})).status_code == 422
    assert (await admin.patch(f"{PREFIX}/intake/steps/zz", json={"label": "x"})).status_code == 404


# ------------------------------------------------------------------ edge cases (AC 2)


async def test_an_edge_case_is_added_edited_and_deleted_on_its_own(edit):
    admin, _, _ = edit
    added = (await _call(admin, "add_edge_case")).json()
    assert {c["key"] for c in added["edge_cases"]} == {"e1", "e2", "e9"}
    assert next(c for c in added["edge_cases"] if c["key"] == "e9")["step_key"] == "s2"
    sub = len(added["sub_steps"])
    edited = (await admin.patch(f"{PREFIX}/intake/edge-cases/e9", json={"handling": "Text back"})).json()
    assert next(c for c in edited["edge_cases"] if c["key"] == "e9")["handling"] == "Text back"
    gone = (await admin.delete(f"{PREFIX}/intake/edge-cases/e9")).json()
    assert {c["key"] for c in gone["edge_cases"]} == {"e1", "e2"} and len(gone["sub_steps"]) == sub


async def test_an_edge_case_without_handling_reopens_the_label_gate(edit):
    admin, _, _ = edit
    plan = (await admin.patch(f"{PREFIX}/intake/edge-cases/e1", json={"handling": ""})).json()
    assert plan["status"] == "measured"
    fixed = (await _call(admin, "patch_edge_case")).json()
    assert fixed["status"] == "labeled"


async def test_the_edge_case_rules_hold_for_a_single_edit(edit):
    admin, _, _ = edit
    dup = await admin.post(f"{PREFIX}/intake/steps/s2/edge-cases", json={**CASE, "key": "e1"})
    assert dup.status_code == 422 and "duplicate edge case key" in dup.text
    off_step = await admin.post(f"{PREFIX}/intake/steps/s1/edge-cases", json=CASE)
    assert off_step.status_code == 409 and "One Number" in off_step.text
    no_sub = await admin.patch(f"{PREFIX}/intake/edge-cases/e1", json={"sub_step_key": "nope"})
    assert no_sub.status_code == 422 and "nope" in no_sub.text
    cleared = await admin.patch(f"{PREFIX}/intake/edge-cases/e2", json={"sub_step_key": None})
    assert cleared.status_code == 200
    assert (await admin.patch(f"{PREFIX}/intake/edge-cases/zz", json={"handling": "x"})).status_code == 404
    assert (await admin.delete(f"{PREFIX}/intake/edge-cases/zz")).status_code == 404


async def test_the_whole_breakdown_put_refuses_two_edge_cases_with_one_key(edit):
    admin, _, _ = edit
    body = {"sub_steps": [], "edge_cases": [CASE, CASE]}
    r = await admin.put(f"{PREFIX}/intake/steps/s2/breakdown", json=body)
    assert r.status_code == 422 and "duplicate edge case key" in r.text


# ------------------------------------------------------------------ converted and cross-company (AC 3)


@pytest.mark.parametrize("name", sorted(ROUTES))
async def test_a_converted_revision_refuses_every_edit_with_409_and_stays_as_it_was(ctx, name):
    _, role, factory = ctx
    admin = _client(factory, COMPANY_A, ADMIN_A)
    await _approved(admin, role)
    assert (await admin.post(f"{PREFIX}/intake/convert")).json()["status"] == "converted"
    before = await _get(admin)
    r = await _call(admin, name)
    assert r.status_code == 409, r.text
    assert await _get(admin) == before


@pytest.mark.parametrize("name", sorted(ROUTES))
async def test_another_companys_admin_gets_404_for_every_edit(edit, name):
    _, _, factory = edit
    other = _client(factory, COMPANY_B, ADMIN_B)
    before = await _get(edit[0])
    r = await _call(other, name)
    assert r.status_code == 404, r.text
    assert await _get(edit[0]) == before


async def test_a_member_who_is_not_an_admin_may_not_edit(edit):
    _, _, factory = edit
    member = _client(factory, COMPANY_A, MEMBER_A)
    for name in ("add_step", "patch_edge_case"):
        assert (await _call(member, name)).status_code == 403


async def test_the_routes_follow_the_planner_flag(edit, monkeypatch):
    import llc.api.company_os_plans as plans_api

    admin, _, _ = edit
    monkeypatch.setattr(plans_api, "is_feature_enabled", lambda name: False)
    for name in ROUTES:
        assert (await _call(admin, name)).status_code == 404


# ------------------------------------------------------------------ two people at once


async def test_two_people_editing_different_things_both_keep_their_change(edit):
    """Each one reads the plan, then edits one thing: neither has to resend the structure, so neither loses."""
    _, _, factory = edit
    first, second = _client(factory, COMPANY_A, ADMIN_A), _client(factory, COMPANY_A, ADMIN_A)
    stale = await _get(first)  # both people are looking at this
    assert (
        await first.post(f"{PREFIX}/intake/steps", json={"key": "s7", "lane_key": "ops", "label": "One"})
    ).status_code == 201
    assert (
        await second.post(f"{PREFIX}/intake/steps", json={"key": "s8", "lane_key": "ops", "label": "Two"})
    ).status_code == 201
    assert (await second.patch(f"{PREFIX}/intake/steps/s1", json={"label": "Renamed"})).status_code == 200
    plan = await _get(first)
    assert {"s7", "s8"} <= {s["key"] for s in plan["steps"]}
    assert next(s for s in plan["steps"] if s["key"] == "s1")["label"] == "Renamed"
    assert {s["key"] for s in stale["steps"]} == {"s1", "s2", "s3"}


async def test_control_replacing_the_whole_map_from_a_stale_view_loses_the_other_edit(edit):
    admin, _, _ = edit
    stale = await _get(admin)
    assert (await _call(admin, "add_step")).status_code == 201
    body = {k: stale[k] for k in ("lanes", "steps", "edges")}
    assert (await admin.put(f"{PREFIX}/intake/map", json=body)).status_code == 200
    assert "s9" not in {s["key"] for s in (await _get(admin))["steps"]}  # the problem the new routes remove


async def test_a_role_removed_from_an_untouched_lane_does_not_block_an_unrelated_edit(edit):
    admin, role, factory = edit
    async with factory() as s:
        await s.execute(delete(Role).where(Role.id == role))
        await s.commit()
    assert (await admin.delete(f"{PREFIX}/intake/edges/s2/s3")).status_code == 200  # the lane is not this edit's
    assert (await admin.post(f"{PREFIX}/intake/steps", json=ROUTES["add_step"][2])).status_code == 201
    # contrast: touching that lane, or replacing the whole map, checks its role
    assert (await admin.patch(f"{PREFIX}/intake/lanes/ops", json={"name": "Ops"})).status_code == 404
    plan = await _get(admin)
    body = {k: plan[k] for k in ("lanes", "steps", "edges")}
    assert (await admin.put(f"{PREFIX}/intake/map", json=body)).status_code == 404
