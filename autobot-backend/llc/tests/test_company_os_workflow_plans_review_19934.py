# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Workflow Planner: who may hold a lock, whose goal gets renamed, and revision edge cases (#19934)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from llc.models.goal import LLCGoal
from llc.services.authz import NotAuthorisedError
from llc.services.company_os import plan_store
from llc.services.company_os.plans import CompanyOsPlanService
from llc.tests import test_company_os_workflow_plans_19934 as base
from llc.tests.test_company_os_workflow_plans_19934 import COMPANY_A, MEMBER_A, ONE, PREFIX, _measure

pytestmark = pytest.mark.asyncio

#: The sibling module's fixtures: the same schema, plan and clients.
_planner_on, factory, ctx = base._planner_on, base.factory, base.ctx


async def test_a_refused_metric_write_takes_no_row_lock(ctx):
    _, _, factory = ctx
    async with factory() as session:
        with patch.object(plan_store, "load_writable", AsyncMock()) as lock:
            with pytest.raises(NotAuthorisedError):
                await CompanyOsPlanService().put_metric(
                    session, COMPANY_A, "intake", "s1", actor=MEMBER_A, frequency=(1, "per_week"), duration=(1, "hours")
                )
    lock.assert_not_awaited()


async def test_linking_someone_elses_goal_does_not_rename_it(ctx):
    admin, _, factory = ctx
    await _measure(admin)
    async with factory() as s:
        goal = LLCGoal(id=uuid.uuid4(), company_id=str(COMPANY_A), title="Theirs", level="key_result", status="active")
        s.add(goal)
        await s.commit()
    assert (await admin.put(f"{PREFIX}/intake/one-number", json={**ONE, "goal_id": str(goal.id)})).status_code == 200
    assert (await admin.put(f"{PREFIX}/intake/one-number", json={**ONE, "title": "Renamed"})).status_code == 200
    async with factory() as s:
        assert (await s.get(LLCGoal, goal.id)).title == "Theirs"


async def test_renaming_the_one_number_renames_the_goal_the_plan_made(ctx):
    admin, _, factory = ctx
    await _measure(admin)
    one = (await admin.put(f"{PREFIX}/intake/one-number", json={**ONE, "title": "Renamed"})).json()["one_number"]
    async with factory() as s:
        assert (await s.get(LLCGoal, uuid.UUID(one["goal_id"]))).title == "Renamed"


async def test_revision_zero_is_a_404_not_the_latest(ctx):
    admin, _, _ = ctx
    assert (await admin.get(f"{PREFIX}/intake/revisions/0")).status_code == 404
