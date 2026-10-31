# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Plan conversion follow-ups: one approval type, no second request for a decided proposal, policies stated as unenforced (#20115)."""

# flake8: noqa: F811 -- imported pytest fixtures are redefined as test arguments
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select, update

import llc.services.company_os.plan_store as store_mod
from llc.models.company_os_plan import CompanyOsWorkflowPlan
from llc.services.company_os.plan_types import TURN_ON_TRACKING_ISSUE, PlanApprovalPolicy
from llc.tests.test_company_os_plan_convert_19936 import (  # noqa: F401 -- fixtures are used by name
    ADMIN_A,
    COMPANY_A,
    PREFIX,
    _approved,
    _client,
    _count,
    _labeled,
    _outside_world,
    ctx,
    factory,
)
from models.approval import Approval, ApprovalStatus, ApprovalType

pytestmark = pytest.mark.asyncio

PLAN_TYPES = Path(store_mod.__file__).with_name("plan_types.py")


# ------------------------------------------------------------------ one definition of the approval type


def test_the_plan_policy_uses_the_canonical_approval_type_and_defines_none_of_its_own():
    policy = PlanApprovalPolicy(key="g")
    assert policy.approval_type is ApprovalType.WORKFLOW_GATE
    assert PlanApprovalPolicy.model_validate({"key": "g", "approval_type": "workflow_gate"}) == policy
    assert policy.model_dump(mode="json")["approval_type"] == "workflow_gate"
    source = PLAN_TYPES.read_text(encoding="utf-8")
    assert "class PlanApprovalType" not in source and '"workflow_gate"' not in source


@pytest.mark.parametrize("other", [t.value for t in ApprovalType if t is not ApprovalType.WORKFLOW_GATE])
def test_a_policy_names_no_other_approval_type(other):
    with pytest.raises(ValueError):
        PlanApprovalPolicy.model_validate({"key": "g", "approval_type": other})


# ------------------------------------------------------------------ a retry never files a decided proposal again


