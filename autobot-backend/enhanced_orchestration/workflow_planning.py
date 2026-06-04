# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Planning Module

Issue #381: Extracted from enhanced_multi_agent_orchestrator.py god class refactoring.
Contains workflow planning, building, and utility functions.

Note: The class in this module is named ``StrategyPlanner`` — not ``WorkflowPlanner`` —
to distinguish it from the canonical (but currently unwired) ``orchestration.WorkflowPlanner``
in ``autobot-backend/orchestration/workflow_planner.py``.  Both classes were historically
called ``WorkflowPlanner`` and every import site aliased this one ``as StrategyPlanner``;
the rename removes that aliasing smell (#6817).  The orphan status of the canonical class
is tracked separately in #6820.
"""

import re
import uuid
from typing import Any, Dict, List, Set

from autobot_shared.logging_manager import get_logger

from .types import AgentCapability, AgentTask, ExecutionStrategy, WorkflowPlan

logger = get_logger(__name__)


class StrategyPlanner:
    """Handles workflow plan creation and task management."""

    def __init__(
        self,
        agent_capabilities: Dict[str, Set[AgentCapability]],
        *,
        strict_gap_fill: bool = False,
    ):
        """Initialize workflow planner.

        Args:
            agent_capabilities: Mapping of agent types to their capabilities.
            strict_gap_fill: ADR-006 strict mode (#7431). When ``True``, a
                no-skill-match at plan time fires the async Phase 3 gap-fill
                loop (skill-researcher → autonomous-skill-development →
                governance → register) and flips the plan to
                ``BLOCKED_ON_SKILL_GENERATION`` until a skill is promoted.
                When ``False`` (default, lenient), a no-match leaves
                ``task.skill_name=None`` and legacy capability-based routing
                handles the task unchanged.
        """
        self.agent_capabilities = agent_capabilities
        self.strict_gap_fill = strict_gap_fill
        # #7268 Phase 1: lazily-instantiated skill_router for plan-time binding.
        # Created on first ``build_workflow_plan`` call and cached for the
        # planner's lifetime. Each lookup is ``dry_run=True`` so no skill is
        # auto-enabled and no Phase 3 gap-fill runs at plan time.
        self._skill_router_skill: Any | None = None

    async def build_workflow_plan(self, goal: str, plan_data: Dict[str, Any]) -> WorkflowPlan:
        """Build workflow plan from parsed data.

        #7268 Phase 1, ADR-006: Skill-Bound Planning. After each task is
        constructed from the LLM-parsed plan_data, attempt to resolve a
        concrete skill via skill_router (dry_run mode — no auto-enable, no
        Phase 3 gap-fill). When a skill matches, attach ``skill_name`` and
        ``skill_action`` to the task so Phase 2 (WorkflowExecutor
        consumption) can dispatch via ``SkillRegistry`` instead of (or in
        addition to) capability-based agent routing.
        """
        plan_id = str(uuid.uuid4())

        # Create tasks
        tasks = []
        dependencies_graph = {}

        for i, task_data in enumerate(plan_data.get("tasks", [])):
            task_id = f"{plan_id}_task_{i}"

            # Determine required capabilities
            caps_required = set()
            for cap_name in task_data.get("capabilities_required", []):
                try:
                    caps_required.add(AgentCapability(cap_name))
                except ValueError:
                    logger.debug("Unknown capability %s, skipping", cap_name)

            task = AgentTask(
                task_id=task_id,
                agent_type=task_data.get("agent", "orchestrator"),
                action=task_data.get("action", "process"),
                inputs=task_data.get("inputs", {}),
                dependencies=task_data.get("dependencies", []),
                priority=task_data.get("priority", 5),
                capabilities_required=caps_required,
            )

            # #7268 Phase 1: bind a skill at plan time when one matches.
            # Best-effort; failures (no registry, network error, malformed
            # response) leave skill_name=None so legacy capability-based
            # routing continues to work unchanged.
            await self._bind_skill_to_task(task, task_data, goal)

            tasks.append(task)
            dependencies_graph[task_id] = task.dependencies

        # Determine strategy
        strategy_name = plan_data.get("strategy", "sequential")
        try:
            strategy = ExecutionStrategy(strategy_name)
        except ValueError:
            strategy = ExecutionStrategy.SEQUENTIAL

        # #7431 Phase 3: if any task is awaiting an async-generated skill,
        # flip the plan to BLOCKED so the executor refuses to run it. The
        # resume path (BlockedPlanResumer subscriber) re-binds and unblocks
        # once the awaited skill is promoted via skill_promoted Redis pub-sub.
        plan_status = "blocked" if any(t.pending_skill_id for t in tasks) else "pending"
        if plan_status == "blocked":
            blocked_count = sum(1 for t in tasks if t.pending_skill_id)
            logger.info(
                "plan %s constructed in BLOCKED state: %d task(s) awaiting Phase 3 skill generation",
                plan_id,
                blocked_count,
            )

        return WorkflowPlan(
            plan_id=plan_id,
            goal=goal,
            strategy=strategy,
            tasks=tasks,
            dependencies_graph=dependencies_graph,
            estimated_total_duration_seconds=plan_data.get("estimated_duration", 60.0),
            resource_requirements=plan_data.get("resource_requirements", {}),
            success_criteria=plan_data.get("success_criteria", ["All tasks completed"]),
            status=plan_status,
        )

    def _get_skill_router(self) -> Any | None:
        """Lazily instantiate ``SkillRouterSkill`` for plan-time lookups (#7268).

        Returns ``None`` if instantiation fails (skills package import error,
        registry unavailable, etc.) — caller treats that as "no skill match"
        and leaves ``skill_name=None`` on the task. Cached after first success.
        """
        if self._skill_router_skill is not None:
            return self._skill_router_skill
        try:
            from skills.builtin.skill_router import SkillRouterSkill

            self._skill_router_skill = SkillRouterSkill()
            return self._skill_router_skill
        except Exception as exc:  # noqa: BLE001 — best-effort init
            logger.debug("skill_router unavailable for plan-time binding: %s", exc)
            return None

    async def _bind_skill_to_task(self, task: "AgentTask", task_data: Dict[str, Any], goal: str) -> None:
        """Resolve a concrete skill for this task via skill_router (#7268 Phase 1).

        Uses ``dry_run=True`` so the registry is not mutated at plan time
        (no auto-enable) and the Phase 3 gap-fill loop does not fire (no
        synchronous LLM-driven skill creation during planning). The task
        description used for routing is, in priority order:

        1. ``task_data["task"]`` — explicit task description from plan_data
        2. ``task_data["explanation"]`` — LLM-provided rationale
        3. ``f"{task.action} (in workflow: {goal})"`` — synthesized fallback

        Failures and "no match" cases leave ``skill_name=None``.
        """
        router = self._get_skill_router()
        if router is None:
            return

        task_desc = task_data.get("task") or task_data.get("explanation") or f"{task.action} (in workflow: {goal})"
        try:
            result = await router.execute(
                "find_skill",
                {"task": task_desc, "dry_run": True},
            )
        except Exception as exc:  # noqa: BLE001 — best-effort resolution
            logger.debug("skill_router lookup raised for task %s: %s", task.task_id, exc)
            return

        if not isinstance(result, dict) or not result.get("success"):
            return

        skill_name = result.get("enabled_skill")
        if not skill_name:
            # #7431 Phase 3: no skill matched.
            # strict_gap_fill=True (ADR-006 strict mode): fire async gap-fill
            # in the background, attach a pending_skill_id, and let the plan
            # flip to BLOCKED_ON_SKILL_GENERATION. The resume path re-binds
            # the task once a skill is promoted via skill_promoted Redis pub-sub.
            # strict_gap_fill=False (default, lenient): leave skill_name=None
            # and fall back to legacy capability-based routing — no gap-fill.
            if self.strict_gap_fill:
                await self._trigger_async_gap_fill(task, task_desc)
            return

        # Action defaults to ``"execute"`` — Phase 2 (WorkflowExecutor
        # consumption) can refine this once the dispatch contract is decided.
        task.skill_name = skill_name
        task.skill_action = task_data.get("skill_action") or "execute"
        task.skill_resolution_method = result.get("method")
        logger.debug(
            "bound skill '%s' to task %s (method=%s)",
            skill_name,
            task.task_id,
            task.skill_resolution_method,
        )

    async def _trigger_async_gap_fill(self, task: "AgentTask", intent: str) -> None:
        """Fire Phase 3 gap-fill in background; attach pending_skill_id (#7431).

        Best-effort: when the pending_skills module isn't importable the
        task stays unbound (legacy capability dispatch continues). This
        keeps planner behavior compatible with stripped-down environments
        that don't ship the gap-fill pipeline.
        """
        try:
            from skills.pending_skills import trigger_gap_fill
        except ImportError:
            logger.debug("pending_skills module unavailable; gap-fill skipped")
            return

        router = self._get_skill_router()
        if router is None:
            logger.debug("skill_router unavailable; gap-fill skipped for task %s", task.task_id)
            return

        async def _router_call(task_intent: str) -> Dict[str, Any]:
            # No dry_run → Phase 3 (research → autonomous-skill-development
            # → governance → register) runs. Result returned here is just
            # informational; the resume path listens on skill_promoted via
            # Redis pub-sub for the eventual outcome.
            return await router.execute("find_skill", {"task": task_intent})

        # plan_id is not yet known here (binding happens before plan
        # construction completes) — record placeholder and reconcile in
        # build_workflow_plan via the post-loop pass that flips status.
        binding = await trigger_gap_fill(
            intent=intent,
            plan_id="<pending-plan>",
            task_id=task.task_id,
            router_call=_router_call,
        )
        task.pending_skill_id = binding.pending_skill_id
        logger.info(
            "task %s blocked on Phase 3 skill generation (pending_skill_id=%s)",
            task.task_id,
            binding.pending_skill_id,
        )

    def create_fallback_plan(self, goal: str) -> Dict[str, Any]:
        """Create a simple fallback plan"""
        return {
            "strategy": "sequential",
            "tasks": [
                {
                    "agent": "classification_agent",
                    "action": "classify_request",
                    "inputs": {"message": goal},
                    "dependencies": [],
                    "priority": 8,
                },
                {
                    "agent": "orchestrator",
                    "action": "process_goal",
                    "inputs": {"goal": goal},
                    "dependencies": [],
                    "priority": 5,
                },
            ],
            "success_criteria": ["Goal processed"],
            "estimated_duration": 30.0,
            "resource_requirements": {},
        }

    def create_simple_workflow_plan(self, goal: str) -> WorkflowPlan:
        """Create a simple sequential workflow plan"""
        plan_id = str(uuid.uuid4())

        return WorkflowPlan(
            plan_id=plan_id,
            goal=goal,
            strategy=ExecutionStrategy.SEQUENTIAL,
            tasks=[
                AgentTask(
                    task_id=f"{plan_id}_task_0",
                    agent_type="orchestrator",
                    action="process_goal",
                    inputs={"goal": goal},
                    priority=5,
                )
            ],
            dependencies_graph={},
            estimated_total_duration_seconds=30.0,
            resource_requirements={},
            success_criteria=["Task completed"],
        )

    def topological_sort_tasks(self, tasks: List[AgentTask], dependencies: Dict[str, List[str]]) -> List[AgentTask]:
        """Sort tasks based on dependencies"""
        # Create task lookup
        task_map = {task.task_id: task for task in tasks}

        # Kahn's algorithm for topological sort
        in_degree = {task.task_id: 0 for task in tasks}
        for deps in dependencies.values():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] += 1

        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        sorted_tasks = []

        while queue:
            # Sort by priority within same dependency level
            queue.sort(key=lambda tid: task_map[tid].priority, reverse=True)

            task_id = queue.pop(0)
            sorted_tasks.append(task_map[task_id])

            # Reduce in-degree for dependent tasks
            for other_id, deps in dependencies.items():
                if task_id in deps:
                    in_degree[other_id] -= 1
                    if in_degree[other_id] == 0:
                        queue.append(other_id)

        # Add any remaining tasks (cycles)
        for task in tasks:
            if task not in sorted_tasks:
                sorted_tasks.append(task)

        return sorted_tasks

    def dependencies_met(self, task: AgentTask, results: Dict[str, Any]) -> bool:
        """Check if task dependencies are met"""
        for dep_id in task.dependencies:
            if dep_id not in results or results[dep_id].get("status") != "completed":
                return False
        return True

    def group_pipeline_stages(
        self, tasks: List[AgentTask], dependencies: Dict[str, List[str]]
    ) -> List[List[AgentTask]]:
        """Group tasks into pipeline stages"""
        stages = []
        processed = set()

        while len(processed) < len(tasks):
            # Find tasks that can run in current stage
            stage_tasks = []
            for task in tasks:
                if task.task_id not in processed:
                    # Check if all dependencies are in previous stages
                    deps_satisfied = all(dep in processed for dep in task.dependencies)
                    if deps_satisfied:
                        stage_tasks.append(task)

            if not stage_tasks:
                # Circular dependency or error - add remaining tasks as final stage
                stage_tasks = [t for t in tasks if t.task_id not in processed]

            stages.append(stage_tasks)
            processed.update(t.task_id for t in stage_tasks)

        return stages

    def enhance_task_for_collaboration(self, task: AgentTask, collab_channel: str) -> AgentTask:
        """Enhance task with collaboration metadata"""
        task.metadata["collaboration_channel"] = collab_channel
        task.metadata["enable_sharing"] = True
        return task

    def check_success_criteria(self, plan: WorkflowPlan, results: Dict[str, Any]) -> bool:
        """Check if workflow met success criteria"""
        # Basic check: all non-optional tasks completed
        for task in plan.tasks:
            if not task.metadata.get("optional", False):
                result = results.get(task.task_id, {})
                if result.get("status") != "completed":
                    return False

        # Check custom success criteria from the plan
        if plan.success_criteria:
            for criterion in plan.success_criteria:
                if not self.evaluate_success_criterion(criterion, results):
                    logger.warning("Success criterion not met: %s", criterion)
                    return False

        return True

    def evaluate_success_criterion(self, criterion: str, results: Dict[str, Any]) -> bool:
        """
        Evaluate a single success criterion against workflow results.

        Supports these criterion patterns:
        - "All tasks completed" - All tasks must have status 'completed'
        - "No failures" - No task should have status 'failed'
        - "Success rate >= X%" - At least X% of tasks must complete
        - "Task:<task_id> completed" - Specific task must complete
        - Default: Returns True (unknown criteria are considered met)
        """
        criterion_lower = criterion.lower().strip()

        # Pattern: "All tasks completed"
        if "all tasks completed" in criterion_lower:
            return all(r.get("status") == "completed" for r in results.values())

        # Pattern: "No failures"
        if "no failure" in criterion_lower:
            return not any(r.get("status") == "failed" for r in results.values())

        # Pattern: "Success rate >= X%"
        if "success rate" in criterion_lower and ">=" in criterion_lower:
            match = re.search(r"(\d+(?:\.\d+)?)\s*%", criterion)
            if match:
                required_rate = float(match.group(1)) / 100
                if results:
                    completed = sum(1 for r in results.values() if r.get("status") == "completed")
                    actual_rate = completed / len(results)
                    return actual_rate >= required_rate
            return True

        # Pattern: "Task:<task_id> completed"
        if criterion_lower.startswith("task:") and "completed" in criterion_lower:
            # Extract task_id between "task:" and "completed"
            parts = criterion_lower.replace("task:", "").replace("completed", "").strip()
            task_id = parts.strip()
            if task_id in results:
                return results[task_id].get("status") == "completed"
            return False

        # Default: unknown criteria considered met (log for visibility)
        logger.debug("Unknown success criterion pattern: %s", criterion)
        return True

    def summarize_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize workflow results"""
        completed = sum(1 for r in results.values() if r.get("status") == "completed")
        failed = sum(1 for r in results.values() if r.get("status") == "failed")

        return {
            "total_tasks": len(results),
            "completed": completed,
            "failed": failed,
            "success_rate": completed / max(len(results), 1),
        }

    # ------------------------------------------------------------------
    # GH#7354 — GOAP plan builder
    # ------------------------------------------------------------------

    def build_goap_workflow_plan(
        self,
        goal: str,
        goal_facts: Set[str],
        initial_state: Set[str] | None = None,
        strategy: ExecutionStrategy = ExecutionStrategy.SEQUENTIAL,
        success_criteria: List[str] | None = None,
        plan_id: str | None = None,
    ) -> WorkflowPlan:
        """Build a WorkflowPlan using GOAP A* search (GH#7354).

        Unlike ``build_workflow_plan`` (which relies on LLM-generated
        ``plan_data``), this method uses ``GOAPPlanner`` to search the
        discrete fact-space for the cheapest action sequence that satisfies
        ``goal_facts`` from ``initial_state``.

        Raises ``ValueError`` when the goal is unreachable with the default
        action library.

        The returned plan carries ``is_goap_plan=True`` and ``goap_goal`` so
        that ``WorkflowRunner`` can invoke adaptive replanning on step failure.
        """
        from orchestration.goap_planner import GOAPPlanner

        planner = GOAPPlanner()
        effective_plan_id = plan_id or str(uuid.uuid4())
        task_dicts = planner.build_workflow_tasks(
            goal_facts=frozenset(goal_facts),
            initial_state=frozenset(initial_state or set()),
            plan_id=effective_plan_id,
        )
        if task_dicts is None:
            raise ValueError(
                f"GOAP planner: goal {goal_facts!r} is unreachable from "
                f"initial_state {initial_state!r} with the default action library."
            )

        tasks = [AgentTask.from_dict(d) for d in task_dicts]
        dependencies_graph: Dict[str, List[str]] = {t["task_id"]: t["dependencies"] for t in task_dicts}

        return WorkflowPlan(
            plan_id=effective_plan_id,
            goal=goal,
            tasks=tasks,
            strategy=strategy,
            dependencies_graph=dependencies_graph,
            success_criteria=success_criteria or ["All tasks completed"],
            is_goap_plan=True,
            goap_goal=sorted(goal_facts),
        )
