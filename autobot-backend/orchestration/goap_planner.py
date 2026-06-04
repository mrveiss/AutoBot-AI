# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""GOAP-style state-space planner for WorkflowPlan (GH#7354).

Implements A* search over a discrete fact-space:

    State  = frozenset[str]   — current world facts
    Goal   = frozenset[str]   — required facts that must be true at end
    Action = GOAPAction       — preconditions → effects, cost, capability

The heuristic h(state) = |goal - state| (count of unsatisfied goal facts) is
admissible: each action adds ≥1 fact to the state and costs ≥0, so h never
overestimates the true remaining cost.

Usage
-----
    planner = GOAPPlanner()

    # initial plan
    steps = planner.plan(initial_state=frozenset(), goal=frozenset({"pr_opened"}))

    # adaptive replanning after step failure
    steps = planner.replan(current_state={"code_written"}, goal={"pr_opened"})

    # build WorkflowTask-compatible dicts directly
    task_dicts = planner.build_workflow_tasks(goal_facts={"pr_opened"}, plan_id="p1")
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Union

from orchestration.types import AgentCapability

_StateArg = Union[FrozenSet[str], Set[str]]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GOAPAction:
    """A plannable action in the GOAP action space.

    ``preconditions`` — facts that must be true in the current state for this
    action to be applicable.
    ``effects``       — facts that become true after this action executes.
    ``cost``          — non-negative action cost used by A* to find cheapest path.
    ``agent_capability`` — the AgentCapability that can execute this action.
    """

    name: str
    preconditions: FrozenSet[str]
    effects: FrozenSet[str]
    cost: float
    agent_capability: AgentCapability


# ---------------------------------------------------------------------------
# Default action library (~20 actions covering AutoBot's common verbs)
# ---------------------------------------------------------------------------


def _action(
    name: str,
    pre: Iterable[str],
    eff: Iterable[str],
    cost: float,
    cap: AgentCapability,
) -> GOAPAction:
    return GOAPAction(
        name=name,
        preconditions=frozenset(pre),
        effects=frozenset(eff),
        cost=cost,
        agent_capability=cap,
    )


DEFAULT_ACTIONS: tuple[GOAPAction, ...] = (
    # ── research / retrieval ────────────────────────────────────────────────
    _action("research", [], ["research_done"], 1.0, AgentCapability.RESEARCH),
    _action("search_knowledge_base", [], ["knowledge_retrieved"], 0.5, AgentCapability.RESEARCH),
    # ── analysis / synthesis ────────────────────────────────────────────────
    _action("analyze_data", ["research_done"], ["analysis_done"], 1.5, AgentCapability.ANALYSIS),
    _action("analyze_from_knowledge", ["knowledge_retrieved"], ["analysis_done"], 1.0, AgentCapability.ANALYSIS),
    _action("summarize_findings", ["research_done"], ["summary_written"], 1.0, AgentCapability.SYNTHESIS),
    _action("summarize_from_knowledge", ["knowledge_retrieved"], ["summary_written"], 0.8, AgentCapability.SYNTHESIS),
    # ── code generation ─────────────────────────────────────────────────────
    _action("generate_code", ["analysis_done"], ["code_written"], 2.0, AgentCapability.CODE_GENERATION),
    _action("generate_code_from_summary", ["summary_written"], ["code_written"], 2.5, AgentCapability.CODE_GENERATION),
    # ── validation / testing ────────────────────────────────────────────────
    _action("run_tests", ["code_written"], ["tests_passed"], 1.0, AgentCapability.VALIDATION),
    _action("validate_output", ["code_written"], ["output_validated"], 1.0, AgentCapability.VALIDATION),
    _action("security_scan", ["code_written"], ["security_checked"], 1.0, AgentCapability.SECURITY),
    # ── PR / system ops ─────────────────────────────────────────────────────
    _action("open_pr", ["tests_passed"], ["pr_opened"], 0.5, AgentCapability.SYSTEM_OPERATIONS),
    _action("open_pr_without_tests", ["code_written"], ["pr_opened"], 2.0, AgentCapability.SYSTEM_OPERATIONS),
    _action("execute_system_command", [], ["command_executed"], 1.0, AgentCapability.SYSTEM_OPERATIONS),
    _action("monitor_execution", ["command_executed"], ["execution_monitored"], 0.5, AgentCapability.MONITORING),
    # ── documentation / knowledge ───────────────────────────────────────────
    _action("write_documentation", ["analysis_done"], ["docs_written"], 1.5, AgentCapability.DOCUMENTATION),
    _action("write_docs_from_summary", ["summary_written"], ["docs_written"], 1.5, AgentCapability.DOCUMENTATION),
    _action(
        "store_in_knowledge_base", ["docs_written"], ["knowledge_stored"], 0.5, AgentCapability.KNOWLEDGE_MANAGEMENT
    ),
    # ── orchestration ───────────────────────────────────────────────────────
    _action("coordinate_agents", [], ["agents_coordinated"], 1.0, AgentCapability.WORKFLOW_COORDINATION),
    _action("process_data", ["research_done"], ["data_processed"], 1.0, AgentCapability.DATA_PROCESSING),
    _action("optimize_workflow", ["analysis_done"], ["workflow_optimized"], 2.0, AgentCapability.OPTIMIZATION),
)


