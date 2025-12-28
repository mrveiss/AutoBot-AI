# Planner Module Architecture Design

**Issue**: #645 - Implement Industry-Standard Agent Architecture Patterns
**Author**: mrveiss
**Date**: 2025-12-28
**Status**: Draft

---

## 1. Overview

This document defines the design for a Planner Module inspired by the Manus and Devin agent architectures. The Planner provides:

- Task decomposition into numbered pseudocode steps
- Step status tracking with reflections
- Integration with the Event Stream for progress visibility
- TodoWrite-style progress tracking with enhanced capabilities

---

## 2. Core Concepts

### 2.1 Manus Planner Principles

From the Manus architecture analysis:

1. **Numbered Pseudocode Steps**: Plans are expressed as numbered steps
2. **Status Tracking**: Each step has a status (pending, in_progress, completed, blocked, failed)
3. **Reflections**: Updates include assessment of current state
4. **Plan Updates**: Pseudocode updates when task objective changes
5. **Completion Requirement**: All planned steps must complete before task completion

### 2.2 Devin Dual-Mode Operation

From the Devin architecture:

1. **Planning Mode**: Gather information, understand codebase, create plan
2. **Standard Mode**: Execute plan steps with visibility into next steps
3. **Plan Suggestion**: Call `suggest_plan` only when confident about ALL locations to edit

---

## 3. Data Structures

### 3.1 Plan Step

```python
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Optional
import uuid

class StepStatus(Enum):
    """Status of a plan step"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class PlanStep:
    """A single step in the execution plan"""

    # Identity
    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    step_number: int = 0

    # Content
    description: str = ""
    pseudocode: str = ""  # Detailed implementation hint

    # Status
    status: StepStatus = StepStatus.PENDING

    # Dependencies
    depends_on: list[str] = field(default_factory=list)  # Step IDs this depends on
    blocks: list[str] = field(default_factory=list)  # Step IDs blocked by this

    # Tracking
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    reflection: Optional[str] = None  # Assessment after completion/failure

    # Tool associations
    tools_used: list[str] = field(default_factory=list)
    action_event_ids: list[str] = field(default_factory=list)

    # Metrics
    estimated_complexity: str = "medium"  # low, medium, high
    actual_duration_ms: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "step_number": self.step_number,
            "description": self.description,
            "pseudocode": self.pseudocode,
            "status": self.status.value,
            "depends_on": self.depends_on,
            "blocks": self.blocks,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "reflection": self.reflection,
            "tools_used": self.tools_used,
            "action_event_ids": self.action_event_ids,
            "estimated_complexity": self.estimated_complexity,
            "actual_duration_ms": self.actual_duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlanStep":
        return cls(
            step_id=data["step_id"],
            step_number=data["step_number"],
            description=data["description"],
            pseudocode=data.get("pseudocode", ""),
            status=StepStatus(data["status"]),
            depends_on=data.get("depends_on", []),
            blocks=data.get("blocks", []),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            reflection=data.get("reflection"),
            tools_used=data.get("tools_used", []),
            action_event_ids=data.get("action_event_ids", []),
            estimated_complexity=data.get("estimated_complexity", "medium"),
            actual_duration_ms=data.get("actual_duration_ms"),
        )
```

### 3.2 Execution Plan

