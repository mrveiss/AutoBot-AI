# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Review fixes on the plan edit routes (#20086): plan-wide keys, admin row lock, pending-first match."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from llc.services.company_os import plan_breakdown, plan_store
from llc.services.company_os.errors import GraphInvalid
from models.approval import ApprovalStatus
from services import ai_line_change_proposal as proposal


class _Item(SimpleNamespace):
    def model_copy(self, update):
        return _Item(**{**self.__dict__, **update})


def _plan(other_sub="x", other_case="c"):
    return SimpleNamespace(
        sub_steps=[_Item(key=other_sub, step_key="other")],
        edge_cases=[_Item(key=other_case, step_key="other")],
        one_number=SimpleNamespace(step_key="s"),
        by_hand_acknowledged_at=None,
    )


@pytest.fixture(autouse=True)
def _step(monkeypatch):
    monkeypatch.setattr(plan_breakdown, "find_step", lambda _p, _k: SimpleNamespace(lane_key="l"))
    monkeypatch.setattr(plan_breakdown, "_breakdown_errors", lambda _s, _c: [])


def test_a_sub_step_key_used_on_another_step_is_refused():
    with pytest.raises(GraphInvalid):
        plan_breakdown.replace_breakdown(_plan(), "s", [_Item(key="x")], [])


def test_an_edge_case_key_used_on_another_step_is_refused():
    with pytest.raises(GraphInvalid):
        plan_breakdown.replace_breakdown(_plan(), "s", [], [_Item(key="c")])


def test_fresh_keys_and_the_steps_own_keys_still_replace():
    plan = _plan()
    plan.sub_steps.append(_Item(key="mine", step_key="s"))
    plan_breakdown.replace_breakdown(plan, "s", [_Item(key="mine")], [_Item(key="new")])
    assert {s.key for s in plan.sub_steps} == {"x", "mine"}


@pytest.mark.asyncio
async def test_locked_plan_locks_the_admin_membership_row(monkeypatch):
    seen = {}

    async def _admin(_session, _company, _actor, **kw):
        seen.update(kw)

    async def _writable(*_a):
        return None

    monkeypatch.setattr(plan_store, "require_company_admin", _admin)
    monkeypatch.setattr(plan_store, "load_writable", _writable)
    monkeypatch.setattr(plan_store, "read_plan", lambda _row: None)
    await plan_store.locked_plan(None, uuid.uuid4(), "k", uuid.uuid4())
    assert seen == {"for_update": True}


@pytest.mark.asyncio
async def test_a_pending_request_wins_over_a_decided_one_for_the_same_plan():
    ctx = {"action": "a", "action_key": "k", "line": "l", "scope_id": "s", "plan_ref": "p"}
    decided = SimpleNamespace(status=ApprovalStatus.APPROVED.value, context=ctx)
    pending = SimpleNamespace(status=ApprovalStatus.PENDING.value, context=ctx)

    class _Session:
        async def execute(self, _stmt):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [decided, pending]))

    found = await proposal._pending_match(
        _Session(), company_id=uuid.uuid4(), requester="r", wanted=("a", "k", "l", "s"), plan_ref="p"
    )
    assert found is pending
