# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One Number candidates are ranked by frequency x duration, and ranking sets nothing (#20037, FR-3.1)."""

# flake8: noqa: F811 -- imported pytest fixtures are redefined as test arguments
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from llc.models.goal import LLCGoal
from llc.tests.test_company_os_plan_convert_19936 import (  # noqa: F401 -- fixtures are used by name
    ADMIN_A,
    ADMIN_B,
    COMPANY_A,
    COMPANY_B,
    PREFIX,
    _outside_world,
    ctx,
    factory,
)
from llc.tests.test_company_os_workflow_plans_19934 import _plan_body
from llc.tests.test_workflow_plan_edit_routes_20086 import _client

pytestmark = pytest.mark.asyncio

URL = f"{PREFIX}/intake/one-number/candidates"


def _metric(per_week: float, value: float, unit: str) -> dict:
    return {"frequency": {"value": per_week, "unit": "per_week"}, "duration": {"value": value, "unit": unit}}


async def _plan(factory, role):
    admin = _client(factory, COMPANY_A, ADMIN_A)
    assert (await admin.post(PREFIX, json=_plan_body(role))).status_code == 201
    return admin


async def _ranked(admin, kind: str = "hours_back") -> dict:
    r = await admin.get(URL, params={"return_kind": kind})
    assert r.status_code == 200, r.text
    return r.json()


async def test_steps_rank_by_frequency_times_duration_in_hours(ctx):
    _, role, factory = ctx
    admin = await _plan(factory, role)
    # s1: 5 x 2 h = 10; s2: 2 x 600 min = 20; s3: 1 x 2 days = 48
    for step, metric in (
        ("s1", _metric(5, 2, "hours")),
        ("s2", _metric(2, 600, "minutes")),
        ("s3", _metric(1, 2, "days")),
    ):
        assert (await admin.put(f"{PREFIX}/intake/steps/{step}/metric", json=metric)).status_code == 200
    body = await _ranked(admin)
    assert [(c["rank"], c["step_key"], c["score"]) for c in body["candidates"]] == [
        (1, "s3", 48),
        (2, "s2", 20),
        (3, "s1", 10),
    ]
    assert body["candidates"][0] | {"label": "Confirm"} == body["candidates"][0]
    assert (body["candidates"][1]["frequency_per_week"], body["candidates"][1]["duration_hours"]) == (2, 10)
    assert body["unmeasured"] == [] and body["return_kind"] == "hours_back"


async def test_a_step_without_a_metric_is_listed_apart_and_never_ranked(ctx):
    _, role, factory = ctx
    admin = await _plan(factory, role)
    assert (await admin.put(f"{PREFIX}/intake/steps/s2/metric", json=_metric(3, 1, "hours"))).status_code == 200
    body = await _ranked(admin)
    assert [c["step_key"] for c in body["candidates"]] == ["s2"]
    assert body["unmeasured"] == ["s1", "s3"]


async def test_equal_scores_keep_the_order_the_map_was_drawn_in(ctx):
    _, role, factory = ctx
    admin = await _plan(factory, role)
    for step in ("s3", "s1", "s2"):
        assert (await admin.put(f"{PREFIX}/intake/steps/{step}/metric", json=_metric(1, 1, "hours"))).status_code == 200
    assert [c["step_key"] for c in (await _ranked(admin))["candidates"]] == ["s1", "s2", "s3"]


@pytest.mark.parametrize("kind", ["hours_back", "more_yeses", "money_sooner"])
async def test_the_return_kind_is_required_and_echoed_and_weighs_every_step_alike(ctx, kind):
    _, role, factory = ctx
    admin = await _plan(factory, role)
    assert (await admin.put(f"{PREFIX}/intake/steps/s1/metric", json=_metric(4, 3, "hours"))).status_code == 200
    body = await _ranked(admin, kind)
    assert body["return_kind"] == kind and body["candidates"][0]["score"] == 12


async def test_a_missing_or_unknown_return_kind_is_422(ctx):
    _, role, factory = ctx
    admin = await _plan(factory, role)
    assert (await admin.get(URL)).status_code == 422
    assert (await admin.get(URL, params={"return_kind": "fame"})).status_code == 422


async def test_ranking_creates_no_one_number_and_no_goal_and_writes_nothing(ctx):
    _, role, factory = ctx
    admin = await _plan(factory, role)
    assert (await admin.put(f"{PREFIX}/intake/steps/s1/metric", json=_metric(4, 3, "hours"))).status_code == 200
    before = (await admin.get(f"{PREFIX}/intake")).json()
    await _ranked(admin)
    after = (await admin.get(f"{PREFIX}/intake")).json()
    assert after == before and after["one_number"] is None
    async with factory() as s:
        assert (await s.execute(select(func.count()).select_from(LLCGoal))).scalar_one() == 0


async def test_another_company_gets_404_and_a_missing_plan_is_404(ctx):
    _, role, factory = ctx
    await _plan(factory, role)
    other = _client(factory, COMPANY_B, ADMIN_B)
    assert (await other.get(URL, params={"return_kind": "hours_back"})).status_code == 404
    mine = _client(factory, COMPANY_A, ADMIN_A)
    assert (
        await mine.get(f"{PREFIX}/nope/one-number/candidates", params={"return_kind": "hours_back"})
    ).status_code == 404