```python
class PlanStatus(Enum):
    """Overall plan status"""
    PLANNING = "planning"      # Still being created
    READY = "ready"            # Ready to execute
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class ExecutionPlan:
    """Complete execution plan for a task"""

    # Identity
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""

    # Task context
    task_description: str = ""
    original_request: str = ""

    # Steps
    steps: list[PlanStep] = field(default_factory=list)

    # Status
    status: PlanStatus = PlanStatus.PLANNING
    current_step_number: int = 0

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Tracking
    version: int = 1  # Increments when plan is updated
    update_history: list[dict] = field(default_factory=list)

    # Metrics
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0

    def get_current_step(self) -> Optional[PlanStep]:
        """Get the currently active step"""
        for step in self.steps:
            if step.status == StepStatus.IN_PROGRESS:
                return step
        return None

    def get_next_executable_steps(self) -> list[PlanStep]:
        """Get steps that can be executed (dependencies satisfied)"""
        completed_ids = {s.step_id for s in self.steps if s.status == StepStatus.COMPLETED}
        executable = []

        for step in self.steps:
            if step.status != StepStatus.PENDING:
                continue
            # Check if all dependencies are completed
            if all(dep_id in completed_ids for dep_id in step.depends_on):
                executable.append(step)

        return executable

    def get_parallel_group(self) -> list[PlanStep]:
        """Get steps that can run in parallel (no mutual dependencies)"""
        executable = self.get_next_executable_steps()
        if len(executable) <= 1:
            return executable

        # Group steps that don't depend on each other
        parallel = [executable[0]]
        for step in executable[1:]:
            can_parallel = True
            for parallel_step in parallel:
                if parallel_step.step_id in step.depends_on or step.step_id in parallel_step.depends_on:
                    can_parallel = False
                    break
            if can_parallel:
                parallel.append(step)

        return parallel

    def update_metrics(self):
        """Recalculate plan metrics"""
        self.total_steps = len(self.steps)
        self.completed_steps = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        self.failed_steps = sum(1 for s in self.steps if s.status == StepStatus.FAILED)

        # Update current step number
        for i, step in enumerate(self.steps):
            if step.status == StepStatus.IN_PROGRESS:
                self.current_step_number = i + 1
                break
        else:
            self.current_step_number = self.completed_steps

    def to_dict(self) -> dict:
        self.update_metrics()
        return {
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "task_description": self.task_description,
            "original_request": self.original_request,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status.value,
            "current_step_number": self.current_step_number,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "version": self.version,
            "update_history": self.update_history,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
        }

    def to_pseudocode(self) -> str:
        """Generate numbered pseudocode representation (Manus-style)"""
        lines = [f"# Plan: {self.task_description}", ""]
        for step in self.steps:
            status_marker = {
                StepStatus.PENDING: "[ ]",
                StepStatus.IN_PROGRESS: "[→]",
                StepStatus.COMPLETED: "[✓]",
                StepStatus.BLOCKED: "[⊗]",
                StepStatus.FAILED: "[✗]",
                StepStatus.SKIPPED: "[-]",
            }.get(step.status, "[ ]")

            lines.append(f"{step.step_number}. {status_marker} {step.description}")
            if step.pseudocode:
                for code_line in step.pseudocode.split("\n"):
                    lines.append(f"      {code_line}")
            if step.reflection:
                lines.append(f"      → Reflection: {step.reflection}")
        return "\n".join(lines)
```

---

## 4. Planner Module

### 4.1 Core Interface

```python
from abc import ABC, abstractmethod

class PlannerModule(ABC):
    """Abstract planner interface"""

    @abstractmethod
    async def create_plan(
        self,
        task_description: str,
        context: dict | None = None,
    ) -> ExecutionPlan:
        """Create a new execution plan for a task"""
        pass

    @abstractmethod
    async def update_plan(
        self,
        plan_id: str,
        new_context: dict,
        reason: str,
    ) -> ExecutionPlan:
        """Update an existing plan based on new information"""
        pass

    @abstractmethod
    async def start_step(
        self,
        plan_id: str,
        step_id: str,
    ) -> PlanStep:
        """Mark a step as in_progress"""
        pass

    @abstractmethod
    async def complete_step(
        self,
        plan_id: str,
        step_id: str,
        reflection: str | None = None,
        tools_used: list[str] | None = None,
    ) -> PlanStep:
        """Mark a step as completed with optional reflection"""
        pass

    @abstractmethod
    async def fail_step(
        self,
        plan_id: str,
        step_id: str,
        error: str,
        reflection: str | None = None,
    ) -> PlanStep:
        """Mark a step as failed"""
        pass

    @abstractmethod
    async def get_plan(self, plan_id: str) -> ExecutionPlan | None:
        """Get a plan by ID"""
        pass

    @abstractmethod
    async def get_current_step(self, plan_id: str) -> PlanStep | None:
        """Get the currently executing step"""
        pass
```

