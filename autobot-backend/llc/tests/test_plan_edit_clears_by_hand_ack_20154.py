# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An owner's By Hand acknowledgement covers the plan they saw, not a later edit (#19936)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from llc.services.company_os import plan_breakdown


def _sub_step(key: str) -> SimpleNamespace:
    return SimpleNamespace(
        key=key, state=None, step_key="s", model_copy=lambda update: SimpleNamespace(key=key, **update)
    )


def _plan() -> SimpleNamespace:
    return SimpleNamespace(
        sub_steps=[_sub_step("a")],
        edge_cases=[],
        one_number=SimpleNamespace(step_key="s"),
        by_hand_acknowledged_at=datetime.now(timezone.utc),
    )


def test_a_relabel_clears_the_acknowledgement():
    plan = _plan()
    plan_breakdown.relabel_sub_step(plan, "a", {"rationale": "changed"})
    assert plan.by_hand_acknowledged_at is None


def test_a_replaced_breakdown_clears_the_acknowledgement(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(plan_breakdown, "find_step", lambda _plan, _key: SimpleNamespace(lane_key="l"))
    monkeypatch.setattr(plan_breakdown, "_breakdown_errors", lambda _subs, _cases: [])
    plan_breakdown.replace_breakdown(plan, "s", [], [])
    assert plan.by_hand_acknowledged_at is None
