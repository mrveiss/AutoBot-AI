# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for GOAPPlanner A* search (GH#7354)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))


from orchestration.goap_planner import GOAPAction, GOAPPlanner
from orchestration.types import AgentCapability

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_planner() -> GOAPPlanner:
    """Planner with a minimal hand-crafted action set for deterministic tests."""
    actions = (
        GOAPAction("a", frozenset(), frozenset({"x"}), 1.0, AgentCapability.RESEARCH),
        GOAPAction("b", frozenset({"x"}), frozenset({"y"}), 1.0, AgentCapability.ANALYSIS),
        GOAPAction("c", frozenset({"y"}), frozenset({"z"}), 1.0, AgentCapability.CODE_GENERATION),
        GOAPAction("d_cheap", frozenset({"x"}), frozenset({"z"}), 0.5, AgentCapability.SYNTHESIS),
    )
    return GOAPPlanner(actions=actions)


# ---------------------------------------------------------------------------
# Basic A* correctness
# ---------------------------------------------------------------------------


def test_empty_initial_state_to_goal():
    """Plan from empty state to a reachable single-fact goal."""
    planner = _simple_planner()
    path = planner.plan(frozenset(), frozenset({"x"}))
    assert path is not None
    assert len(path) == 1
    assert path[0].name == "a"


def test_multi_step_plan():
    """Plan requiring three sequential actions returns them in order."""
    planner = _simple_planner()
    path = planner.plan(frozenset(), frozenset({"z"}))
    assert path is not None
    # Two paths exist: a→b→c (cost 3) or a→d_cheap (cost 1.5); cheapest wins.
    action_names = [a.name for a in path]
    assert action_names == ["a", "d_cheap"]


def test_already_satisfied_goal_returns_empty():
    """plan() returns [] when goal ⊆ initial_state."""
    planner = _simple_planner()
    path = planner.plan(frozenset({"x", "y", "z"}), frozenset({"z"}))
    assert path == []


def test_unreachable_goal_returns_none():
    """plan() returns None when no sequence of actions can reach the goal."""
    planner = _simple_planner()
    path = planner.plan(frozenset(), frozenset({"unreachable_fact"}))
    assert path is None


def test_cycle_detection_does_not_loop():
    """Planner terminates without infinite loops on cyclic action graphs."""
    # action X sets {a}, action Y sets {b} and requires {a}, action Z loops
    # back but produces nothing new — planner must terminate.
    cyclic_actions = (
        GOAPAction("x", frozenset(), frozenset({"a"}), 1.0, AgentCapability.RESEARCH),
        GOAPAction("y", frozenset({"a"}), frozenset({"b", "a"}), 1.0, AgentCapability.ANALYSIS),
        GOAPAction("loop", frozenset({"a"}), frozenset({"a"}), 0.1, AgentCapability.SYNTHESIS),
    )
    planner = GOAPPlanner(actions=cyclic_actions)
    path = planner.plan(frozenset(), frozenset({"b"}))
    assert path is not None
    assert any(a.name == "y" for a in path)


def test_multi_path_tie_breaking_by_cost():
    """When two paths have the same number of steps, the cheaper one wins."""
    actions = (
        GOAPAction("cheap_start", frozenset(), frozenset({"x"}), 0.5, AgentCapability.RESEARCH),
        GOAPAction("expensive_start", frozenset(), frozenset({"x"}), 10.0, AgentCapability.ANALYSIS),
        GOAPAction("finish", frozenset({"x"}), frozenset({"goal"}), 1.0, AgentCapability.CODE_GENERATION),
    )
    planner = GOAPPlanner(actions=actions)
    path = planner.plan(frozenset(), frozenset({"goal"}))
    assert path is not None
    assert path[0].name == "cheap_start"


# ---------------------------------------------------------------------------
# replan()
# ---------------------------------------------------------------------------


def test_replan_from_partial_state():
    """replan() continues from a mid-execution state rather than from scratch."""
    planner = _simple_planner()
    # "x" was already achieved by a completed step; only need to reach "z"
    path = planner.replan(frozenset({"x"}), frozenset({"z"}))
    assert path is not None
    assert path[0].name == "d_cheap"


def test_replan_returns_none_when_unreachable():
    """replan() returns None when no path exists from current_state."""
    # Use a planner whose only action requires a precondition that can never
    # be satisfied from the given initial state (all actions have preconditions).
    blocked_actions = (
        GOAPAction("gated", frozenset({"locked_gate"}), frozenset({"goal"}), 1.0, AgentCapability.RESEARCH),
    )
    planner = GOAPPlanner(actions=blocked_actions)
    result = planner.replan(frozenset({"something_else"}), frozenset({"goal"}))
    assert result is None


# ---------------------------------------------------------------------------
# build_workflow_tasks()
# ---------------------------------------------------------------------------


def test_build_workflow_tasks_returns_task_dicts():
    """build_workflow_tasks() returns dicts with required WorkflowTask keys."""
    planner = _simple_planner()
    tasks = planner.build_workflow_tasks(frozenset({"x"}), initial_state=frozenset(), plan_id="p1")
    assert tasks is not None
    assert len(tasks) == 1
    t = tasks[0]
    assert t["task_id"] == "p1-step-0"
    assert t["action"] == "a"
    assert "preconditions" in t
    assert "effects" in t
    assert "x" in t["effects"]  # sorted list, membership check works


def test_build_workflow_tasks_sequential_dependencies():
    """Each task in the chain depends on the previous task."""
    planner = _simple_planner()
    tasks = planner.build_workflow_tasks(frozenset({"z"}), initial_state=frozenset(), plan_id="p2")
    assert tasks is not None
    assert len(tasks) == 2
    # first task has no deps; second depends on first
    assert tasks[0]["dependencies"] == []
    assert tasks[1]["dependencies"] == [tasks[0]["task_id"]]


def test_build_workflow_tasks_unreachable_returns_none():
    """build_workflow_tasks() returns None when goal is unreachable."""
    planner = _simple_planner()
    result = planner.build_workflow_tasks(frozenset({"nowhere"}))
    assert result is None


# ---------------------------------------------------------------------------
# Default action library integration
# ---------------------------------------------------------------------------


def test_default_actions_pr_opened():
    """Default library can find a path to open a PR."""
    planner = GOAPPlanner()
    path = planner.plan(frozenset(), frozenset({"pr_opened"}))
    assert path is not None
    assert path[-1].name in {"open_pr", "open_pr_without_tests"}


def test_default_actions_docs_written():
    """Default library finds a path to docs_written."""
    planner = GOAPPlanner()
    path = planner.plan(frozenset(), frozenset({"docs_written"}))
    assert path is not None
    assert any(a.name.startswith("write_doc") for a in path)