### 4.2 LLM-Based Planner Implementation

```python
import logging
from typing import Any

from src.events.stream_manager import EventStreamManager
from src.events.types import AgentEvent, EventType

logger = logging.getLogger(__name__)

class LLMPlannerModule(PlannerModule):
    """LLM-powered planner that generates execution plans"""

    PLAN_GENERATION_PROMPT = """You are a task planner. Create a detailed execution plan for the following task.

TASK: {task_description}

CONTEXT:
{context}

Generate a plan with numbered steps. Each step should be:
1. Atomic - accomplishes one specific thing
2. Testable - has clear success criteria
3. Ordered - respects dependencies

For each step, provide:
- step_number: Sequential number (1, 2, 3...)
- description: What this step accomplishes
- pseudocode: Implementation hints (optional)
- depends_on: List of step numbers this depends on
- estimated_complexity: low, medium, or high

Output as JSON:
{{
  "task_description": "Summarized task",
  "steps": [
    {{
      "step_number": 1,
      "description": "Step description",
      "pseudocode": "Implementation hint",
      "depends_on": [],
      "estimated_complexity": "medium"
    }}
  ]
}}
"""

    def __init__(
        self,
        llm_client: Any,
        event_stream: EventStreamManager,
        redis_client: Any,
    ):
        self.llm = llm_client
        self.event_stream = event_stream
        self.redis = redis_client
        self._plans: dict[str, ExecutionPlan] = {}

    async def create_plan(
        self,
        task_description: str,
        context: dict | None = None,
    ) -> ExecutionPlan:
        """Create a new execution plan using LLM"""

        # Format context for prompt
        context_str = ""
        if context:
            context_str = "\n".join(f"- {k}: {v}" for k, v in context.items())

        prompt = self.PLAN_GENERATION_PROMPT.format(
            task_description=task_description,
            context=context_str or "No additional context provided.",
        )

        # Generate plan with LLM
        response = await self.llm.generate(
            prompt=prompt,
            temperature=0.3,  # Low temperature for consistency
            response_format="json",
        )

        # Parse response
        plan_data = self._parse_plan_response(response)

        # Create plan object
        plan = ExecutionPlan(
            task_description=plan_data["task_description"],
            original_request=task_description,
        )

        # Create steps with proper IDs
        step_id_map = {}  # step_number -> step_id
        for step_data in plan_data["steps"]:
            step = PlanStep(
                step_number=step_data["step_number"],
                description=step_data["description"],
                pseudocode=step_data.get("pseudocode", ""),
                estimated_complexity=step_data.get("estimated_complexity", "medium"),
            )
            step_id_map[step.step_number] = step.step_id
            plan.steps.append(step)

        # Resolve dependencies from step numbers to step IDs
        for step_data in plan_data["steps"]:
            step = plan.steps[step_data["step_number"] - 1]
            step.depends_on = [
                step_id_map[dep_num]
                for dep_num in step_data.get("depends_on", [])
                if dep_num in step_id_map
            ]

        plan.status = PlanStatus.READY
        plan.update_metrics()

        # Store plan
        await self._store_plan(plan)

        # Publish PLAN event
        await self.event_stream.publish(AgentEvent(
            event_type=EventType.PLAN,
            content={
                "task_description": plan.task_description,
                "steps": [s.to_dict() for s in plan.steps],
                "current_step": 0,
                "total_steps": plan.total_steps,
                "status": plan.status.value,
                "is_update": False,
            },
            source="planner",
            task_id=plan.task_id,
        ))

        logger.info(
            "Created plan %s with %d steps for task: %s",
            plan.plan_id, plan.total_steps, task_description[:50]
        )

        return plan

    async def start_step(self, plan_id: str, step_id: str) -> PlanStep:
        """Mark a step as in_progress"""
        plan = await self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        step = self._find_step(plan, step_id)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        step.status = StepStatus.IN_PROGRESS
        step.started_at = datetime.utcnow()
        plan.status = PlanStatus.IN_PROGRESS
        if not plan.started_at:
            plan.started_at = datetime.utcnow()

        plan.update_metrics()
        await self._store_plan(plan)

        # Publish PLAN update event
        await self.event_stream.publish(AgentEvent(
            event_type=EventType.PLAN,
            content={
                "task_description": plan.task_description,
                "steps": [s.to_dict() for s in plan.steps],
                "current_step": plan.current_step_number,
                "total_steps": plan.total_steps,
                "status": plan.status.value,
                "is_update": True,
                "changes_made": [f"Started step {step.step_number}: {step.description}"],
            },
            source="planner",
            task_id=plan.task_id,
            step_number=step.step_number,
        ))

        return step

    async def complete_step(
        self,
        plan_id: str,
        step_id: str,
        reflection: str | None = None,
        tools_used: list[str] | None = None,
    ) -> PlanStep:
        """Mark a step as completed"""
        plan = await self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        step = self._find_step(plan, step_id)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        step.status = StepStatus.COMPLETED
        step.completed_at = datetime.utcnow()
        step.reflection = reflection
        if tools_used:
            step.tools_used = tools_used

        if step.started_at:
            step.actual_duration_ms = (
                step.completed_at - step.started_at
            ).total_seconds() * 1000

        plan.update_metrics()

        # Check if plan is complete
        if plan.completed_steps == plan.total_steps:
            plan.status = PlanStatus.COMPLETED
            plan.completed_at = datetime.utcnow()

        await self._store_plan(plan)

        # Publish PLAN update event
        await self.event_stream.publish(AgentEvent(
            event_type=EventType.PLAN,
            content={
                "task_description": plan.task_description,
                "steps": [s.to_dict() for s in plan.steps],
                "current_step": plan.current_step_number,
                "total_steps": plan.total_steps,
                "status": plan.status.value,
                "is_update": True,
                "changes_made": [f"Completed step {step.step_number}: {step.description}"],
                "reflection": reflection,
            },
            source="planner",
            task_id=plan.task_id,
            step_number=step.step_number,
        ))

        return step

    async def fail_step(
        self,
        plan_id: str,
        step_id: str,
        error: str,
        reflection: str | None = None,
    ) -> PlanStep:
        """Mark a step as failed"""
        plan = await self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        step = self._find_step(plan, step_id)
        if not step:
            raise ValueError(f"Step not found: {step_id}")

        step.status = StepStatus.FAILED
        step.completed_at = datetime.utcnow()
        step.reflection = reflection or f"Failed: {error}"

        if step.started_at:
            step.actual_duration_ms = (
                step.completed_at - step.started_at
            ).total_seconds() * 1000

        plan.update_metrics()

        # Mark blocked steps
        for other_step in plan.steps:
            if step.step_id in other_step.depends_on:
                other_step.status = StepStatus.BLOCKED

        await self._store_plan(plan)

        # Publish PLAN update event
        await self.event_stream.publish(AgentEvent(
            event_type=EventType.PLAN,
            content={
                "task_description": plan.task_description,
                "steps": [s.to_dict() for s in plan.steps],
                "current_step": plan.current_step_number,
                "total_steps": plan.total_steps,
                "status": plan.status.value,
                "is_update": True,
                "changes_made": [f"Failed step {step.step_number}: {error}"],
                "reflection": reflection,
            },
            source="planner",
            task_id=plan.task_id,
            step_number=step.step_number,
        ))

        return step

    async def update_plan(
        self,
        plan_id: str,
        new_context: dict,
        reason: str,
    ) -> ExecutionPlan:
        """Update an existing plan based on new information"""
        plan = await self.get_plan(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        # Store update in history
        plan.update_history.append({
            "version": plan.version,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "previous_steps": [s.to_dict() for s in plan.steps],
        })
        plan.version += 1

        # Re-plan remaining steps
        remaining_descriptions = [
            s.description for s in plan.steps
            if s.status in (StepStatus.PENDING, StepStatus.BLOCKED)
        ]

        if remaining_descriptions:
            # Generate updated plan for remaining work
            new_plan = await self.create_plan(
                task_description=f"Continue: {plan.task_description}. Remaining: {', '.join(remaining_descriptions)}",
                context=new_context,
            )

            # Replace pending/blocked steps
            completed_steps = [s for s in plan.steps if s.status == StepStatus.COMPLETED]
            plan.steps = completed_steps + new_plan.steps

            # Renumber steps
            for i, step in enumerate(plan.steps):
                step.step_number = i + 1

        plan.update_metrics()
        await self._store_plan(plan)

        # Publish PLAN update event
        await self.event_stream.publish(AgentEvent(
            event_type=EventType.PLAN,
            content={
                "task_description": plan.task_description,
                "steps": [s.to_dict() for s in plan.steps],
                "current_step": plan.current_step_number,
                "total_steps": plan.total_steps,
                "status": plan.status.value,
                "is_update": True,
                "changes_made": [f"Plan updated: {reason}"],
            },
            source="planner",
            task_id=plan.task_id,
        ))

        return plan

    # Helper methods
    async def _store_plan(self, plan: ExecutionPlan) -> None:
        """Store plan in Redis"""
        key = f"autobot:plans:{plan.plan_id}"
        await self.redis.set(key, json.dumps(plan.to_dict()), ex=86400)
        self._plans[plan.plan_id] = plan

    async def get_plan(self, plan_id: str) -> ExecutionPlan | None:
        """Get plan from cache or Redis"""
        if plan_id in self._plans:
            return self._plans[plan_id]

        key = f"autobot:plans:{plan_id}"
        data = await self.redis.get(key)
        if data:
            plan_dict = json.loads(data)
            plan = ExecutionPlan.from_dict(plan_dict)
            self._plans[plan_id] = plan
            return plan
        return None

    async def get_current_step(self, plan_id: str) -> PlanStep | None:
        """Get currently executing step"""
        plan = await self.get_plan(plan_id)
        return plan.get_current_step() if plan else None

    def _find_step(self, plan: ExecutionPlan, step_id: str) -> PlanStep | None:
        """Find a step by ID"""
        for step in plan.steps:
            if step.step_id == step_id:
                return step
        return None

    def _parse_plan_response(self, response: str) -> dict:
        """Parse LLM response into plan data"""
        # Handle JSON extraction from response
        import json
        import re

        # Try to extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError("Failed to parse plan from LLM response")
```