# ---------------------------------------------------------------------------
# A* planner
# ---------------------------------------------------------------------------


class GOAPPlanner:
    """GOAP A* planner over a discrete fact-space.

    Each node in the search tree is a frozenset of facts that are currently
    true.  Edges are GOAPActions whose preconditions are a subset of the
    current state.  The goal is reached when all goal facts are a subset of
    the current state.

    Admissible heuristic: h(state) = |goal - state| (unsatisfied goal fact
    count).  This never overestimates because satisfying one fact costs ≥ 0
    and requires at least one action application.

    Cycle detection: a visited dict maps (state → best g seen) so that a
    state re-explored at higher cost is pruned.
    """

    def __init__(self, actions: Sequence[GOAPAction] = DEFAULT_ACTIONS) -> None:
        self._actions = list(actions)

    # ---------------------------------------------------------------- public

    def plan(
        self,
        initial_state: _StateArg,
        goal: _StateArg,
    ) -> Optional[List[GOAPAction]]:
        """Return the cheapest action sequence from *initial_state* to *goal*.

        Returns ``[]`` when goal ⊆ initial_state (already satisfied).
        Returns ``None`` when the goal is unreachable with the current action
        library (no path exists).
        """
        start = frozenset(initial_state)
        goal_fs = frozenset(goal)

        if goal_fs.issubset(start):
            return []

        # heap entries: (f_score, g_score, tie_counter, state, path)
        counter = 0
        h0 = len(goal_fs - start)
        heap: list[tuple[float, float, int, frozenset, list[GOAPAction]]] = [(float(h0), 0.0, counter, start, [])]
        # state → best g already expanded at this state (closed list)
        visited: Dict[frozenset, float] = {}

        while heap:
            f, g, _, state, path = heapq.heappop(heap)

            if goal_fs.issubset(state):
                return path

            if state in visited and visited[state] <= g:
                continue
            visited[state] = g

            for action in self._actions:
                if not action.preconditions.issubset(state):
                    continue
                new_state = state | action.effects
                new_g = g + action.cost
                if new_state in visited and visited[new_state] <= new_g:
                    continue
                h = len(goal_fs - new_state)
                counter += 1
                heapq.heappush(
                    heap,
                    (new_g + h, new_g, counter, new_state, path + [action]),
                )

        return None  # unreachable

    def replan(
        self,
        current_state: _StateArg,
        goal: _StateArg,
    ) -> Optional[List[GOAPAction]]:
        """Replan from *current_state* after a mid-execution failure.

        Semantically identical to ``plan()`` but named separately so callers
        can clearly distinguish adaptive replanning from initial planning.
        Returns ``None`` when no alternative path exists (caller should abort).
        """
        return self.plan(current_state, goal)

    def build_workflow_tasks(
        self,
        goal_facts: _StateArg,
        initial_state: Optional[_StateArg] = None,
        plan_id: Optional[str] = None,
    ) -> Optional[List[Dict]]:
        """Build WorkflowTask-compatible dicts from a GOAP plan.

        Returns ``None`` when the goal is unreachable.  Each dict includes
        ``preconditions`` and ``effects`` (both ``set[str]``) in addition to
        standard WorkflowTask fields so callers can reconstruct the GOAP
        chain and use it for replanning.

        Sequential dependency chain: each step depends on the previous one.
        """
        actions = self.plan(initial_state or frozenset(), goal_facts)
        if actions is None:
            return None

        tasks: List[Dict] = []
        prev_task_id: Optional[str] = None

        for i, action in enumerate(actions):
            task_id = f"{plan_id or 'goap'}-step-{i}"
            tasks.append(
                {
                    "task_id": task_id,
                    "description": action.name.replace("_", " ").capitalize(),
                    "action": action.name,
                    "capabilities_required": [action.agent_capability.value],
                    "dependencies": [prev_task_id] if prev_task_id else [],
                    "preconditions": sorted(action.preconditions),
                    "effects": sorted(action.effects),
                    "metadata": {
                        "goap_action": action.name,
                        "goap_plan_id": plan_id or "",
                    },
                }
            )
            prev_task_id = task_id

        return tasks
