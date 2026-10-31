# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Workflow plan follow-ups through the real routes: who acknowledges, what an edit voids, the wait clamp (#20187)."""

# flake8: noqa: F811 -- imported pytest fixtures are redefined as test arguments
from __future__ import annotations

import pytest

import llc.services.company_os.plan_convert as convert_mod
from llc.tests.test_company_os_plan_convert_19936 import (  # noqa: F401 -- fixtures are used by name
    ADMIN_A,
    COMPANY_A,
    PREFIX,
    _approved,
    _client,
    _labeled,
    _outside_world,
    ctx,
    factory,
)

pytestmark = pytest.mark.asyncio

RUN_JWT = {"auth_method": "run_jwt", "username": "run:abc"}
DEVICE = {"auth_method": "device", "username": "device:abc"}


@pytest.mark.parametrize("credential", [RUN_JWT, DEVICE])
async def test_a_non_human_admin_cannot_acknowledge_by_hand(ctx, credential):
    admin, role, factory = ctx
    await _labeled(admin, role)
    agent = _client(factory, COMPANY_A, ADMIN_A, credential)
    assert (await agent.post(f"{PREFIX}/intake/by-hand-acknowledgement")).status_code == 403
    assert (await admin.get(f"{PREFIX}/intake")).json()["by_hand_acknowledged_at"] is None
    assert (await admin.post(f"{PREFIX}/intake/by-hand-acknowledgement")).status_code == 200  # contrast: a person


_EDITS = [
    ("patch", "", {"name": "Edited"}),
    (
        "put",
        "/steps/s1/metric",
        {"frequency": {"value": 9, "unit": "per_week"}, "duration": {"value": 1, "unit": "hours"}},
    ),
    ("patch", "/sub-steps/p2", {"rationale": "x"}),
    ("put", "/approval-policies", {"policies": []}),
]


@pytest.mark.parametrize("verb,path,body", _EDITS)
async def test_any_ordinary_edit_voids_the_acknowledgement(ctx, verb, path, body):
    admin, role, _ = ctx
    await _labeled(admin, role)
    assert (await admin.post(f"{PREFIX}/intake/by-hand-acknowledgement")).json()["by_hand_acknowledged_at"]
    r = await getattr(admin, verb)(f"{PREFIX}/intake{path}", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["by_hand_acknowledged_at"] is None


async def test_the_preview_and_the_approval_keep_the_acknowledgement(ctx):
    admin, role, _ = ctx
    plan = await _approved(admin, role)
    got = (await admin.get(f"{PREFIX}/intake")).json()
    assert got["status"] == "approved" and got["by_hand_acknowledged_at"] is not None
    assert plan is not None


@pytest.mark.parametrize("configured", [0, -30])
async def test_a_zero_or_negative_wait_setting_is_clamped_before_the_timeout_transitions(ctx, monkeypatch, configured):
    admin, role, _ = ctx
    monkeypatch.setattr(convert_mod, "APPROVAL_WAIT_SECONDS", configured)
    await _approved(admin, role)
    assert (await admin.post(f"{PREFIX}/intake/convert")).status_code == 200
    g = (await admin.get("/api/llc/company-os/workflows/intake.ops/graph")).json()
    waits = [t["timeout_seconds"] for t in g["graph"]["transitions"] if t["kind"] == "timeout"]
    assert waits == [convert_mod.MIN_APPROVAL_WAIT_SECONDS]


async def test_a_policy_on_a_by_hand_or_current_sub_step_is_refused(ctx):
    admin, role, _ = ctx
    await _labeled(admin, role)
    for target in ("p3", "c1"):
        body = {"policies": [{"key": "g", "sub_step_keys": [target], "on_timeout": "hold", "wait_limit": False}]}
        r = await admin.put(f"{PREFIX}/intake/approval-policies", json=body)
        assert r.status_code == 422, (target, r.text)
    assert (await admin.get(f"{PREFIX}/intake")).json()["approval_policies"] == []
