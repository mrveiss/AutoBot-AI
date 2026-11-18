# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# flake8: noqa: F811 -- imported pytest fixtures are redefined as test arguments
"""By Hand stays with a person; AI-line proposals follow the committed conversion (#19936).

Same harness as ``test_company_os_plan_convert_19936`` (its fixtures and helpers are reused).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import llc.services.company_os.plan_convert_lines as lines_mod
from llc.models.enums import RoleHolderType
from llc.models.role_assignment import LLCRoleAssignment
from llc.tests.test_company_os_plan_convert_19936 import (  # noqa: F401 -- fixtures are used by name
    ADMIN_A,
    ADMIN_B,
    COMPANY_A,
    COMPANY_B,
    MEMBER_A,
    PREFIX,
    Approval,
    LLCProcess,
    Workflow,
    _approved,
    _client,
    _count,
    _labeled,
    _outside_world,
    _people_safe,
    _role,
    ctx,
    factory,
)


async def test_a_by_hand_node_is_refused_when_an_agent_also_holds_the_role(factory):
    role = await _role(factory, COMPANY_A, "Shared desk")  # a person holds it ...
    async with factory() as s:  # ... and so does an agent
        s.add(
            LLCRoleAssignment(
                id=uuid.uuid4(),
                company_id=COMPANY_A,
                role_id=role,
                holder_type=RoleHolderType.AGENT.value,
                holder_agent_id=uuid.uuid4(),
            )
        )
        await s.commit()
    admin = _client(factory, COMPANY_A, ADMIN_A)
    await _labeled(admin, role)
    await _people_safe(admin)
    conv = (await admin.post(f"{PREFIX}/intake/convert/preview")).json()
    assert any("an agent also holds" in e for e in conv["contract_errors"])
    assert (await admin.post(f"{PREFIX}/intake/approve")).status_code == 409


async def test_a_hold_policy_has_no_timeout_and_the_policies_ride_the_committed_conversion(ctx):
    admin, role, _ = ctx
    await _labeled(admin, role)
    hold = {"policies": [{"key": "gate-1", "sub_step_keys": ["p1"], "on_timeout": "hold", "wait_limit": True}]}
    assert (await admin.put(f"{PREFIX}/intake/approval-policies", json=hold)).status_code == 200
    assert (await admin.post(f"{PREFIX}/intake/by-hand-acknowledgement")).status_code == 200
    assert (await admin.post(f"{PREFIX}/intake/convert/preview")).status_code == 200
    assert (await admin.post(f"{PREFIX}/intake/approve")).status_code == 200
    plan = (await admin.post(f"{PREFIX}/intake/convert")).json()
    g = (await admin.get("/api/llc/company-os/workflows/intake.ops/graph")).json()
    assert [t for t in g["graph"]["transitions"] if t["kind"] == "timeout"] == []
    assert [(p["key"], p["on_timeout"]) for p in plan["conversion"]["approval_policies"]] == [("gate-1", "hold")]


async def test_approving_needs_a_person_not_an_agent_credential(ctx):
    admin, role, factory = ctx
    await _labeled(admin, role)
    await _people_safe(admin)
    assert (await admin.post(f"{PREFIX}/intake/convert/preview")).status_code == 200
    agent = _client(factory, COMPANY_A, ADMIN_A, {"auth_method": "run_jwt", "username": "run:abc"})
    assert (await agent.post(f"{PREFIX}/intake/approve")).status_code == 403
    assert (await admin.get(f"{PREFIX}/intake")).json()["approved_at"] is None


async def test_a_commit_failure_files_no_proposal_and_leaves_the_plan_approved(ctx, monkeypatch):
    admin, role, factory = ctx
    await _approved(admin, role)

    async def _no_commit(self):
        raise RuntimeError("commit failed")

    real_commit = AsyncSession.commit
    monkeypatch.setattr(AsyncSession, "commit", _no_commit)
    with pytest.raises(RuntimeError):
        await admin.post(f"{PREFIX}/intake/convert")
    monkeypatch.setattr(AsyncSession, "commit", real_commit)
    assert await _count(factory, Approval, None) == 0
    assert await _count(factory, Workflow) == 0 and await _count(factory, LLCProcess) == 0
    assert (await admin.get(f"{PREFIX}/intake")).json()["status"] == "approved"


async def test_a_proposal_failure_keeps_the_conversion_records_it_and_the_retry_fixes_it(ctx, monkeypatch):
    admin, role, factory = ctx
    await _approved(admin, role)
    real = lines_mod.propose_line_change

    async def _down(**kw):
        raise ConnectionError("approvals store down")

    monkeypatch.setattr(lines_mod, "propose_line_change", _down)
    r = await admin.post(f"{PREFIX}/intake/convert")
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["status"] == "converted" and await _count(factory, Workflow) == 1
    assert {p["outcome"] for p in plan["conversion"]["ai_line_proposals"]} == {"failed"}
    assert {p["error"] for p in plan["conversion"]["ai_line_proposals"]} == {"ConnectionError"}
    assert await _count(factory, Approval, None) == 0
    monkeypatch.setattr(lines_mod, "propose_line_change", real)
    url = f"{PREFIX}/intake/convert/retry-ai-line-proposals"
    first = (await admin.post(url)).json()["conversion"]["ai_line_proposals"]
    assert {p["outcome"] for p in first} == {"filed"} and all(p["approval_id"] and p["error"] is None for p in first)
    assert await _count(factory, Approval, None) == 2
    again = (await admin.post(url)).json()["conversion"]["ai_line_proposals"]
    assert again == first and await _count(factory, Approval, None) == 2
    assert (await admin.get(f"{PREFIX}/intake")).json()["status"] == "converted"


async def test_the_retry_route_is_for_a_person_admin_of_a_converted_plan_only(ctx):
    admin, role, factory = ctx
    url = f"{PREFIX}/intake/convert/retry-ai-line-proposals"
    await _approved(admin, role)
    assert (await admin.post(url)).status_code == 409  # not converted yet
    assert (await admin.post(f"{PREFIX}/intake/convert")).status_code == 200
    assert (await _client(factory, COMPANY_A, MEMBER_A).post(url)).status_code == 403
    assert (await _client(factory, COMPANY_B, ADMIN_B).post(url)).status_code == 404
    agent = _client(factory, COMPANY_A, ADMIN_A, {"auth_method": "run_jwt", "username": "run:abc"})
    assert (await agent.post(url)).status_code == 403
    assert await _count(factory, Approval, None) == 2
