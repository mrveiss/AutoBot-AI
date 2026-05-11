# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for #7268 Phase 1 — StrategyPlanner skill_router plan-time binding.

Pins the wire-in contract introduced by ADR-006 Phase 1:
- ``WorkflowTask`` exposes ``skill_name`` / ``skill_action`` / ``skill_resolution_method``
- ``StrategyPlanner.build_workflow_plan`` is async + invokes skill_router with ``dry_run=True``
- A successful skill_router result populates the new fields on each task
- A failure (exception, missing router, ``success: False``) leaves them None
- Lookup never auto-enables skills or fires Phase 3 gap-fill at plan time
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Make ``autobot-backend`` importable for bare ``enhanced_orchestration.*`` imports.
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------------------------------------------------------------------------
# Field surface (#7268 Phase 1)
# ---------------------------------------------------------------------------


def test_workflow_task_has_skill_binding_fields() -> None:
    """Canonical WorkflowTask must expose the 3 skill-binding fields."""
    from autobot_shared.workflow.types import WorkflowTask

    field_names = {f.name for f in dataclasses.fields(WorkflowTask)}
    for required in ("skill_name", "skill_action", "skill_resolution_method"):
        assert required in field_names, f"WorkflowTask missing #{required} (#7268 Phase 1)"

    # Defaults are None — task with no skill binding is the unaltered legacy shape
    t = WorkflowTask(task_id="x")
    assert t.skill_name is None
    assert t.skill_action is None
    assert t.skill_resolution_method is None


# ---------------------------------------------------------------------------
# StrategyPlanner: async + skill_router invocation
# ---------------------------------------------------------------------------


@pytest.fixture
def planner():
    from enhanced_orchestration.workflow_planning import StrategyPlanner

    return StrategyPlanner(agent_capabilities={})


@pytest.fixture
def plan_data():
    return {
        "strategy": "sequential",
        "tasks": [
            {
                "agent": "classifier",
                "action": "classify",
                "task": "classify the user's intent",
            },
            {
                "agent": "researcher",
                "action": "search",
                "explanation": "search the knowledge base",
            },
        ],
    }


@pytest.mark.asyncio
async def test_build_workflow_plan_is_async(planner, plan_data) -> None:
    """build_workflow_plan must be a coroutine (Phase 1 made it async)."""
    import inspect

    assert inspect.iscoroutinefunction(planner.build_workflow_plan)


@pytest.mark.asyncio
async def test_skill_router_dry_run_only_no_auto_enable(monkeypatch, planner, plan_data) -> None:
    """Plan-time lookup must always pass ``dry_run=True`` (no auto-enable)."""
    fake_router = MagicMock()
    fake_router.execute = AsyncMock(return_value={"success": False})
    planner._skill_router_skill = fake_router  # bypass lazy init

    await planner.build_workflow_plan("goal", plan_data)

    assert fake_router.execute.call_count == len(plan_data["tasks"])
    for call in fake_router.execute.call_args_list:
        args, _kwargs = call
        assert args[0] == "find_skill"
        params = args[1]
        assert params["dry_run"] is True, "Phase 1 must NOT auto-enable at plan time"


@pytest.mark.asyncio
async def test_successful_lookup_populates_skill_fields(monkeypatch, planner, plan_data) -> None:
    """When skill_router returns success, attach skill_name + method to the task."""
    fake_router = MagicMock()
    fake_router.execute = AsyncMock(
        return_value={
            "success": True,
            "enabled_skill": "intent_classifier",
            "method": "llm",
            "candidates": [{"name": "intent_classifier", "score": 0.9}],
        }
    )
    planner._skill_router_skill = fake_router

    plan = await planner.build_workflow_plan("test goal", plan_data)

    assert len(plan.tasks) == 2
    for task in plan.tasks:
        assert task.skill_name == "intent_classifier"
        assert task.skill_action == "execute"
        assert task.skill_resolution_method == "llm"


@pytest.mark.asyncio
async def test_no_match_leaves_skill_fields_none(planner, plan_data) -> None:
    """``success: False`` keeps skill_name=None — legacy routing fallback."""
    fake_router = MagicMock()
    fake_router.execute = AsyncMock(return_value={"success": False, "error": "no match"})
    planner._skill_router_skill = fake_router

    plan = await planner.build_workflow_plan("goal", plan_data)
    for task in plan.tasks:
        assert task.skill_name is None
        assert task.skill_action is None
        assert task.skill_resolution_method is None


@pytest.mark.asyncio
async def test_router_exception_leaves_skill_fields_none(planner, plan_data) -> None:
    """Exception during lookup is best-effort — task still produced, no skill bound."""
    fake_router = MagicMock()
    fake_router.execute = AsyncMock(side_effect=RuntimeError("registry offline"))
    planner._skill_router_skill = fake_router

    plan = await planner.build_workflow_plan("goal", plan_data)
    for task in plan.tasks:
        assert task.skill_name is None


@pytest.mark.asyncio
async def test_router_unavailable_silent_fallback(monkeypatch, planner, plan_data) -> None:
    """If skill_router cannot be instantiated, plan-build still succeeds."""
    # Force the lazy init to fail by monkeypatching the import path
    import enhanced_orchestration.workflow_planning as wp

    wp.StrategyPlanner._get_skill_router

    def _stub(self):
        return None

    monkeypatch.setattr(wp.StrategyPlanner, "_get_skill_router", _stub)

    plan = await planner.build_workflow_plan("goal", plan_data)
    assert len(plan.tasks) == 2
    for task in plan.tasks:
        assert task.skill_name is None  # legacy capability-based routing intact
