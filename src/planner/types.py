# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Planner Type Definitions

Data structures for execution plans and steps.
Based on Manus numbered pseudocode pattern.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class StepStatus(Enum):
    """Status of a plan step"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStatus(Enum):
    """Overall plan status"""

    PLANNING = "planning"  # Still being created
    READY = "ready"  # Ready to execute
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "reflection": self.reflection,
            "tools_used": self.tools_used,
            "action_event_ids": self.action_event_ids,
            "estimated_complexity": self.estimated_complexity,
            "actual_duration_ms": self.actual_duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlanStep":
        return cls(
            step_id=data.get("step_id", str(uuid.uuid4())),
            step_number=data.get("step_number", 0),
            description=data.get("description", ""),
            pseudocode=data.get("pseudocode", ""),
            status=StepStatus(data.get("status", "pending")),
            depends_on=data.get("depends_on", []),
            blocks=data.get("blocks", []),
            started_at=(
                datetime.fromisoformat(data["started_at"])
                if data.get("started_at")
                else None
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"])
                if data.get("completed_at")
                else None
            ),
            reflection=data.get("reflection"),
            tools_used=data.get("tools_used", []),
            action_event_ids=data.get("action_event_ids", []),
            estimated_complexity=data.get("estimated_complexity", "medium"),
            actual_duration_ms=data.get("actual_duration_ms"),
        )

    def __repr__(self) -> str:
        return (
            f"PlanStep({self.step_number}: {self.description[:30]}... "
            f"[{self.status.value}])"
        )


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
        completed_ids = {
            s.step_id for s in self.steps if s.status == StepStatus.COMPLETED
        }
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
                if (
                    parallel_step.step_id in step.depends_on
                    or step.step_id in parallel_step.depends_on
                ):
                    can_parallel = False
                    break
            if can_parallel:
                parallel.append(step)

        return parallel

    def get_step_by_id(self, step_id: str) -> Optional[PlanStep]:
        """Find a step by its ID"""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def get_step_by_number(self, step_number: int) -> Optional[PlanStep]:
        """Find a step by its number"""
        for step in self.steps:
            if step.step_number == step_number:
                return step
        return None

    def update_metrics(self) -> None:
        """Recalculate plan metrics"""
        self.total_steps = len(self.steps)
        self.completed_steps = sum(
            1 for s in self.steps if s.status == StepStatus.COMPLETED
        )
        self.failed_steps = sum(1 for s in self.steps if s.status == StepStatus.FAILED)

        # Update current step number
        for i, step in enumerate(self.steps):
            if step.status == StepStatus.IN_PROGRESS:
                self.current_step_number = i + 1
                break
        else:
            self.current_step_number = self.completed_steps

    def is_complete(self) -> bool:
        """Check if plan is fully completed"""
        return all(
            s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in self.steps
        )

    def has_failures(self) -> bool:
        """Check if any steps have failed"""
        return any(s.status == StepStatus.FAILED for s in self.steps)

    def get_progress_percentage(self) -> float:
        """Get completion percentage"""
        if not self.steps:
            return 0.0
        return (self.completed_steps / self.total_steps) * 100

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
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "version": self.version,
            "update_history": self.update_history,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionPlan":
        plan = cls(
            plan_id=data.get("plan_id", str(uuid.uuid4())),
            task_id=data.get("task_id", ""),
            task_description=data.get("task_description", ""),
            original_request=data.get("original_request", ""),
            steps=[PlanStep.from_dict(s) for s in data.get("steps", [])],
            status=PlanStatus(data.get("status", "planning")),
            current_step_number=data.get("current_step_number", 0),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.utcnow()
            ),
            started_at=(
                datetime.fromisoformat(data["started_at"])
                if data.get("started_at")
                else None
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"])
                if data.get("completed_at")
                else None
            ),
            version=data.get("version", 1),
            update_history=data.get("update_history", []),
        )
        plan.update_metrics()
        return plan

    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "ExecutionPlan":
        """Deserialize from JSON string"""
        return cls.from_dict(json.loads(json_str))

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

    def to_todowrite_format(self) -> list[dict]:
        """Convert to TodoWrite-compatible format for frontend display"""
        todos = []
        for step in self.steps:
            status_map = {
                StepStatus.PENDING: "pending",
                StepStatus.IN_PROGRESS: "in_progress",
                StepStatus.COMPLETED: "completed",
                StepStatus.BLOCKED: "pending",
                StepStatus.FAILED: "pending",
                StepStatus.SKIPPED: "completed",
            }

            todos.append(
                {
                    "content": step.description,
                    "status": status_map.get(step.status, "pending"),
                    "activeForm": f"Step {step.step_number}: {step.description}",
                }
            )

        return todos

    def __repr__(self) -> str:
        self.update_metrics()
        return (
            f"ExecutionPlan(id={self.plan_id[:8]}..., "
            f"status={self.status.value}, "
            f"steps={self.completed_steps}/{self.total_steps})"
        )