async def _convert_that_loses_its_outcomes(admin, monkeypatch) -> None:
    """Convert; the proposals file, then saving their outcomes fails, so the plan still says unfiled."""
    real, calls = store_mod.save_plan, []

    async def _save(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:  # the first save is the conversion itself, the second records the outcomes
            raise RuntimeError("save failed after the proposals were filed")
        return await real(*args, **kwargs)

    monkeypatch.setattr(store_mod, "save_plan", _save)
    with pytest.raises(RuntimeError):
        await admin.post(f"{PREFIX}/intake/convert")
    monkeypatch.setattr(store_mod, "save_plan", real)


_DECISIONS = [
    (ApprovalStatus.APPROVED, "filed"),
    (ApprovalStatus.REJECTED, "declined"),
    (ApprovalStatus.REVISION_REQUESTED, "declined"),
]


@pytest.mark.parametrize("decision,outcome", _DECISIONS)
async def test_a_retry_after_a_person_decided_files_nothing_again_and_records_what_happened(
    ctx, monkeypatch, decision, outcome
):
    admin, role, factory = ctx
    await _approved(admin, role)
    await _convert_that_loses_its_outcomes(admin, monkeypatch)
    stored = (await admin.get(f"{PREFIX}/intake")).json()["conversion"]["ai_line_proposals"]
    assert {p["outcome"] for p in stored} == {"unfiled"} and await _count(factory, Approval, None) == 2
    async with factory() as s:  # a person decides both requests before anyone retries
        await s.execute(update(Approval).values(status=decision.value))
        await s.commit()
    url = f"{PREFIX}/intake/convert/retry-ai-line-proposals"
    r = await admin.post(url)
    assert r.status_code == 200, r.text
    filed = r.json()["conversion"]["ai_line_proposals"]
    assert await _count(factory, Approval, None) == 2  # not four
    assert {p["outcome"] for p in filed} == {outcome} and all(p["approval_id"] for p in filed)
    async with factory() as s:
        ids = {str(i) for i in (await s.execute(select(Approval.id))).scalars()}
    assert {p["approval_id"] for p in filed} == ids
    again = (await admin.post(url)).json()["conversion"]["ai_line_proposals"]
    assert again == filed and await _count(factory, Approval, None) == 2  # a settled outcome is not revisited


def _under_the_old_ref(monkeypatch):
    """File through the real function, but under the reference a plan used before it carried a revision.

    Returns the function that puts the real one back.
    """
    import llc.services.company_os.plan_convert_lines as lines_mod

    real = lines_mod.propose_line_change

    async def _old(**kw):
        return await real(**{**kw, "plan_ref": "workflow-plan:intake", "legacy_plan_refs": ()})

    monkeypatch.setattr(lines_mod, "propose_line_change", _old)
    return lambda: monkeypatch.setattr(lines_mod, "propose_line_change", real)


async def test_a_pending_request_filed_under_the_old_reference_is_not_filed_twice(ctx, monkeypatch):
    admin, role, factory = ctx
    await _approved(admin, role)
    restore = _under_the_old_ref(monkeypatch)
    await _convert_that_loses_its_outcomes(admin, monkeypatch)
    restore()  # the retry runs the real code, under the new reference
    r = await admin.post(f"{PREFIX}/intake/convert/retry-ai-line-proposals")
    assert r.status_code == 200, r.text
    assert await _count(factory, Approval, None) == 2
    assert {p["outcome"] for p in r.json()["conversion"]["ai_line_proposals"]} == {"filed"}


async def test_control_a_decided_request_under_the_old_reference_does_not_match(ctx, monkeypatch):
    admin, role, factory = ctx
    await _approved(admin, role)
    restore = _under_the_old_ref(monkeypatch)
    await _convert_that_loses_its_outcomes(admin, monkeypatch)
    restore()
    async with factory() as s:
        await s.execute(update(Approval).values(status=ApprovalStatus.APPROVED.value))
        await s.commit()
    assert (await admin.post(f"{PREFIX}/intake/convert/retry-ai-line-proposals")).status_code == 200
    assert await _count(factory, Approval, None) == 4  # only a pending one is carried over


async def test_control_a_withdrawn_request_is_over_and_a_retry_may_file_a_new_one(ctx, monkeypatch):
    admin, role, factory = ctx
    await _approved(admin, role)
    await _convert_that_loses_its_outcomes(admin, monkeypatch)
    async with factory() as s:
        await s.execute(update(Approval).values(status=ApprovalStatus.WITHDRAWN.value))
        await s.commit()
    assert (await admin.post(f"{PREFIX}/intake/convert/retry-ai-line-proposals")).status_code == 200
    assert await _count(factory, Approval, None) == 4


# ------------------------------------------------------------------ the response says the policies are not enforced


def _stated(plan: dict) -> tuple:
    return plan["policy_enforcement"], plan["policy_enforcement_tracking_issue"]


async def test_an_approved_and_a_converted_plan_state_that_policies_are_not_enforced(ctx):
    admin, role, _ = ctx
    await _labeled(admin, role)
    assert _stated((await admin.get(f"{PREFIX}/intake")).json()) == (None, None)  # below approved: nothing to say
    await _approved_from_labeled(admin)
    approved = (await admin.get(f"{PREFIX}/intake")).json()
    assert approved["status"] == "approved" and _stated(approved) == ("not_enforced", TURN_ON_TRACKING_ISSUE)
    converted = (await admin.post(f"{PREFIX}/intake/convert")).json()
    assert converted["status"] == "converted" and _stated(converted) == ("not_enforced", TURN_ON_TRACKING_ISSUE)
    assert _stated((await admin.get(f"{PREFIX}/intake")).json()) == ("not_enforced", TURN_ON_TRACKING_ISSUE)
    assert TURN_ON_TRACKING_ISSUE == 16763


async def _approved_from_labeled(admin) -> None:
    from llc.tests.test_company_os_plan_convert_19936 import _people_safe

    await _people_safe(admin)
    assert (await admin.post(f"{PREFIX}/intake/convert/preview")).status_code == 200
    assert (await admin.post(f"{PREFIX}/intake/approve")).json()["status"] == "approved"


async def test_an_edit_that_drops_the_approval_drops_the_statement(ctx):
    admin, role, _ = ctx
    await _approved(admin, role)
    plan = (await admin.patch(f"{PREFIX}/intake", json={"name": "Renamed"})).json()
    assert plan["status"] == "labeled" and _stated(plan) == (None, None)


async def test_a_plan_stored_before_the_field_existed_still_states_it(ctx):
    admin, role, factory = ctx
    await _approved(admin, role)
    async with factory() as s:
        row = (await s.execute(select(CompanyOsWorkflowPlan))).scalar_one()
        row.document = {k: v for k, v in row.document.items() if not k.startswith("policy_enforcement")}
        await s.commit()
    assert _stated((await admin.get(f"{PREFIX}/intake")).json()) == ("not_enforced", TURN_ON_TRACKING_ISSUE)


# ------------------------------------------------------------------ the approval type round trip, and what is stored


def test_the_approval_type_round_trips_as_the_plain_string():
    body = {"key": "g", "approval_type": "workflow_gate", "sub_step_keys": ["p1"]}
    policy = PlanApprovalPolicy.model_validate(body)
    assert policy.approval_type is ApprovalType.WORKFLOW_GATE
    assert PlanApprovalPolicy.model_validate_json(json.dumps(body)) == policy
    assert policy.model_dump(mode="json")["approval_type"] == "workflow_gate"
    assert json.loads(policy.model_dump_json())["approval_type"] == "workflow_gate"
    assert PlanApprovalPolicy.model_validate(policy.model_dump(mode="json")) == policy


async def test_a_stored_plan_with_a_policy_reads_back_and_the_derived_fields_are_not_stored(ctx):
    admin, role, factory = ctx
    await _approved(admin, role)
    async with factory() as s:
        row = (await s.execute(select(CompanyOsWorkflowPlan))).scalar_one()
        stored = row.document
        assert stored["approval_policies"][0]["approval_type"] == "workflow_gate"
        assert "policy_enforcement" not in stored and "policy_enforcement_tracking_issue" not in stored
        assert store_mod.read_plan(row).approval_policies[0].approval_type is ApprovalType.WORKFLOW_GATE
    served = (await admin.get(f"{PREFIX}/intake")).json()
    assert served["policy_enforcement"] == "not_enforced"  # in the response all the same
    assert served["approval_policies"][0]["approval_type"] == "workflow_gate"
