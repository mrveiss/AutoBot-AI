# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Memory Manager Enums - Shared enumeration types

Issue #670: Re-exports from centralized src.constants.status_enums for backward compatibility.
New code should import directly from constants.status_enums.
"""

# Re-export from centralized location for backward compatibility
from enum import Enum

from backend.constants.status_enums import Priority as TaskPriority
from backend.constants.status_enums import TaskStatus


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
