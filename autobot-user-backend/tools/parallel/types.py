# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Parallel Execution Type Definitions

Data structures for tool calls and dependency tracking.
"""

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

from src.constants.status_enums import TaskStatus


class DependencyType(Enum):
    """Types of dependencies between tool calls"""

    NONE = auto()  # No dependency, can run in parallel
    DATA = auto()  # Output of A is input to B
    RESOURCE = auto()  # Both access same resource (file, connection)
    ORDER = auto()  # Must run in specific order (create → use)
    TRANSACTIONAL = auto()  # Must complete together or rollback


@dataclass
class ToolCall:
    """Representation of a tool call for execution"""

    # Identity
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = ""
    arguments: dict = field(default_factory=dict)

    # Scheduling
    priority: int = 0  # Higher = execute first

    # Dependency tracking
    depends_on: list[str] = field(default_factory=list)  # Call IDs
    dependency_types: dict[str, DependencyType] = field(default_factory=dict)

    # Execution state - Issue #670: Use centralized enum
    status: str = TaskStatus.PENDING.value
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0

    # Parallel group
    parallel_group_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "priority": self.priority,
            "depends_on": self.depends_on,
            "dependency_types": {k: v.name for k, v in self.dependency_types.items()},
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "parallel_group_id": self.parallel_group_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolCall":
        return cls(
            call_id=data.get("call_id", str(uuid.uuid4())),
            tool_name=data.get("tool_name", ""),
            arguments=data.get("arguments", {}),
            priority=data.get("priority", 0),
            depends_on=data.get("depends_on", []),
            dependency_types={
                k: DependencyType[v]
                for k, v in data.get("dependency_types", {}).items()
            },
            status=data.get("status", TaskStatus.PENDING.value),
            result=data.get("result"),
            error=data.get("error"),
            execution_time_ms=data.get("execution_time_ms", 0.0),
            parallel_group_id=data.get("parallel_group_id"),
        )

    def __repr__(self) -> str:
        return f"ToolCall({self.tool_name}, status={self.status})"


@dataclass
class ExecutionMetrics:
    """Metrics for parallel execution analysis"""

    total_calls: int = 0
    parallel_groups: int = 0
    sequential_calls: int = 0  # Calls that couldn't be parallelized

    total_time_ms: float = 0.0
    sequential_time_ms: float = 0.0  # Time if run sequentially
    parallel_time_ms: float = 0.0  # Actual parallel time

    speedup_factor: float = 1.0  # sequential_time / parallel_time

    def calculate_speedup(self) -> float:
        """Calculate speedup from parallelization"""
        if self.parallel_time_ms > 0:
            self.speedup_factor = self.sequential_time_ms / self.parallel_time_ms
        return self.speedup_factor

    def to_dict(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "parallel_groups": self.parallel_groups,
            "sequential_calls": self.sequential_calls,
            "total_time_ms": self.total_time_ms,
            "sequential_time_ms": self.sequential_time_ms,
            "parallel_time_ms": self.parallel_time_ms,
            "speedup_factor": self.speedup_factor,
        }
