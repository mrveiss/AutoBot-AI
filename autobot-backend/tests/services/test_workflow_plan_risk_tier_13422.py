# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A presented workflow plan carries each step's risk tier for the frontend badge (#13422).

``risk_level`` stays as sent (steps can carry free text from the canvas, or a Severity
spelling); ``risk_tier`` is the one four-rung ladder, or ``None`` when ungradable.
"""

from services.workflow_automation.models import PlanApprovalRequest, WorkflowStep


def _steps(*levels: str) -> list[dict]:
    steps = [
        WorkflowStep(step_id=f"s{i}", command="true", description="", risk_level=lvl) for i, lvl in enumerate(levels)
    ]
    plan = PlanApprovalRequest(workflow_id="w", plan_summary="", total_steps=len(steps), steps_preview=steps)
    return plan.to_presentation_dict()["steps"]


def test_each_step_gets_its_tier_beside_the_unchanged_risk_level():
    rows = _steps("low", "medium", "critical", "warning")
    assert [(r["risk_level"], r["risk_tier"]) for r in rows] == [
        ("low", "low"),
        ("medium", "medium"),
        ("critical", "critical"),
        ("warning", "medium"),
    ]


def test_free_text_from_the_canvas_gives_no_tier_rather_than_failing_the_plan():
    (row,) = _steps("pretty risky")
    assert row["risk_level"] == "pretty risky"
    assert row["risk_tier"] is None


def test_the_status_dict_the_runner_reads_carries_the_risk_it_never_had():
    status = WorkflowStep(step_id="s", command="true", description="", risk_level="HIGH").to_status_dict()
    assert (status["risk_level"], status["risk_tier"]) == ("HIGH", "high")