---

## 5. Integration with TodoWrite

### 5.1 TodoWrite Compatibility

The Planner Module generates TodoWrite-compatible output:

```python
def plan_to_todowrite(plan: ExecutionPlan) -> list[dict]:
    """Convert plan to TodoWrite format for frontend display"""
    todos = []
    for step in plan.steps:
        status_map = {
            StepStatus.PENDING: "pending",
            StepStatus.IN_PROGRESS: "in_progress",
            StepStatus.COMPLETED: "completed",
            StepStatus.BLOCKED: "pending",  # TodoWrite doesn't have blocked
            StepStatus.FAILED: "pending",   # Show as needing retry
            StepStatus.SKIPPED: "completed",
        }

        todos.append({
            "content": step.description,
            "status": status_map.get(step.status, "pending"),
            "activeForm": f"Step {step.step_number}: {step.description}",
        })

    return todos
```

---

## 6. Agent Loop Integration

### 6.1 Modified Agent Orchestrator

```python
class AgentOrchestrator:
    def __init__(self):
        self.planner = LLMPlannerModule(...)
        self.event_stream = RedisEventStreamManager()

    async def process_request(self, user_message: str, task_id: str) -> str:
        # 1. Create plan
        plan = await self.planner.create_plan(
            task_description=user_message,
            context={"task_id": task_id},
        )
        plan.task_id = task_id

        # 2. Execute plan steps
        while True:
            executable = plan.get_next_executable_steps()
            if not executable:
                break

            # Get parallel group (Cursor pattern)
            parallel_steps = plan.get_parallel_group()

            if len(parallel_steps) > 1:
                # Execute in parallel
                results = await asyncio.gather(*[
                    self._execute_step(plan, step)
                    for step in parallel_steps
                ], return_exceptions=True)
            else:
                # Execute single step
                result = await self._execute_step(plan, parallel_steps[0])

            # Refresh plan state
            plan = await self.planner.get_plan(plan.plan_id)

        # 3. Generate final response
        return await self._synthesize_response(plan)

    async def _execute_step(
        self,
        plan: ExecutionPlan,
        step: PlanStep,
    ) -> Any:
        """Execute a single plan step"""
        await self.planner.start_step(plan.plan_id, step.step_id)

        try:
            # Execute step logic based on description
            result = await self._run_step_tools(step)

            await self.planner.complete_step(
                plan.plan_id,
                step.step_id,
                reflection=f"Completed successfully: {result[:100] if result else 'OK'}",
            )
            return result

        except Exception as e:
            await self.planner.fail_step(
                plan.plan_id,
                step.step_id,
                error=str(e),
                reflection="Step failed, may need retry or alternative approach",
            )
            raise
```

