# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Orchestration Types Module

Issue #381: Extracted from enhanced_multi_agent_orchestrator.py god class refactoring.
Issue #6951 Phase 2B: ``AgentTask`` and ``WorkflowPlan`` are now thin subclasses
of the canonical ``autobot_shared.workflow.WorkflowTask`` / ``WorkflowPlan``.
The local definitions only add behaviour the canonical shapes intentionally
omit (task lifecycle methods + structured success criteria), keeping fields
in one place.
"""

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, FrozenSet, List

if TYPE_CHECKING:
    from .success_criteria import SuccessCriteria

from autobot_shared.workflow import ExecutionStrategy as ExecutionStrategy
from autobot_shared.workflow import WorkflowPlan as _SharedWorkflowPlan
from autobot_shared.workflow import WorkflowTask
from constants.status_enums import TaskStatus
from orchestration.types import AgentCapability  # single canonical definition (#6192)

# Module-level frozenset for fallback tier checks
FALLBACK_TIERS: FrozenSet[str] = frozenset({"basic", "emergency"})


class AgentTask(WorkflowTask):
    """Workflow task with execution lifecycle methods.

    Inherits every field from ``autobot_shared.workflow.WorkflowTask`` (#6951
    Phase 1b). The methods below were extracted under Issue #372 to reduce
    feature envy in the runner; they live in this subclass — not on the
    canonical type — because they encode an execution-runtime concern that
    the shared shape intentionally avoids.
    """

    def start_execution(self) -> None:
        """Mark task as started (Issue #372)."""
        self.start_time = time.time()
        self.status = TaskStatus.RUNNING.value

    def complete_execution(self, result: Dict[str, Any]) -> None:
        """Mark task as completed with result (Issue #372)."""
        self.end_time = time.time()
        self.status = TaskStatus.COMPLETED.value
        self.outputs = result

    def fail_execution(self, error_msg: str) -> None:
        """Mark task as failed with error (Issue #372)."""
        self.status = TaskStatus.FAILED.value
        self.error = error_msg

    def get_execution_time(self) -> float:
        """Get execution time in seconds (Issue #372)."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    def can_retry(self) -> bool:
        """Check if task can be retried (Issue #372)."""
        return self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        """Increment retry counter (Issue #372)."""
        self.retry_count += 1

    def get_enhanced_inputs(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Get inputs enhanced with context (Issue #372)."""
        return {
            **self.inputs,
            "context": context,
            "task_id": self.task_id,
            "workflow_metadata": self.metadata,
        }

    def to_completed_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Build completed result dict (Issue #372)."""
        return {
            "status": "completed",
            "output": result,
            "execution_time": self.get_execution_time(),
            "agent": self.agent_type,
        }

    def to_failed_result(self, error_msg: str) -> Dict[str, Any]:
        """Build failed result dict (Issue #372)."""
        return {
            "status": "failed",
            "error": error_msg,
            "agent": self.agent_type,
        }


@dataclass
class WorkflowPlan(_SharedWorkflowPlan):
    """Enhanced workflow plan with structured success criteria.

    Inherits every field from ``autobot_shared.workflow.WorkflowPlan`` (#6951
    Phase 1b). ``structured_criteria`` (#3293) lives here, not on the canonical
    shape, because it depends on backend-only ``SuccessCriteria`` semantics for
    partial/full/failed evaluation.
    """

    structured_criteria: List["SuccessCriteria"] = field(default_factory=list)


@dataclass
class WorkflowDependencies:
    """Groups the callable dependencies injected into ExecutionStrategyHandler (#6422).

    Replaces 6 positional Callable params with a single named container, making
    the constructor testable and the dependency surface explicit.
    """

    execute_single_task: Callable
    topological_sort_tasks: Callable
    dependencies_met: Callable
    group_pipeline_stages: Callable
    enhance_task_for_collaboration: Callable
    coordinate_collaboration: Callable


@dataclass
class AgentPerformance:
    """Track agent performance metrics"""

    agent_type: str
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    average_execution_time: float = 0.0
    reliability_score: float = 1.0  # 0-1
    capability_scores: Dict[AgentCapability, float] = field(default_factory=dict)
    last_update: float = field(default_factory=time.time)
