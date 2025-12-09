# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Memory Manager Data Models - Structured data classes
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from .enums import MemoryCategory, TaskPriority, TaskStatus


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
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    agent_type: Optional[str] = None
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    markdown_references: Optional[List[str]] = None
    parent_task_id: Optional[str] = None
    subtask_ids: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

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
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
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

    id: Optional[int]
    category: Union[MemoryCategory, str]
    content: str
    metadata: Dict[str, Any]
    timestamp: datetime
    reference_path: Optional[str] = None
    embedding: Optional[bytes] = None


__all__ = [
    "TaskExecutionRecord",
    "MemoryEntry",
]
