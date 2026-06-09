# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Subagent Task Definition (#4348)

Defines task data structures for subagent spawning and execution:
- SubagentTask: Individual task for a spawned subagent
- SubagentContext: Shared context passed to subagents
- TaskResult: Result from completed subagent execution
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List
from uuid import uuid4

from autobot_shared.status_enums import TaskPriority  # #7504 consolidation
from autobot_shared.status_enums import TaskStatus  # #6973 consolidation


@dataclass
class SubagentTask:
    """Definition of a task for a spawned subagent."""

    task_id: str = field(default_factory=lambda: str(uuid4()))
    goal: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 300
    priority: TaskPriority = TaskPriority.NORMAL
    parent_task_id: str | None = None
    depth: int = 0  # Recursion depth (max 2)
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "context": self.context,
            "constraints": self.constraints,
            "timeout_seconds": self.timeout_seconds,
            "priority": self.priority.value,
            "parent_task_id": self.parent_task_id,
            "depth": self.depth,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubagentTask":
        """Create from dictionary."""
        return cls(
            task_id=data.get("task_id", str(uuid4())),
            goal=data.get("goal", ""),
            context=data.get("context", {}),
            constraints=data.get("constraints", {}),
            timeout_seconds=data.get("timeout_seconds", 300),
            priority=TaskPriority(data.get("priority", "normal")),
            parent_task_id=data.get("parent_task_id"),
            depth=data.get("depth", 0),
            created_at=data.get("created_at", time.time()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class TaskResult:
    """Result from a completed subagent task."""

    task_id: str
    status: TaskStatus
    output: Any = None
    error: str | None = None
    duration_seconds: float = 0.0
    tokens_used: int | None = None
    completed_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "tokens_used": self.tokens_used,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        """Create from dictionary."""
        return cls(
            task_id=data.get("task_id", ""),
            status=TaskStatus(data.get("status", "pending")),
            output=data.get("output"),
            error=data.get("error"),
            duration_seconds=data.get("duration_seconds", 0.0),
            tokens_used=data.get("tokens_used"),
            completed_at=data.get("completed_at", time.time()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ConflictResolution:
    """Resolution of conflicts between subagent outputs."""

    conflict_id: str = field(default_factory=lambda: str(uuid4()))
    task_ids: List[str] = field(default_factory=list)
    resolution_strategy: str = "consensus"  # consensus, majority, priority, manual
    resolved_output: Any = None
    confidence: float = 0.0
    resolved_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "conflict_id": self.conflict_id,
            "task_ids": self.task_ids,
            "resolution_strategy": self.resolution_strategy,
            "resolved_output": self.resolved_output,
            "confidence": self.confidence,
            "resolved_at": self.resolved_at,
            "metadata": self.metadata,
        }
