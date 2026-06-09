# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
def strict_planner():
    """StrategyPlanner with strict_gap_fill=True for Phase 3 tests."""
    from enhanced_orchestration.workflow_planning import StrategyPlanner

    return StrategyPlanner(agent_capabilities={}, strict_gap_fill=True)


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


# ---------------------------------------------------------------------------
# #7431 Phase 3 — async gap-fill + BLOCKED plan state
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fresh_pending_skills():
    """Each Phase 3 test starts with an empty PendingSkillsRegistry."""
    from skills.pending_skills import reset_pending_skills_registry_for_tests

    reset_pending_skills_registry_for_tests()
    yield
    reset_pending_skills_registry_for_tests()


@pytest.mark.asyncio
async def test_no_winner_triggers_async_gap_fill_and_pending_id(strict_planner, plan_data) -> None:
    """When skill_router returns success=True with enabled_skill=None, the
    strict-mode planner triggers Phase 3 async gap-fill and attaches a
    pending_skill_id to each unbound task."""
    fake_router = MagicMock()
    fake_router.execute = AsyncMock(return_value={"success": True, "enabled_skill": None})
    strict_planner._skill_router_skill = fake_router

    plan = await strict_planner.build_workflow_plan("goal", plan_data)

    for task in plan.tasks:
        assert task.skill_name is None
        assert task.pending_skill_id is not None
    pids = [t.pending_skill_id for t in plan.tasks]
    assert len(pids) == len(set(pids))


@pytest.mark.asyncio
async def test_plan_status_blocked_when_any_task_pending(strict_planner, plan_data) -> None:
    """A plan with at least one pending_skill_id is constructed in BLOCKED state."""
    fake_router = MagicMock()
    fake_router.execute = AsyncMock(return_value={"success": True, "enabled_skill": None})
    strict_planner._skill_router_skill = fake_router

    plan = await strict_planner.build_workflow_plan("goal", plan_data)
    assert plan.status == "blocked"


@pytest.mark.asyncio
async def test_plan_status_pending_when_all_tasks_resolve(planner, plan_data) -> None:
    """When every task gets a skill, plan.status stays at default 'pending'."""
    fake_router = MagicMock()
    fake_router.execute = AsyncMock(return_value={"success": True, "enabled_skill": "good_skill", "method": "llm"})
    planner._skill_router_skill = fake_router

    plan = await planner.build_workflow_plan("goal", plan_data)
    assert plan.status == "pending"
    for task in plan.tasks:
        assert task.skill_name == "good_skill"
        assert task.pending_skill_id is None


@pytest.mark.asyncio
async def test_pending_binding_recorded_in_registry(strict_planner, plan_data) -> None:
    """Each pending_skill_id corresponds to a registered binding in PendingSkillsRegistry."""
    from skills.pending_skills import get_pending_skills_registry

    fake_router = MagicMock()
    fake_router.execute = AsyncMock(return_value={"success": True, "enabled_skill": None})
    strict_planner._skill_router_skill = fake_router

    plan = await strict_planner.build_workflow_plan("goal", plan_data)
    registry = get_pending_skills_registry()

    for task in plan.tasks:
        binding = registry.get(task.pending_skill_id)
        assert binding is not None
        assert binding.task_id == task.task_id


@pytest.mark.asyncio
async def test_no_match_unsuccessful_response_does_not_trigger_gap_fill(planner, plan_data) -> None:
    """success=False (router error) does NOT fire gap-fill — pending_skill_id stays None.
    Phase 3 is only triggered on the explicit "found no skill" outcome
    (success=True, enabled_skill=None), not on router errors."""
    from skills.pending_skills import get_pending_skills_registry

    fake_router = MagicMock()
    fake_router.execute = AsyncMock(return_value={"success": False, "error": "no match"})
    planner._skill_router_skill = fake_router

    plan = await planner.build_workflow_plan("goal", plan_data)
    for task in plan.tasks:
        assert task.pending_skill_id is None
    assert plan.status == "pending"  # not blocked
    assert get_pending_skills_registry().size() == 0


