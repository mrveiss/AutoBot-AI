# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Multi-agent workflow execution engine extracted from Orchestrator (#5058).

Structural refactor (#6393/#6392): collaboration and agent-routing responsibilities
moved to CollaborationCoordinator and AgentRouter collaborators respectively.

Executor scope (#6826): WorkflowRunner is the **enhanced/multi-agent strategy engine**.
It executes WorkflowPlan objects via pluggable ExecutionStrategy instances and delegates
agent routing and collaboration to injected collaborators.  It does not handle DAG graphs
or step-level checkpoints — those remain in orchestration.WorkflowExecutor and
CheckpointResumer.  WorkflowRunner is the post-#5058 successor for the multi-agent path;
orchestration.WorkflowExecutor remains canonical for the legacy step-based path.
"""

import asyncio
import time
from typing import Any, Dict, List, Set, Tuple

from autobot_shared.logging_manager import get_logger
from enhanced_orchestration.agent_router import AgentRouter
from enhanced_orchestration.collaboration_coordinator import CollaborationCoordinator
from enhanced_orchestration.execution_strategies import ExecutionStrategyHandler
from enhanced_orchestration.success_criteria import SuccessCriteriaEvaluator
from enhanced_orchestration.types import AgentTask, WorkflowDependencies, WorkflowPlan
from enhanced_orchestration.workflow_planning import StrategyPlanner
from events.bus import PersistStrategy, publish_event
from orchestration.performance_tracker import PerformanceTracker

logger = get_logger("workflow_runner")


class WorkflowRunner:
    """Executes WorkflowPlan objects via the multi-agent strategy engine.

    Delegates to injected collaborators:
    - AgentRouter    — agent selection, resolution, capability coverage (#6392/#6393)
    - CollaborationCoordinator — Redis pub/sub between agents (#6393)
    - PerformanceTracker — per-agent success/failure metrics (#5058)
    """

    def __init__(
        self,
        strategy_planner: StrategyPlanner,
        performance_tracker: PerformanceTracker,
        active_workflows: Dict[str, WorkflowPlan],
        collaboration: CollaborationCoordinator,
        agent_router: AgentRouter,
        max_parallel_tasks: int = 5,
        criteria_evaluator: SuccessCriteriaEvaluator | None = None,
    ) -> None:
        self._strategy_planner = strategy_planner
        self._perf = performance_tracker
        self.active_workflows = active_workflows
        self._collab = collaboration
        self._agent_router = agent_router
        self.max_parallel_tasks = max_parallel_tasks
        self.resource_semaphore: asyncio.Semaphore = asyncio.Semaphore(max_parallel_tasks)
        self._criteria_evaluator = criteria_evaluator or SuccessCriteriaEvaluator()
        self._strategy_handler: ExecutionStrategyHandler | None = None
        # #7431 ADR-006 §Q1: subscriber that wakes blocked plans when
        # skill_promoted events arrive on Redis pub-sub. Lazy-constructed
        # via get_blocked_plan_resumer(); not started automatically — the
        # orchestrator (or whichever caller owns the lifecycle) must call
        # start() / stop() to enable auto-resume. Tests that don't need
        # auto-resume never construct the resumer (zero overhead).
        self._resumer: Any | None = None

    # ------------------------------------------------------------------ helpers

    def _get_strategy_handler(self) -> ExecutionStrategyHandler:
        if self._strategy_handler is None:
            self._strategy_handler = ExecutionStrategyHandler(
                max_parallel_tasks=self.max_parallel_tasks,
                resource_semaphore=self.resource_semaphore,
                deps=WorkflowDependencies(
                    execute_single_task=self._execute_single_agent_task,
                    topological_sort_tasks=self._strategy_planner.topological_sort_tasks,
                    dependencies_met=self._strategy_planner.dependencies_met,
                    group_pipeline_stages=self._strategy_planner.group_pipeline_stages,
                    enhance_task_for_collaboration=self._strategy_planner.enhance_task_for_collaboration,
                    coordinate_collaboration=self._collab.coordinate_collaboration,
                ),
            )
        return self._strategy_handler

    # ----------------------------------------------------------------- public

    async def execute_workflow(self, plan: WorkflowPlan, _depth: int = 0) -> Dict[str, Any]:
        """Execute a WorkflowPlan through the strategy handler."""
        # #7431 Phase 3: refuse to execute a plan blocked on async skill
        # generation. The resume path (BlockedPlanResumer subscriber, lands
        # in a forthcoming commit) re-invokes execute_workflow once the
        # awaited skill is promoted via the skill_promoted Redis pub-sub
        # event. Returning a structured response (rather than raising) lets
        # the caller decide whether to retry, surface to user, or wait.
        if plan.status == "blocked":
            pending_ids = [t.pending_skill_id for t in plan.tasks if t.pending_skill_id]
            logger.info(
                "workflow %s is blocked on %d pending skill(s); refusing to execute",
                plan.plan_id,
                len(pending_ids),
            )
            return {
                "plan_id": plan.plan_id,
                "success": False,
                "status": "blocked",
                "reason": "blocked_on_skill_generation",
                "pending_skill_ids": pending_ids,
                "results": {},
            }

        logger.info("Executing workflow %s strategy=%s", plan.plan_id, plan.strategy.value)
        start_time = time.time()
        results: Dict[str, Any] = {}
        try:
            await self._publish_workflow_event(
                plan.plan_id,
                "workflow_started",
                {"goal": plan.goal, "strategy": plan.strategy.value, "task_count": len(plan.tasks)},
            )
            results = await self._get_strategy_handler().execute_by_strategy(plan)
            return await self._handle_workflow_execution_success(plan, results, start_time)
        except Exception as e:
            return await self._handle_workflow_execution_failure(plan, e, results, _depth)

    async def get_agent_recommendations(self, capabilities_needed: Set) -> List[str]:
        return await self._agent_router.get_agent_recommendations(capabilities_needed)

    async def get_agent_recommendations_scored(self, capabilities_needed: Set) -> List[Tuple[str, float]]:
        return await self._agent_router.get_agent_recommendations_scored(capabilities_needed)

    def get_blocked_plan_resumer(self) -> Any:
        """Return the BlockedPlanResumer for this runner (lazy-constructed).

        Caller is responsible for the resumer's lifecycle: call
        ``await resumer.start()`` to begin auto-resume, ``await
        resumer.stop()`` for graceful shutdown. The resumer subscribes to
        the ``skill_promoted`` Redis pub-sub channel and calls
        ``try_resume_blocked_plan`` for each BLOCKED plan whenever a new
        skill is promoted. #7431, ADR-006 §Q1.
        """
        if self._resumer is None:
            from enhanced_orchestration.blocked_plan_resumer import BlockedPlanResumer

            self._resumer = BlockedPlanResumer(self)
        return self._resumer

    async def try_resume_blocked_plan(self, plan_id: str) -> Dict[str, Any]:
        """Re-attempt skill binding on a BLOCKED plan and execute if it unblocks.

        ADR-006 §Q1 manual resume API. Triggered by:
        - The auto-subscriber (forthcoming) when a ``skill_promoted`` event
          fires on Redis pub-sub (registry.register publishes it).
        - Periodic retry workers, dashboards, or operator commands.

        Behavior:
        - Plan unknown to active_workflows → ``{"resumed": False, "reason": "plan_not_found"}``.
        - Plan not BLOCKED → ``{"resumed": False, "reason": "plan_not_blocked"}`` (no-op).
        - Plan BLOCKED: clear all pending_skill_id values + matching
          PendingSkillsRegistry entries, set plan.status="pending",
          re-invoke ``StrategyPlanner.build_workflow_plan`` against the
          original plan_data — but since plan_data isn't retained, we
          instead re-run the per-task ``_bind_skill_to_task`` against the
          current router state. If any task is still unresolved, the plan
          re-blocks. Otherwise execute_workflow runs.
        """
        plan = self.active_workflows.get(plan_id)
        if plan is None:
            return {"resumed": False, "reason": "plan_not_found"}
        if plan.status != "blocked":
            return {"resumed": False, "reason": "plan_not_blocked"}

        # Clear pending state on every task that was waiting; bind_skill
        # will be re-attempted below against the current registry.
        try:
            from skills.pending_skills import get_pending_skills_registry

            pending_registry = get_pending_skills_registry()
        except ImportError:
            pending_registry = None
        for task in plan.tasks:
            if task.pending_skill_id:
                if pending_registry is not None:
                    pending_registry.clear(task.pending_skill_id)
                task.pending_skill_id = None
        plan.status = "pending"

        # Re-attempt skill binding against the current registry. If the
        # promoted skill addresses the previously-unresolved intent, the
        # task gets bound; otherwise it goes back to BLOCKED via the
        # planner's gap-fill path (no infinite loop — gap-fill only fires
        # when a fresh skill_router lookup still finds no winner).
        await self._rebind_blocked_tasks(plan)

        if plan.status == "blocked":
            return {
                "resumed": False,
                "reason": "still_missing_skills",
                "pending_skill_ids": [t.pending_skill_id for t in plan.tasks if t.pending_skill_id],
            }

        result = await self.execute_workflow(plan)
        return {"resumed": True, "result": result}

    async def _rebind_blocked_tasks(self, plan: WorkflowPlan) -> None:
        """Re-run ``_bind_skill_to_task`` for every task in a freshly-unblocked
        plan. Used by ``try_resume_blocked_plan`` to reconcile the plan with
        the current SkillRegistry contents (which may have grown since the
        plan was originally constructed)."""
        any_pending = False
        for task in plan.tasks:
            # Reset only the binding fields; leave inputs/dependencies/etc alone.
            task.skill_name = None
            task.skill_action = None
            task.skill_resolution_method = None
            await self._strategy_planner._bind_skill_to_task(
                task,
                {"task": task.action or task.task_id, "skill_action": task.skill_action},
                plan.goal,
            )
            if task.pending_skill_id:
                any_pending = True
        if any_pending:
            plan.status = "blocked"

    def get_performance_report(self) -> Dict[str, Any]:
        return {
            "agent_performance": self._perf.report(),
            "active_workflows": len(self.active_workflows),
            "capabilities_coverage": self._agent_router.calculate_capability_coverage(),
        }

    # ------------------------------------------------------ execution internals

    async def _evaluate_workflow_criteria(self, plan: WorkflowPlan, results: Dict[str, Any]) -> Dict[str, Any]:
        if plan.structured_criteria:
            eval_result = await self._criteria_evaluator.evaluate(plan.structured_criteria, results)
            return eval_result.to_dict()
        binary_pass = self._strategy_planner.check_success_criteria(plan, results)
        return {
            "overall": "full" if binary_pass else "failed",
            "score": 1.0 if binary_pass else 0.0,
            "results": [],
        }

    async def _handle_workflow_execution_success(
        self,
        plan: WorkflowPlan,
        results: Dict[str, Any],
        start_time: float,
    ) -> Dict[str, Any]:
        criteria_eval = await self._evaluate_workflow_criteria(plan, results)
        success = criteria_eval["overall"] in ("full", "partial")
        execution_time = time.time() - start_time
        self._perf.update_from_plan(plan, results)
        await self._publish_workflow_event(
            plan.plan_id,
            "workflow_completed",
            {
                "success": success,
                "execution_time": execution_time,
                "results_summary": self._strategy_planner.summarize_results(results),
                "criteria_evaluation": criteria_eval,
            },
        )
        response = {
            "plan_id": plan.plan_id,
            "success": success,
            "results": results,
            "execution_time": execution_time,
            "strategy_used": plan.strategy.value,
            "criteria_evaluation": criteria_eval,
        }
        # GH#7357: capture trajectory for future planner retrieval
        await self._capture_trajectory(plan, response)
        return response

    async def _capture_trajectory(self, plan: WorkflowPlan, result: Dict[str, Any]) -> None:
        """Write a trajectory record to the TrajectoryStore (GH#7357).

        Fire-and-forget: errors are logged but never propagate to the caller so
        trajectory capture cannot break workflow execution.
        """
        try:
            from memory.trajectory_store import get_trajectory_store, reward_from_execution

            store = await get_trajectory_store()
            action_sequence = [
                {
                    "task_id": t.task_id,
                    "agent_type": getattr(t, "agent_type", ""),
                    "description": getattr(t, "description", ""),
                    "status": getattr(t, "status", ""),
                }
                for t in plan.tasks
            ]
            outcome = "success" if result.get("success") else "failure"
            criteria = result.get("criteria_evaluation", {})
            if isinstance(criteria, dict) and criteria.get("overall") == "partial":
                outcome = "partial"
            reward = reward_from_execution(result)
            await store.capture(
                task_text=plan.goal,
                action_sequence=action_sequence,
                outcome=outcome,
                reward=reward,
                duration=float(result.get("execution_time", 0.0)),
                agent_id=getattr(plan, "assigned_agent", ""),
                plan_id=plan.plan_id,
                strategy=plan.strategy.value,
            )
        except Exception as exc:
            logger.warning("TrajectoryStore.capture failed (non-fatal): %s", exc)

    async def _record_failure_pattern(self, plan: WorkflowPlan, error: Exception) -> Dict[str, Any] | None:
        """Learn this workflow failure and flag it when it is a known recurring pattern (#10628).

        Wires the previously-unused FailurePatternDetector into the failure path:
        records the failure (write) and surfaces prior-occurrence metadata (read).
        Awaited inline but fully guarded — any detector/Redis error is swallowed
        so failure handling is never disrupted.  (The detector currently uses a
        sync Redis client; making it async-native is tracked separately.)
        Returns annotation metadata when the pattern has been seen before,
        else None.
        """
        try:
            from services.failure_pattern_detector import get_pattern_detector

            error_type = type(error).__name__
            causal_chain = f"workflow:{plan.strategy.value}:{error_type}"
            detector = get_pattern_detector()
            known = await detector.detect_pattern(causal_chain, error_type)
            await detector.learn_pattern(causal_chain, error_type)
            if known and known.occurrence_count > 0:
                return {
                    "pattern_id": known.pattern_id,
                    "occurrences": known.occurrence_count,
                    "resolution_success_rate": known.resolution_success_rate,
                }
        except Exception as exc:  # never break failure handling
            logger.debug("Failure-pattern recording skipped: %s", exc)
        return None

    async def _handle_workflow_execution_failure(
        self, plan: WorkflowPlan, error: Exception, results: Dict[str, Any], _depth: int = 0
    ) -> Dict[str, Any]:
        logger.error("Workflow execution failed: %s", error)
        # #10628: record the originating failure once, at the top level only, so
        # the learned occurrence count isn't inflated by each fallback retry
        # (this method recurses via execute_workflow on fallbacks).
        pattern_info = await self._record_failure_pattern(plan, error) if _depth == 0 else None
        result = await self._attempt_failure_recovery(plan, error, results, _depth)
        if pattern_info and not result.get("success", False):
            result["known_failure_pattern"] = pattern_info
        return result

    async def _attempt_failure_recovery(
        self, plan: WorkflowPlan, error: Exception, results: Dict[str, Any], _depth: int
    ) -> Dict[str, Any]:
        """GOAP-replan / fallback-chain recovery for a failed workflow (#10628 extracted)."""
        if _depth >= 5:
            logger.error("Max fallback depth (5) reached, aborting fallback chain")
            return {"plan_id": plan.plan_id, "success": False, "error": str(error), "results": results}

        # GH#7354: GOAP adaptive replanning.  When the plan was produced by
        # GOAPPlanner, derive the current world-state from completed tasks and
        # ask the planner for an alternative path to the original goal.
        # Capability-mapping plans keep the existing fallback-chain behaviour.
        if plan.is_goap_plan and plan.goap_goal:
            replan_result = await self._try_goap_replan(plan, results, _depth)
            if replan_result is not None:
                return replan_result

        for fallback in plan.fallback_plans or []:
            try:
                return await self.execute_workflow(fallback, _depth + 1)
            except Exception as fe:
                logger.error("Fallback plan failed: %s", fe)
        return {"plan_id": plan.plan_id, "success": False, "error": str(error), "results": results}

    async def _try_goap_replan(self, plan: WorkflowPlan, results: Dict[str, Any], _depth: int) -> Dict[str, Any] | None:
        """Attempt GOAP adaptive replanning after a step failure (GH#7354).

        Derives the current world-state from effects of completed tasks, then
        calls GOAPPlanner.replan().  Returns a new execution result dict when
        a valid replan is found and successfully executed; returns None when
        replanning is impossible or produces an equivalent plan (avoid loop).
        """
        try:
            from orchestration.goap_planner import GOAPPlanner
        except ImportError as exc:
            logger.error("GOAP replanning unavailable: %s", exc)
            return None

        # Accumulate world state from completed task effects.
        current_state: set[str] = set()
        for task in plan.tasks:
            if task.status == "completed" and task.effects:
                current_state.update(task.effects)

        goal_facts: set[str] = set(plan.goap_goal)
        if goal_facts.issubset(current_state):
            # Goal already satisfied — treat as success.
            logger.info("GOAP replan: goal already satisfied by completed tasks")
            return {"plan_id": plan.plan_id, "success": True, "results": results}

        planner = GOAPPlanner()
        new_actions = planner.replan(current_state, goal_facts)
        if not new_actions:
            logger.warning("GOAP replan: no alternative path found for goal %s", goal_facts)
            return None

        new_plan_id = f"{plan.plan_id}-replan-{_depth}"
        task_dicts = planner.build_workflow_tasks(
            goal_facts=goal_facts,
            initial_state=current_state,
            plan_id=new_plan_id,
        )
        if not task_dicts:
            return None

        new_tasks = [AgentTask.from_dict(d) for d in task_dicts]
        # Avoid re-executing the exact same plan (cycle guard).
        new_action_names = [t.action for t in new_tasks]
        original_action_names = [t.action for t in plan.tasks if t.status != "completed"]
        if new_action_names == original_action_names:
            logger.warning("GOAP replan: produced identical remaining steps, skipping")
            return None

        replan = WorkflowPlan(
            plan_id=new_plan_id,
            goal=plan.goal,
            tasks=new_tasks,
            strategy=plan.strategy,
            success_criteria=plan.success_criteria,
            is_goap_plan=True,
            goap_goal=list(goal_facts),
            metadata={**plan.metadata, "replanned_from": plan.plan_id},
        )
        logger.info(
            "GOAP replan: executing %d-step alternative plan %s",
            len(new_tasks),
            new_plan_id,
        )
        return await self.execute_workflow(replan, _depth + 1)

    async def _handle_task_timeout(self, task: AgentTask, context: Dict[str, Any]) -> Dict[str, Any]:
        task.fail_execution("Timeout")
        if task.can_retry():
            task.increment_retry()
            logger.warning(
                "Task %s timed out, retrying (%d/%d)",
                task.task_id,
                task.retry_count,
                task.max_retries,
            )
            return await self._execute_single_agent_task(task, context)
        self._perf.update(task.agent_type, False, time.time() - (task.start_time or time.time()))
        return task.to_failed_result("Task execution timed out")

    def _handle_task_exception(self, task: AgentTask, error: Exception) -> Dict[str, Any]:
        task.fail_execution(str(error))
        execution_time = time.time() - (task.start_time or time.time())
        self._perf.update(task.agent_type, False, execution_time)
        return task.to_failed_result(str(error))

    async def _execute_single_agent_task(self, task: AgentTask, context: Dict[str, Any]) -> Dict[str, Any]:
        task.start_execution()
        try:
            async with self.resource_semaphore:
                # #7430 Phase 2: if StrategyPlanner bound a skill at plan time
                # (#7268 Phase 1), dispatch via SkillRegistry instead of the
                # capability-based agent path. ADR-006 default: skill-bound
                # execution **replaces** agent dispatch — the skill is the
                # concrete implementation. Removed/disabled skill at execute
                # time fails the step (don't silently re-route at execute time;
                # plans should re-plan instead, per #7431 Q3).
                if task.skill_name:
                    return await self._dispatch_via_skill(task, context)
                agent = await self._agent_router.get_agent_instance(task.agent_type)
                if not agent:
                    raise Exception(f"Agent {task.agent_type} not available")
                enhanced_inputs = task.get_enhanced_inputs(context)
                result = await asyncio.wait_for(
                    agent.process_request({"action": task.action, "payload": enhanced_inputs}),
                    timeout=task.timeout_seconds,
                )
                task.complete_execution(result)
                self._perf.update(task.agent_type, True, task.get_execution_time())
                return task.to_completed_result(result)
        except asyncio.TimeoutError:
            return await self._handle_task_timeout(task, context)
        except Exception as e:
            return self._handle_task_exception(task, e)

    async def _dispatch_via_skill(self, task: AgentTask, context: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch task via the bound skill (#7430 Phase 2 of #7268 / ADR-006).

        Caller already holds ``self.resource_semaphore`` and called
        ``task.start_execution()``. We enforce the same timeout behavior as
        the legacy agent path so resource accounting + perf metrics stay
        consistent.

        Failure modes:
        - Skill not registered (or registered but disabled) → raise
          ``RuntimeError`` so the existing ``_handle_task_exception`` path
          surfaces it as a failed task. This is the explicit ADR-006 choice
          per #7431 Q3 — fail the step, don't re-route at execute time.
        - Skill ``execute`` raises → propagate up; same handler.
        - Skill ``execute`` times out → propagate ``asyncio.TimeoutError``;
          same handler.
        """
        # Lazy import — avoids circular dep if skills imports orchestration
        from skills.registry import get_skill_registry

        registry = get_skill_registry()
        skill = registry.get(task.skill_name)
        if skill is None:
            raise RuntimeError(
                f"Skill '{task.skill_name}' bound at plan time is not registered "
                f"(registry may have been mutated between plan and execute). "
                f"Failing step per ADR-006 'fail-don't-reroute' policy."
            )
        if not skill.enabled:
            raise RuntimeError(
                f"Skill '{task.skill_name}' is registered but disabled at execute time. "
                f"Failing step per ADR-006 'fail-don't-reroute' policy."
            )

        enhanced_inputs = task.get_enhanced_inputs(context)
        action = task.skill_action or "execute"
        result = await asyncio.wait_for(
            skill.execute(action, enhanced_inputs),
            timeout=task.timeout_seconds,
        )
        task.complete_execution(result)
        # Perf-tracker key uses skill_name — agent_type may still be set on
        # the task for legacy reasons but the actual dispatch was the skill.
        self._perf.update(f"skill:{task.skill_name}", True, task.get_execution_time())
        return task.to_completed_result(result)

    async def _publish_workflow_event(self, workflow_id: str, event_type: str, data: Dict[str, Any]) -> None:
        await publish_event(
            "global",
            "workflow_event",
            {"workflow_id": workflow_id, "event_type": event_type, "timestamp": time.time(), "data": data},
            persist=PersistStrategy.NONE,
        )
