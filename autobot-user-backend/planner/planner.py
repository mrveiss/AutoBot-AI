# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Planner Module Implementation

LLM-powered task planning with numbered pseudocode steps.
Integrates with Event Stream for visibility into planning process.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from backend.constants.threshold_constants import (
    BatchConfig,
    LLMDefaults,
    RetryConfig,
    TimingConstants,
)
from backend.events.types import create_plan_event
from backend.planner.types import ExecutionPlan, PlanStatus, PlanStep, StepStatus

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class PlannerConfig:
    """Planner module configuration.

    Issue #670: Uses centralized constants from threshold_constants.py
    """

    max_steps_per_plan: int = 20  # Plan-specific, no constant needed
    plan_ttl_seconds: int = TimingConstants.HOURLY_INTERVAL * 24  # 86400 = 24 hours
    llm_temperature: float = (
        LLMDefaults.DEFAULT_TEMPERATURE - 0.4
    )  # 0.3 for planning precision
    enable_parallel_steps: bool = True
    max_parallel_steps: int = BatchConfig.SMALL_BATCH // 2  # 5 parallel steps
    auto_retry_failed_steps: bool = True
    max_retries_per_step: int = RetryConfig.DEFAULT_RETRIES


# =============================================================================
# Abstract Interface
# =============================================================================


class PlannerModule(ABC):
    """Abstract planner interface"""

    @abstractmethod
    async def create_plan(
        self,
        task_description: str,
        context: Optional[dict] = None,
    ) -> ExecutionPlan:
        """Create a new execution plan for a task"""

    @abstractmethod
    async def update_plan(
        self,
        plan_id: str,
        new_context: dict,
        reason: str,
    ) -> ExecutionPlan:
        """Update an existing plan based on new information"""

    @abstractmethod
    async def start_step(
        self,
        plan_id: str,
        step_id: str,
    ) -> PlanStep:
        """Mark a step as in_progress"""

    @abstractmethod
    async def complete_step(
        self,
        plan_id: str,
        step_id: str,
        reflection: Optional[str] = None,
        tools_used: Optional[list[str]] = None,
    ) -> PlanStep:
        """Mark a step as completed with optional reflection"""

    @abstractmethod
    async def fail_step(
        self,
        plan_id: str,
        step_id: str,
        error: str,
        reflection: Optional[str] = None,
    ) -> PlanStep:
        """Mark a step as failed"""

    @abstractmethod
    async def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get a plan by ID"""

    @abstractmethod
    async def get_current_step(self, plan_id: str) -> Optional[PlanStep]:
        """Get the currently executing step"""


# =============================================================================
# LLM-Based Implementation
# =============================================================================


class LLMPlannerModule(PlannerModule):
    """LLM-powered planner that generates execution plans"""

    PLAN_GENERATION_PROMPT = """You are a task planner for an AI coding assistant. Create a detailed execution plan for the following task.

TASK: {task_description}

CONTEXT:
{context}

Generate a plan with numbered steps. Each step should be:
1. Atomic - accomplishes one specific thing
2. Testable - has clear success criteria
3. Ordered - respects dependencies between steps

For each step, provide:
- step_number: Sequential number (1, 2, 3...)
- description: What this step accomplishes (concise, action-oriented)
- pseudocode: Implementation hints or commands (optional, for complex steps)
- depends_on: List of step numbers this depends on (empty if independent)
- estimated_complexity: low, medium, or high

IMPORTANT:
- Keep steps focused and achievable
- Maximum {max_steps} steps
- Steps without dependencies can potentially run in parallel
- Include verification/testing as separate steps when appropriate