# ---------------------------------------------------------------------------
# ADR-006 strict/lenient mode + WorkflowPlanState (#7431)
# ---------------------------------------------------------------------------


def test_strict_gap_fill_default_is_lenient() -> None:
    """StrategyPlanner defaults to lenient mode (strict_gap_fill=False)."""
    from enhanced_orchestration.workflow_planning import StrategyPlanner

    p = StrategyPlanner(agent_capabilities={})
    assert p.strict_gap_fill is False


@pytest.mark.asyncio
async def test_lenient_mode_no_match_leaves_skill_name_none_no_gap_fill(planner, plan_data) -> None:
    """Lenient mode (default): no-skill-match leaves skill_name=None, no pending_skill_id, no gap-fill.

    The plan stays READY (status='pending') so legacy capability routing handles it.
    """
    from skills.pending_skills import get_pending_skills_registry

    fake_router = MagicMock()
    fake_router.execute = AsyncMock(return_value={"success": True, "enabled_skill": None})
    planner._skill_router_skill = fake_router

    plan = await planner.build_workflow_plan("goal", plan_data)

    for task in plan.tasks:
        assert task.skill_name is None
        assert task.pending_skill_id is None, "lenient mode must NOT set pending_skill_id"
    assert plan.status == "pending", "lenient mode must NOT block the plan"
    assert get_pending_skills_registry().size() == 0, "lenient mode must NOT register pending bindings"


@pytest.mark.asyncio
async def test_strict_mode_no_match_sets_pending_id_and_blocks(strict_planner, plan_data) -> None:
    """Strict mode: no-skill-match fires gap-fill, sets pending_skill_id, blocks plan."""
    from skills.pending_skills import get_pending_skills_registry

    fake_router = MagicMock()
    fake_router.execute = AsyncMock(return_value={"success": True, "enabled_skill": None})
    strict_planner._skill_router_skill = fake_router

    plan = await strict_planner.build_workflow_plan("goal", plan_data)

    assert plan.status == "blocked"
    for task in plan.tasks:
        assert task.pending_skill_id is not None
    assert get_pending_skills_registry().size() == len(plan.tasks)


# ---------------------------------------------------------------------------
# WorkflowPlanState enum (#7431)
# ---------------------------------------------------------------------------


def test_workflow_plan_state_ready_on_pending_plan() -> None:
    """WorkflowPlan.state returns READY when status is 'pending'."""
    from autobot_shared.workflow.types import WorkflowPlan, WorkflowPlanState

    plan = WorkflowPlan(plan_id="p1", goal="g", tasks=[], status="pending")
    assert plan.state is WorkflowPlanState.READY


def test_workflow_plan_state_blocked_on_skill_generation() -> None:
    """WorkflowPlan.state returns BLOCKED_ON_SKILL_GENERATION when status is 'blocked'."""
    from autobot_shared.workflow.types import WorkflowPlan, WorkflowPlanState

    plan = WorkflowPlan(plan_id="p2", goal="g", tasks=[], status="blocked")
    assert plan.state is WorkflowPlanState.BLOCKED_ON_SKILL_GENERATION


def test_workflow_plan_state_enum_has_required_members() -> None:
    """WorkflowPlanState must expose at least READY and BLOCKED_ON_SKILL_GENERATION (ADR-006)."""
    from autobot_shared.workflow.types import WorkflowPlanState

    assert hasattr(WorkflowPlanState, "READY")
    assert hasattr(WorkflowPlanState, "BLOCKED_ON_SKILL_GENERATION")
    assert WorkflowPlanState.READY.value == "ready"
    assert WorkflowPlanState.BLOCKED_ON_SKILL_GENERATION.value == "blocked_on_skill_generation"