---

## 7. Configuration

```python
@dataclass
class PlannerConfig:
    """Planner module configuration"""
    max_steps_per_plan: int = 20
    plan_ttl_seconds: int = 86400
    llm_temperature: float = 0.3
    enable_parallel_steps: bool = True
    max_parallel_steps: int = 5
    auto_retry_failed_steps: bool = True
    max_retries_per_step: int = 3
```

---

## 8. File Structure

```
src/planner/
├── __init__.py
├── types.py           # StepStatus, PlanStatus, PlanStep, ExecutionPlan
├── planner.py         # PlannerModule interface
├── llm_planner.py     # LLMPlannerModule implementation
├── todowrite_compat.py # TodoWrite compatibility layer
└── utils.py           # Helper functions
```

---

## 9. Testing Strategy

```python
async def test_plan_creation():
    """Test plan creation with steps"""
    planner = LLMPlannerModule(...)
    plan = await planner.create_plan("Implement user authentication")

    assert plan.status == PlanStatus.READY
    assert len(plan.steps) > 0
    assert all(s.status == StepStatus.PENDING for s in plan.steps)

async def test_step_execution_flow():
    """Test start → complete step flow"""
    planner = LLMPlannerModule(...)
    plan = await planner.create_plan("Simple task")
    step = plan.steps[0]

    await planner.start_step(plan.plan_id, step.step_id)
    updated_step = await planner.complete_step(
        plan.plan_id, step.step_id, reflection="Done"
    )

    assert updated_step.status == StepStatus.COMPLETED
    assert updated_step.reflection == "Done"

async def test_parallel_step_detection():
    """Test parallel step identification"""
    plan = ExecutionPlan(steps=[
        PlanStep(step_id="a", step_number=1, depends_on=[]),
        PlanStep(step_id="b", step_number=2, depends_on=[]),
        PlanStep(step_id="c", step_number=3, depends_on=["a", "b"]),
    ])

    parallel = plan.get_parallel_group()
    assert len(parallel) == 2  # a and b can run in parallel
    assert "c" not in [s.step_id for s in parallel]
```

---

## 10. References

- Manus Planner Module: `docs/external_apps/.../Manus Agent Tools & Prompt/Modules.txt`
- Devin Planning Mode: `docs/external_apps/.../Devin AI/Prompt.txt`
- Existing TodoWrite: `src/utils/todo_manager.py` (if exists)
