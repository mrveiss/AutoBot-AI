# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Orchestration Types Module

Issue #381: Extracted from enhanced_multi_agent_orchestrator.py god class refactoring.
Contains enums and dataclasses for the enhanced orchestration system.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set

from backend.constants.status_enums import TaskStatus
from backend.constants.threshold_constants import RetryConfig, TimingConstants

# Module-level frozenset for fallback tier checks
FALLBACK_TIERS: FrozenSet[str] = frozenset({"basic", "emergency"})


class AgentCapability(Enum):
    """Core agent capabilities"""

    RESEARCH = "research"
    ANALYSIS = "analysis"
    EXECUTION = "execution"
    MONITORING = "monitoring"
    SYNTHESIS = "synthesis"
    VALIDATION = "validation"
    OPTIMIZATION = "optimization"
    SECURITY = "security"


class ExecutionStrategy(Enum):
    """Task execution strategies"""

    SEQUENTIAL = "sequential"  # One after another
    PARALLEL = "parallel"  # All at once
    PIPELINE = "pipeline"  # Output feeds next input
    COLLABORATIVE = "collaborative"  # Agents work together
    ADAPTIVE = "adaptive"  # Strategy changes based on progress


@dataclass
class AgentTask:
    """Enhanced task definition for agents"""

    task_id: str
    agent_type: str
    action: str
    inputs: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    priority: int = 5  # 1-10, higher is more important
    timeout: float = float(TimingConstants.STANDARD_TIMEOUT)
    retry_count: int = 0
    max_retries: int = RetryConfig.DEFAULT_RETRIES
    capabilities_required: Set[AgentCapability] = field(default_factory=set)
    outputs: Optional[Dict[str, Any]] = None
    status: str = TaskStatus.PENDING.value  # Issue #670: Use centralized enum
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def start_execution(self) -> None:
        """Mark task as started (Issue #372 - reduces feature envy)."""
        self.start_time = time.time()
        self.status = TaskStatus.RUNNING.value

    def complete_execution(self, result: Dict[str, Any]) -> None:
        """Mark task as completed with result (Issue #372 - reduces feature envy)."""
        self.end_time = time.time()
        self.status = TaskStatus.COMPLETED.value
        self.outputs = result

    def fail_execution(self, error_msg: str) -> None:
        """Mark task as failed with error (Issue #372 - reduces feature envy)."""
        self.status = TaskStatus.FAILED.value
        self.error = error_msg

    def get_execution_time(self) -> float:
        """Get execution time in seconds (Issue #372 - reduces feature envy)."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    def can_retry(self) -> bool:
        """Check if task can be retried (Issue #372 - reduces feature envy)."""
        return self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        """Increment retry counter (Issue #372 - reduces feature envy)."""
        self.retry_count += 1

    def get_enhanced_inputs(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Get inputs enhanced with context (Issue #372 - reduces feature envy)."""
        return {
            **self.inputs,
            "context": context,
            "task_id": self.task_id,
            "workflow_metadata": self.metadata,
        }

    def to_completed_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Build completed result dict (Issue #372 - reduces feature envy)."""
        return {
            "status": "completed",
            "output": result,
            "execution_time": self.get_execution_time(),
            "agent": self.agent_type,
        }

    def to_failed_result(self, error_msg: str) -> Dict[str, Any]:
        """Build failed result dict (Issue #372 - reduces feature envy)."""
        return {
            "status": "failed",
            "error": error_msg,
            "agent": self.agent_type,
        }


@dataclass
class WorkflowPlan:
    """Enhanced workflow execution plan"""

    plan_id: str
    goal: str
    strategy: ExecutionStrategy
    tasks: List[AgentTask]
    dependencies_graph: Dict[str, List[str]]  # task_id -> [dependency_ids]
    estimated_duration: float
    resource_requirements: Dict[str, Any]
    success_criteria: List[str]
    fallback_plans: List["WorkflowPlan"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


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
