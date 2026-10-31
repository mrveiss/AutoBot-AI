# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Memory Manager Data Models - Structured data classes
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger

from .enums import MemoryCategory, TaskPriority, TaskStatus

logger = get_logger(__name__)


@dataclass
class TaskExecutionRecord:
    """
    Task-centric memory record (from enhanced_memory_manager)

    Comprehensive task execution tracking with:
    - Lifecycle management (pending → in_progress → completed)
    - Duration tracking
    - Agent attribution
    - Input/output logging
    - Error handling
    - Parent/child relationships
    - Markdown references
    """

    task_id: str
    task_name: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    agent_type: str | None = None
    inputs: Dict[str, Any] | None = None
    outputs: Dict[str, Any] | None = None
    error_message: str | None = None
    retry_count: int = 0
    markdown_references: List[str] | None = None
    parent_task_id: str | None = None
    subtask_ids: List[str] | None = None
    metadata: Dict[str, Any] | None = None

    def elapsed_seconds(self, completed_at: datetime) -> float | None:
        """Seconds from ``started_at`` to *completed_at*, or ``None`` if unknowable.

        #13344: ``MemoryManager.update_task_status`` rejects a negative
        ``duration_seconds``, and that ``ValueError`` escaped through
        ``TaskExecutionTracker.track_task``, which re-raises — so a bookkeeping
        inconsistency failed the caller's *real* work. One observed run reported
        "Contextual decision making failed" for a decision that had succeeded.

        **The cause of ``started_at > completed_at`` is not established.** Every
        production writer stores an aware UTC value and the SQLite round-trip is
        lossless, so neither hypothesis on #13344 is demonstrable from the code;
        a wall-clock step and an untyped ``update_task_status(started_at=...)``
        kwarg both remain possible and neither is provable here.

        What does not depend on the cause: an unknowable duration must not be
        invented, and must not abort the tracked operation. So this returns
        ``None`` — *we do not know* — and logs both instants and the delta, so
        the next occurrence names its own cause. It deliberately does **not**
        clamp to ``0``: a zero is a measurement, and writing one would hide the
        skew behind a plausible number.

        A naive instant meeting an aware one is the same kind of unknowable, and
        is checked *before* the subtraction: ``datetime - datetime`` across that
        boundary raises ``TypeError``, which would abort the tracked operation
        exactly as the ``ValueError`` above did — the fallback below could never
        run. It returns ``None`` rather than assuming a zone for the naive side,
        because picking UTC would invent the very measurement this refuses to
        invent. Normalising at the write boundary is the real repair (#18103).
        """
        if not self.started_at:
            return None
        if (self.started_at.tzinfo is None) is not (completed_at.tzinfo is None):
            self._log_unmeasurable(completed_at, "one instant is timezone-naive and the other aware")
            return None
        duration = (completed_at - self.started_at).total_seconds()
        if duration >= 0:
            return duration
        self._log_unmeasurable(completed_at, f"started_at is AFTER completed_at by {-duration:.3f}s")
        return None

    def _log_unmeasurable(self, completed_at: datetime, reason: str) -> None:
        """Record an unknowable duration, naming both instants (#13344).

        Shared by both unmeasurable cases so their wording cannot drift apart.
        """
        logger.error(
            "Task %s: duration unmeasurable — %s. started_at=%s completed_at=%s. Recording "
            "duration_seconds=None rather than a clamped value; the tracked operation is "
            "unaffected (#13344).",
            self.task_id,
            reason,
            self.started_at.isoformat() if self.started_at else None,
            completed_at.isoformat(),
        )

    def to_db_tuple(self) -> Tuple:
        """Convert to tuple for SQLite insertion (Issue #372 - reduces feature envy).

        Returns:
            Tuple with all fields formatted for task_execution_history table insertion.
        """
        return (
            self.task_id,
            self.task_name,
            self.description,
            self.status.value,
            self.priority.value,
            self.created_at,
            self.started_at,
            self.completed_at,
            self.duration_seconds,
            self.agent_type,
            json.dumps(self.inputs) if self.inputs else None,
            json.dumps(self.outputs) if self.outputs else None,
            self.error_message,
            self.retry_count,
            json.dumps(self.markdown_references) if self.markdown_references else None,
            self.parent_task_id,
            json.dumps(self.subtask_ids) if self.subtask_ids else None,
            json.dumps(self.metadata) if self.metadata else None,
        )

    def to_response_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response (Issue #372 - reduces feature envy).

        Returns:
            Dictionary with all fields formatted for JSON serialization.
        """
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
            "duration_seconds": self.duration_seconds,
            "agent_type": self.agent_type,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "parent_task_id": self.parent_task_id,
            "subtask_ids": self.subtask_ids,
            "markdown_references": self.markdown_references,
            "metadata": self.metadata,
        }


@dataclass
class MemoryEntry:
    """
    General purpose memory entry (from memory_manager)

    Category-based memory storage with:
    - Flexible categorization
    - Metadata support
    - Optional embedding storage
    - Reference path tracking
    """

    id: int | None
    category: MemoryCategory | str
    content: str
    metadata: Dict[str, Any]
    timestamp: datetime
    reference_path: str | None = None
    embedding: bytes | None = None
    # #13688: owner scope as a first-class field, never buried in `metadata`.
    # Defaulted so existing keyword construction stays valid, but GeneralStorage
    # rejects a write without it — the write path cannot silently go unscoped.
    user_id: str | None = None


__all__ = [
    "TaskExecutionRecord",
    "MemoryEntry",
]
