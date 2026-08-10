# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Planner

DEPRECATED — NOT A PRODUCTION PLANNING PATH (#13751). Every public method on
``WorkflowPlanner`` has **zero callers**. It is the planner half of the
orchestration engine that ``orchestrator.run_workflow`` stopped using at #5058;
#12373/#12579 deprecated the executor half
(``orchestration/workflow_executor.py``) in place and did not reach this
sibling. ``Orchestrator`` still constructs it as ``self._step_planner``
(orchestrator.py) but never calls a method on it.

Unlike the executor, this module holds **no capability the canonical path
lacks**, so there is nothing here staged for future consolidation. Each
capability maps to wired code today:

- Base plan + capability-to-agent assignment
  (``plan_workflow_steps_with_agents``) -> ``orchestrator.create_workflow_plan``
  builds the plan and ``AgentRouter.get_agent_recommendations_scored`` does the
  scored capability-to-agent selection, reached via
  ``WorkflowRunner``/``Orchestrator.get_agent_recommendations_scored``.
- Similar-trajectory priors (``_annotate_context_with_trajectories``, GH#7357)
  -> ``orchestrator._fetch_planning_context`` (#10580/#10581), tenant-scoped by
  #11015/#11089.
- Plan without executing (``get_plan_summary``) ->
  ``orchestrator.create_workflow_plan``, which builds and stores a
  ``WorkflowPlan`` without running it.
- Approval presentation (``create_plan_summary_for_approval``) ->
  ``services.workflow_automation.executor.WorkflowExecutor
  .present_plan_for_approval``, reached through
  ``WorkflowAutomationManager.present_plan_for_approval`` (#390) and the
  ``/api/workflow-automation/*`` surface.

Kept **in place with all code intact** — per repo policy code is never deleted,
only wired in or superseded. Do not wire these methods into a request path:
doing so would create a second planning path alongside
``create_workflow_plan`` for the two to drift against, which is the outcome
#13751 was filed to avoid. ``repo_tests/workflow_planner_deprecation_test.py``
holds this invariant so the statement above cannot silently go stale.

Issue #381: Extracted from enhanced_orchestrator.py god class refactoring.
Contains workflow planning, step estimation, and capability determination.
"""

from typing import Any, Dict, List, Set

from autobot_shared.logging_manager import get_logger

# Issue #673: Import from autobot_types to avoid circular import with src.orchestrator
from autobot_types import TaskComplexity

from .types import AgentCapability, AgentProfile

logger = get_logger(__name__)


class WorkflowPlanner:
    """
    Plans workflow steps with intelligent agent assignment.

    DEPRECATED — no callers on any public method; see the module docstring for
    the per-capability mapping to the canonical code that supersedes each one.
    Retained in full for reference — no code removed (#13751).

    Handles:
    - Enhanced workflow step planning
    - Capability determination for steps
    - Duration estimation based on agent performance
    """

    # Capability mapping for action types
    CAPABILITY_MAPPING = {
        "research": {AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
        "search": {AgentCapability.RESEARCH},
        "analyze": {AgentCapability.ANALYSIS, AgentCapability.DATA_PROCESSING},
        "document": {
            AgentCapability.DOCUMENTATION,
            AgentCapability.KNOWLEDGE_MANAGEMENT,
        },
        "execute": {AgentCapability.SYSTEM_OPERATIONS},
        "coordinate": {AgentCapability.WORKFLOW_COORDINATION},
        "generate": {AgentCapability.CODE_GENERATION},
        "process": {AgentCapability.DATA_PROCESSING},
    }

    # Agent type to capability mapping
    AGENT_CAPABILITY_MAP = {
        "research": {AgentCapability.RESEARCH},
        "librarian": {
            AgentCapability.KNOWLEDGE_MANAGEMENT,
            AgentCapability.DOCUMENTATION,
        },
        "system_commands": {AgentCapability.SYSTEM_OPERATIONS},
        "orchestrator": {AgentCapability.WORKFLOW_COORDINATION},
    }

    # Base duration estimates by action type
    BASE_DURATIONS = {
        "research": 30.0,
        "search": 15.0,
        "analyze": 20.0,
        "document": 25.0,
        "execute": 10.0,
        "coordinate": 5.0,
    }

    def __init__(
        self,
        base_orchestrator: Any,
        agent_registry: Dict[str, AgentProfile],
        find_best_agent_callback: callable,
    ):
        """
        Initialize the workflow planner.

        Args:
            base_orchestrator: Base orchestrator for step planning
            agent_registry: Registry of available agents
            find_best_agent_callback: Function to find best agent for a task
        """
        self.base_orchestrator = base_orchestrator
        self.agent_registry = agent_registry
        self._find_best_agent = find_best_agent_callback

    async def plan_workflow_steps_with_agents(
        self,
        user_request: str,
        complexity: TaskComplexity,
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Plan workflow steps with intelligent agent assignment.

        Consults the TrajectoryStore (GH#7357) before building from scratch:
        if similar high-reward trajectories exist, logs them for the caller to
        inspect via context["similar_trajectories"].  Step generation always
        proceeds regardless of trajectory hits; reuse/adaptation is advisory.

        Args:
            user_request: The user's request to plan
            complexity: Classified task complexity
            context: Additional context for planning

        Returns:
            List of workflow steps with agent assignments
        """
        # GH#7357: consult trajectory store for similar solved tasks
        await self._annotate_context_with_trajectories(user_request, context)

        # Get base workflow steps from original orchestrator.
        # #13730: coroutine function — without await the loop below iterated a
        # coroutine object rather than the plan.
        base_steps = await self.base_orchestrator.plan_workflow_steps(user_request, complexity)

        steps_with_agents = []

        for step in base_steps:
            # Determine required capabilities for each step
            required_capabilities = self.determine_step_capabilities(step.action, step.agent_type)

            # Find best agent for this step
            assigned_agent = self._find_best_agent(
                task_type=step.agent_type,
                required_capabilities=required_capabilities,
            )

            # #13730: dict keys are this module's own contract (consumed by
            # create_plan_summary_for_approval) and stay as they are; only the
            # attribute reads move to the canonical WorkflowTask names.
            assigned_step = {
                "id": step.task_id,
                "agent_type": step.agent_type,
                "assigned_agent": assigned_agent,
                "action": step.action,
                "inputs": step.inputs,
                "user_approval_required": step.requires_approval,
                "dependencies": step.dependencies or [],
                "required_capabilities": list(required_capabilities),
                "estimated_duration": self.estimate_step_duration(step.action, assigned_agent),
                "status": "planned",
            }

            steps_with_agents.append(assigned_step)

        return steps_with_agents

    def determine_step_capabilities(self, action: str, agent_type: str) -> Set[AgentCapability]:
        """
        Determine required capabilities for a workflow step.

        Args:
            action: Step action description
            agent_type: Type of agent for the step

        Returns:
            Set of required AgentCapabilities
        """
        required_capabilities: Set[AgentCapability] = set()

        # Check action keywords
        for keyword, capabilities in self.CAPABILITY_MAPPING.items():
            if keyword in action.lower():
                required_capabilities.update(capabilities)

        # Agent type specific requirements
        if agent_type in self.AGENT_CAPABILITY_MAP:
            required_capabilities.update(self.AGENT_CAPABILITY_MAP[agent_type])

        # Default capability if none determined
        return required_capabilities or {AgentCapability.ANALYSIS}

    def estimate_step_duration(self, action: str, agent_id: str | None) -> float:
        """
        Estimate duration for a workflow step.

        Args:
            action: Step action description
            agent_id: ID of assigned agent (optional)

        Returns:
            Estimated duration in seconds
        """
        # Get base duration from action type
        estimated_duration = 30.0  # Default

        for action_type, duration in self.BASE_DURATIONS.items():
            if action_type in action.lower():
                estimated_duration = duration
                break

        # Adjust based on agent performance
        if agent_id and agent_id in self.agent_registry:
            agent = self.agent_registry[agent_id]
            if agent.average_completion_time > 0:
                # Use agent's historical performance
                performance_factor = agent.average_completion_time / estimated_duration
                # Cap at 2x base duration
                estimated_duration *= min(performance_factor, 2.0)

        return estimated_duration

    async def get_plan_summary(
        self,
        user_request: str,
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Get workflow plan summary without executing.

        #13730: was ``def``, calling the orchestrator's coroutine planning API
        without awaiting it — ``complexity.value`` and ``len(base_steps)`` both
        operated on coroutine objects. Now ``async def`` so the awaits are legal.
        This method currently has no callers; it is corrected rather than
        removed, and the wiring gap is tracked separately.

        Args:
            user_request: The user's request to plan
            context: Additional context

        Returns:
            Plan summary with steps and estimates
        """
        context = context or {}

        # Classify complexity. #13807: the verdict carries whether anything
        # actually judged this request — a plan built on a defaulted COMPLEX is
        # not the same artefact as one built on a real classification, and the
        # summary is where a reader would otherwise have no way to tell.
        verdict = await self.base_orchestrator.classify_request_complexity_verdict(user_request)
        complexity = verdict.complexity

        # Get base steps (no agent assignment yet)
        base_steps = await self.base_orchestrator.plan_workflow_steps(user_request, complexity)

        return {
            "request": user_request,
            "complexity": complexity.value,
            "complexity_classified": verdict.classified,
            "classification_state": verdict.state.value,
            "total_steps": len(base_steps),
            "steps": [
                {
                    "id": step.task_id,
                    "action": step.action,
                    "agent_type": step.agent_type,
                    "requires_approval": step.requires_approval,
                    "dependencies": step.dependencies or [],
                }
                for step in base_steps
            ],
        }

    def create_plan_summary_for_approval(
        self,
        workflow_id: str,
        user_request: str,
        enhanced_steps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Create plan summary for user approval.

        Args:
            workflow_id: Workflow identifier
            user_request: Original user request
            enhanced_steps: Planned workflow steps

        Returns:
            Plan summary dictionary
        """
        return {
            "workflow_id": workflow_id,
            "request": user_request,
            "total_steps": len(enhanced_steps),
            "estimated_total_duration": sum(step.get("estimated_duration", 10.0) for step in enhanced_steps),
            "steps": [
                {
                    "id": step.get("id"),
                    "action": step.get("action"),
                    "agent_type": step.get("agent_type"),
                    "assigned_agent": step.get("assigned_agent"),
                    "estimated_duration": step.get("estimated_duration"),
                    "requires_approval": step.get("user_approval_required", False),
                    "dependencies": step.get("dependencies", []),
                }
                for step in enhanced_steps
            ],
            "agents_involved": list(
                set(step.get("assigned_agent") for step in enhanced_steps if step.get("assigned_agent"))
            ),
        }

    async def _annotate_context_with_trajectories(
        self,
        user_request: str,
        context: Dict[str, Any],
    ) -> None:
        """Populate context['similar_trajectories'] with past solutions (GH#7357).

        Non-fatal: errors are caught and logged so planning always continues.
        """
        try:
            from autobot_shared.ssot_config import PLANNING_CONTEXT_ENABLED  # noqa: PLC0415

            if not PLANNING_CONTEXT_ENABLED:  # #11015 kill-switch
                return
            from memory.trajectory_store import get_trajectory_store

            # #11015: scope to the caller's tenant so one org's trajectories can't
            # surface in another's plan. Absent tenant → un-scoped (legacy).
            # #11089: also scope to the caller's user (strict intra-tenant isolation).
            tenant_id = str(context.get("tenant_id") or "") or None
            user_id = str(context.get("user_id") or "") or None
            store = await get_trajectory_store()
            similar = await store.find_similar_trajectories(
                user_request, top_k=5, min_reward=0.7, tenant_id=tenant_id, user_id=user_id
            )
            if similar:
                context["similar_trajectories"] = similar
                logger.debug(
                    "WorkflowPlanner: found %d similar trajectories for request %r",
                    len(similar),
                    user_request[:80],
                )
        except Exception as exc:
            logger.warning("WorkflowPlanner: trajectory lookup failed (non-fatal): %s", exc)