Output ONLY valid JSON in this format:
{{
  "task_description": "Summarized task in 1 sentence",
  "steps": [
    {{
      "step_number": 1,
      "description": "Step description",
      "pseudocode": "Optional implementation hint",
      "depends_on": [],
      "estimated_complexity": "medium"
    }},
    {{
      "step_number": 2,
      "description": "Another step",
      "pseudocode": "",
      "depends_on": [1],
      "estimated_complexity": "low"
    }}
  ]
}}
"""

    def __init__(
        self,
        llm_client: Any,
        event_stream: Any,
        redis_client: Optional[Any] = None,
        config: Optional[PlannerConfig] = None,
    ):
        self.llm = llm_client
        self.event_stream = event_stream
        self.redis = redis_client
        self.config = config or PlannerConfig()
        self._plans: dict[str, ExecutionPlan] = {}

    def _format_context_for_prompt(self, context: dict) -> str:
        """
        Format context dict for LLM prompt (Issue #665: extracted).

        Args:
            context: Context dictionary

        Returns:
            Formatted context string
        """
        if not context:
            return "No additional context provided."

        context_items = []
        for k, v in context.items():
            if k not in ("task_id",):  # Skip internal keys
                context_items.append(f"- {k}: {v}")

        return (
            "\n".join(context_items)
            if context_items
            else "No additional context provided."
        )

    def _populate_plan_steps(self, plan: ExecutionPlan, plan_data: dict) -> None:
        """
        Populate plan with steps and resolve dependencies (Issue #665: extracted).

        Args:
            plan: ExecutionPlan to populate
            plan_data: Parsed plan data from LLM
        """
        step_id_map: dict[int, str] = {}  # step_number -> step_id

        # Create steps with proper IDs
        for step_data in plan_data.get("steps", []):
            step = PlanStep(
                step_number=step_data.get("step_number", len(plan.steps) + 1),
                description=step_data.get("description", ""),
                pseudocode=step_data.get("pseudocode", ""),
                estimated_complexity=step_data.get("estimated_complexity", "medium"),
            )
            step_id_map[step.step_number] = step.step_id
            plan.steps.append(step)

        # Resolve dependencies from step numbers to step IDs
        for step_data in plan_data.get("steps", []):
            step_num = step_data.get("step_number", 0)
            step = plan.get_step_by_number(step_num)
            if step:
                step.depends_on = [
                    step_id_map[dep_num]
                    for dep_num in step_data.get("depends_on", [])
                    if dep_num in step_id_map
                ]

    async def _publish_plan_event(
        self,
        plan: ExecutionPlan,
        is_update: bool,
        changes_made: Optional[list[str]] = None,
        reflection: Optional[str] = None,
    ) -> None:
        """
        Publish a plan event to the event stream. Issue #620.

        Args:
            plan: The execution plan to publish
            is_update: Whether this is an update to existing plan
            changes_made: List of changes made (for updates)
            reflection: Optional reflection text
        """
        if not self.event_stream:
            return

        event = create_plan_event(
            task_description=plan.task_description,
            steps=[s.to_dict() for s in plan.steps],
            current_step=plan.current_step_number,
            total_steps=plan.total_steps,
            status=plan.status.value,
            task_id=plan.task_id,
            is_update=is_update,
            changes_made=changes_made,
            reflection=reflection,
        )
        await self.event_stream.publish(event)

    async def _get_plan_and_step(
        self, plan_id: str, step_id: str
    ) -> tuple[ExecutionPlan, PlanStep]:
        """
        Retrieve plan and step by IDs, raising errors if not found. Issue #620.

        Args:
            plan_id: The plan identifier
            step_id: The step identifier

        Returns:
            Tuple of (ExecutionPlan, PlanStep)

        Raises:
            ValueError: If plan or step not found
        """
        plan = await self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        step = plan.get_step_by_id(step_id)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        return plan, step

    async def _generate_plan_data(self, task_description: str, context: dict) -> dict:
        """
        Generate plan data using LLM or fallback. Issue #620.

        Args:
            task_description: Description of the task
            context: Context dictionary

        Returns:
            Plan data dictionary with task_description and steps
        """
        context_str = self._format_context_for_prompt(context)

        prompt = self.PLAN_GENERATION_PROMPT.format(
            task_description=task_description,
            context=context_str,
            max_steps=self.config.max_steps_per_plan,
        )

        try:
            if hasattr(self.llm, "generate"):
                response = await self.llm.generate(
                    prompt=prompt,
                    temperature=self.config.llm_temperature,
                )
            elif hasattr(self.llm, "complete"):
                response = await self.llm.complete(prompt)
            else:
                response = self._generate_fallback_plan(task_description)

            return self._parse_plan_response(response)

        except Exception as e:
            logger.warning("LLM plan generation failed: %s, using fallback", e)
            return self._generate_simple_plan(task_description)

    async def create_plan(
        self,
        task_description: str,
        context: Optional[dict] = None,
    ) -> ExecutionPlan:
        """
        Create a new execution plan using LLM. Issue #620.

        Args:
            task_description: Description of the task to plan
            context: Optional context dictionary

        Returns:
            ExecutionPlan with generated steps
        """
        context = context or {}

        # Generate plan data using LLM or fallback (Issue #620: uses helper)
        plan_data = await self._generate_plan_data(task_description, context)

        # Create plan object
        plan = ExecutionPlan(
            task_description=plan_data.get("task_description", task_description),
            original_request=task_description,
            task_id=context.get("task_id", ""),
        )

        # Populate steps and resolve dependencies (Issue #665: uses helper)
        self._populate_plan_steps(plan, plan_data)

        plan.status = PlanStatus.READY
        plan.update_metrics()

        # Store plan
        await self._store_plan(plan)

        # Publish PLAN event (Issue #620: uses helper)
        await self._publish_plan_event(plan, is_update=False)

        logger.info(
            "Created plan %s with %d steps for: %s",
            plan.plan_id[:8],
            plan.total_steps,
            task_description[:50],
        )

        return plan

    async def start_step(self, plan_id: str, step_id: str) -> PlanStep:
        """
        Mark a step as in_progress. Issue #620.

        Args:
            plan_id: The plan identifier
            step_id: The step identifier

        Returns:
            The updated PlanStep
        """
        plan, step = await self._get_plan_and_step(plan_id, step_id)

        step.status = StepStatus.IN_PROGRESS
        step.started_at = datetime.utcnow()
        plan.status = PlanStatus.IN_PROGRESS

        if not plan.started_at:
            plan.started_at = datetime.utcnow()

        plan.update_metrics()
        await self._store_plan(plan)

        await self._publish_plan_event(
            plan,
            is_update=True,
            changes_made=[f"Started step {step.step_number}: {step.description}"],
        )

        logger.debug("Started step %d: %s", step.step_number, step.description[:40])
        return step

    async def complete_step(
        self,
        plan_id: str,
        step_id: str,
        reflection: Optional[str] = None,
        tools_used: Optional[list[str]] = None,
    ) -> PlanStep:
        """
        Mark a step as completed. Issue #620.

        Args:
            plan_id: The plan identifier
            step_id: The step identifier
            reflection: Optional reflection on the completed step
            tools_used: Optional list of tools used during step

        Returns:
            The updated PlanStep
        """
        plan, step = await self._get_plan_and_step(plan_id, step_id)

        self._finalize_step_completion(step, reflection, tools_used)
        self._check_plan_completion(plan)

        await self._store_plan(plan)

        await self._publish_plan_event(
            plan,
            is_update=True,
            changes_made=[f"Completed step {step.step_number}: {step.description}"],
            reflection=reflection,
        )

        logger.debug(
            "Completed step %d: %s (%.1fms)",
            step.step_number,
            step.description[:40],
            step.actual_duration_ms or 0,
        )
        return step

    def _finalize_step_completion(
        self,
        step: PlanStep,
        reflection: Optional[str] = None,
        tools_used: Optional[list[str]] = None,
    ) -> None:
        """
        Finalize step completion by setting status and calculating duration. Issue #620.

        Args:
            step: The step to finalize
            reflection: Optional reflection text
            tools_used: Optional list of tools used
        """
        step.status = StepStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.reflection = reflection

        if tools_used:
            step.tools_used = tools_used

        if step.started_at:
            step.actual_duration_ms = (
                step.completed_at - step.started_at
            ).total_seconds() * 1000

    def _check_plan_completion(self, plan: ExecutionPlan) -> None:
        """
        Check if plan is complete and update status accordingly. Issue #620.

        Args:
            plan: The plan to check
        """
        plan.update_metrics()

        if plan.is_complete():
            plan.status = PlanStatus.COMPLETED
            plan.completed_at = datetime.utcnow()

    async def fail_step(
        self,
        plan_id: str,
        step_id: str,
        error: str,
        reflection: Optional[str] = None,
    ) -> PlanStep:
        """
        Mark a step as failed. Issue #620.

        Args:
            plan_id: The plan identifier
            step_id: The step identifier
            error: Error message describing the failure
            reflection: Optional reflection on the failure

        Returns:
            The updated PlanStep
        """
        plan, step = await self._get_plan_and_step(plan_id, step_id)

        self._finalize_step_failure(plan, step, error, reflection)

        await self._store_plan(plan)

        await self._publish_plan_event(
            plan,
            is_update=True,
            changes_made=[f"Failed step {step.step_number}: {error}"],
            reflection=reflection,
        )

        logger.warning(
            "Failed step %d: %s - %s", step.step_number, step.description[:40], error
        )
        return step

    def _finalize_step_failure(
        self,
        plan: ExecutionPlan,
        step: PlanStep,
        error: str,
        reflection: Optional[str] = None,
    ) -> None:
        """
        Finalize step failure and block dependent steps. Issue #620.

        Args:
            plan: The execution plan
            step: The failed step
            error: Error message
            reflection: Optional reflection text
        """
        step.status = StepStatus.FAILED
        step.completed_at = datetime.utcnow()
        step.reflection = reflection or f"Failed: {error}"

        if step.started_at:
            step.actual_duration_ms = (
                step.completed_at - step.started_at
            ).total_seconds() * 1000

        plan.update_metrics()

        # Mark dependent steps as blocked
        for other_step in plan.steps:
            if step.step_id in other_step.depends_on:
                other_step.status = StepStatus.BLOCKED

        # Update plan status
        if plan.has_failures():
            plan.status = PlanStatus.FAILED

    async def skip_step(
        self,
        plan_id: str,
        step_id: str,
        reason: str,
    ) -> PlanStep:
        """
        Skip a step (won't block dependents). Issue #620.

        Args:
            plan_id: The plan identifier
            step_id: The step identifier
            reason: Reason for skipping

        Returns:
            The updated PlanStep
        """
        plan, step = await self._get_plan_and_step(plan_id, step_id)

        step.status = StepStatus.SKIPPED
        step.reflection = f"Skipped: {reason}"
        step.completed_at = datetime.utcnow()

        plan.update_metrics()
        await self._store_plan(plan)

        logger.info(
            "Skipped step %d: %s - %s", step.step_number, step.description[:40], reason
        )
        return step

    async def update_plan(
        self,
        plan_id: str,
        new_context: dict,
        reason: str,
    ) -> ExecutionPlan:
        """
        Update an existing plan based on new information. Issue #620.

        Args:
            plan_id: The plan identifier
            new_context: New context for replanning
            reason: Reason for the update

        Returns:
            The updated ExecutionPlan
        """
        plan = await self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        self._record_plan_update_history(plan, reason)
        await self._replan_remaining_steps(plan, new_context)

        plan.update_metrics()
        await self._store_plan(plan)

        await self._publish_plan_event(
            plan,
            is_update=True,
            changes_made=[f"Plan updated: {reason}"],
        )

        logger.info("Updated plan %s: %s", plan.plan_id[:8], reason)
        return plan

    def _record_plan_update_history(self, plan: ExecutionPlan, reason: str) -> None:
        """
        Record plan update in history and increment version. Issue #620.

        Args:
            plan: The plan to update
            reason: Reason for the update
        """
        plan.update_history.append(
            {
                "version": plan.version,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat(),
                "previous_steps": [s.to_dict() for s in plan.steps],
            }
        )
        plan.version += 1

    async def _replan_remaining_steps(
        self, plan: ExecutionPlan, new_context: dict
    ) -> None:
        """
        Re-plan remaining steps based on new context. Issue #620.

        Args:
            plan: The plan to update
            new_context: New context for replanning
        """
        remaining = [
            s
            for s in plan.steps
            if s.status in (StepStatus.PENDING, StepStatus.BLOCKED)
        ]

        if not remaining:
            return

        remaining_descriptions = [s.description for s in remaining]
        new_context["remaining_work"] = ", ".join(remaining_descriptions)

        # Generate updated plan for remaining work
        new_plan = await self.create_plan(
            task_description=f"Continue: {plan.task_description}",
            context=new_context,
        )

        # Replace pending/blocked steps
        completed_steps = [s for s in plan.steps if s.status == StepStatus.COMPLETED]
        in_progress = [s for s in plan.steps if s.status == StepStatus.IN_PROGRESS]

        plan.steps = completed_steps + in_progress + new_plan.steps

        # Renumber steps
        for i, step in enumerate(plan.steps):
            step.step_number = i + 1

    async def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get plan from cache or Redis"""
        # Check in-memory cache first
        if plan_id in self._plans:
            return self._plans[plan_id]

        # Try Redis if available
        if self.redis:
            try:
                key = f"autobot:plans:{plan_id}"
                data = await self.redis.get(key)
                if data:
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    plan = ExecutionPlan.from_json(data)
                    self._plans[plan_id] = plan
                    return plan
            except Exception as e:
                logger.warning("Failed to get plan from Redis: %s", e)

        return None

    async def get_current_step(self, plan_id: str) -> Optional[PlanStep]:
        """Get currently executing step"""
        plan = await self.get_plan(plan_id)
        return plan.get_current_step() if plan else None

    async def _store_plan(self, plan: ExecutionPlan) -> None:
        """Store plan in cache and optionally Redis"""
        self._plans[plan.plan_id] = plan

        if self.redis:
            try:
                key = f"autobot:plans:{plan.plan_id}"
                await self.redis.set(
                    key,
                    plan.to_json(),
                    ex=self.config.plan_ttl_seconds,
                )
            except Exception as e:
                logger.warning("Failed to store plan in Redis: %s", e)

    def _parse_plan_response(self, response: str) -> dict:
        """Parse LLM response into plan data"""
        # Try to extract JSON from response
        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        raise ValueError("Failed to parse plan from LLM response")

    def _generate_simple_plan(self, task_description: str) -> dict:
        """Generate a simple fallback plan without LLM"""
        return {
            "task_description": task_description,
            "steps": [
                {
                    "step_number": 1,
                    "description": f"Execute task: {task_description}",
                    "pseudocode": "",
                    "depends_on": [],
                    "estimated_complexity": "medium",
                },
                {
                    "step_number": 2,
                    "description": "Verify completion",
                    "pseudocode": "",
                    "depends_on": [1],
                    "estimated_complexity": "low",
                },
            ],
        }

    def _generate_fallback_plan(self, task_description: str) -> str:
        """Generate fallback JSON when LLM unavailable"""
        plan_data = self._generate_simple_plan(task_description)
        return json.dumps(plan_data)


# =============================================================================
# In-Memory Planner (for testing)
# =============================================================================


class InMemoryPlannerModule(PlannerModule):
    """Simple in-memory planner for testing"""

    def __init__(self):
        self._plans: dict[str, ExecutionPlan] = {}

    async def create_plan(
        self,
        task_description: str,
        context: Optional[dict] = None,
    ) -> ExecutionPlan:
        """Create a simple 2-step plan"""
        plan = ExecutionPlan(
            task_description=task_description,
            original_request=task_description,
            task_id=context.get("task_id", "") if context else "",
            status=PlanStatus.READY,
        )

        plan.steps = [
            PlanStep(
                step_number=1,
                description=f"Execute: {task_description}",
            ),
            PlanStep(
                step_number=2,
                description="Verify completion",
                depends_on=[plan.steps[0].step_id] if plan.steps else [],
            ),
        ]

        # Fix dependency for step 2
        if len(plan.steps) > 1:
            plan.steps[1].depends_on = [plan.steps[0].step_id]

        plan.update_metrics()
        self._plans[plan.plan_id] = plan
        return plan

    async def update_plan(
        self,
        plan_id: str,
        new_context: dict,
        reason: str,
    ) -> ExecutionPlan:
        """Update plan (no-op for simple planner)"""
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")
        return plan

    async def start_step(self, plan_id: str, step_id: str) -> PlanStep:
        """Mark step as in_progress"""
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        step = plan.get_step_by_id(step_id)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        step.status = StepStatus.IN_PROGRESS
        step.started_at = datetime.utcnow()
        plan.status = PlanStatus.IN_PROGRESS
        plan.update_metrics()
        return step

    async def complete_step(
        self,
        plan_id: str,
        step_id: str,
        reflection: Optional[str] = None,
        tools_used: Optional[list[str]] = None,
    ) -> PlanStep:
        """Mark step as completed"""
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        step = plan.get_step_by_id(step_id)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        step.status = StepStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.reflection = reflection
        plan.update_metrics()

        if plan.is_complete():
            plan.status = PlanStatus.COMPLETED
            plan.completed_at = datetime.utcnow()

        return step

    async def fail_step(
        self,
        plan_id: str,
        step_id: str,
        error: str,
        reflection: Optional[str] = None,
    ) -> PlanStep:
        """Mark step as failed"""
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        step = plan.get_step_by_id(step_id)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        step.status = StepStatus.FAILED
        step.reflection = reflection or error
        plan.status = PlanStatus.FAILED
        plan.update_metrics()
        return step

    async def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Get plan by ID"""
        return self._plans.get(plan_id)

    async def get_current_step(self, plan_id: str) -> Optional[PlanStep]:
        """Get current step"""
        plan = self._plans.get(plan_id)
        return plan.get_current_step() if plan else None
