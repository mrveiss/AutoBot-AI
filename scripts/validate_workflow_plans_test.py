# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The example plans pass the real gate, and a planted missing handoff fails it (#20034, FR-1.3)."""

import json

import pytest

from llc.services.company_os import plan_gate
from scripts import validate_workflow_plans as v

EXAMPLES = sorted(v.EXAMPLES_DIR.glob("*.json"))


def test_there_are_two_examples():
    assert [p.name for p in EXAMPLES] == ["client-onboarding.json", "invoice-follow-up.json"]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_passes_the_real_gate(path):
    plan = v.load_plan(path)
    assert v.plan_problems(plan) == []
    assert any(h.from_lane != h.to_lane for h in plan.handoffs)
    assert v.negative_control(plan)


def test_validator_exits_zero_on_the_shipped_examples():
    assert v.main(["validate"]) == 0


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_planted_missing_handoff_fails_the_validator(path, tmp_path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["handoffs"] = doc["handoffs"][1:]
    (tmp_path / path.name).write_text(json.dumps(doc), encoding="utf-8")
    failures = v.validate_dir(tmp_path)
    assert any(v.HANDOFF_RULE in f for f in failures)
    assert v.main(["validate", str(tmp_path)]) == 1


def test_gate_is_the_service_gate_not_a_copy():
    assert v.evaluate_plan_gate is plan_gate.evaluate_plan_gate


def test_empty_directory_fails(tmp_path):
    assert v.validate_dir(tmp_path)


def _report(status, missing):
    return plan_gate.GateReport(status, None, missing)


def test_next_rung_gaps_at_the_declared_status_still_pass(monkeypatch):
    plan = v.load_plan(EXAMPLES[0])
    gaps = [plan_gate.Missing("G5", "next rung gap")]
    monkeypatch.setattr(v, "evaluate_plan_gate", lambda _p: _report(plan.status, gaps))
    assert v.plan_problems(plan) == []


def test_earning_less_than_declared_reports_the_gaps(monkeypatch):
    plan = v.load_plan(EXAMPLES[0])
    gaps = [plan_gate.Missing("G3", "no current sub-step")]
    low = type(plan.status).MEASURED
    monkeypatch.setattr(v, "evaluate_plan_gate", lambda _p: _report(low, gaps))
    problems = v.plan_problems(plan)
    assert any("G3" in p for p in problems) and any("earns" in p for p in problems)


def test_earning_more_than_declared_is_a_mismatch(monkeypatch):
    plan = v.load_plan(EXAMPLES[0]).model_copy(update={"status": type(v.load_plan(EXAMPLES[0]).status).MEASURED})
    monkeypatch.setattr(v, "evaluate_plan_gate", lambda _p: _report(type(plan.status).LABELED, []))
    assert any("earns" in p for p in v.plan_problems(plan))
