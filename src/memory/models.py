# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Memory Manager Data Models - Structured data classes
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

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
