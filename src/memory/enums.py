# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Memory Manager Enums - Shared enumeration types
"""

from enum import Enum


class TaskStatus(Enum):
    """Task execution status enumeration"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class TaskPriority(Enum):
    """Task priority levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MemoryCategory(Enum):
    """General purpose memory categories"""

    TASK = "task"
    EXECUTION = "execution"
    STATE = "state"
    CONFIG = "config"
    FACT = "fact"
    CONVERSATION = "conversation"
    CUSTOM = "custom"


class StorageStrategy(Enum):
    """Storage strategies for unified store() method"""

    TASK_EXECUTION = "task_execution"  # Task-centric storage
    GENERAL_MEMORY = "general_memory"  # Category-based storage
    CACHED = "cached"  # LRU cache only


__all__ = [
    "TaskStatus",
    "TaskPriority",
    "MemoryCategory",
    "StorageStrategy",
]
