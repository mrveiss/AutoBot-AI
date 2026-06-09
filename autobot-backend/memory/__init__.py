# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unified Memory Manager Package - Modularized architecture

This package consolidates 5 memory manager implementations into a clean,
SOLID-principles-based modular structure.

Package Structure:
- enums.py: Shared enumeration types
- models.py: Data models (TaskExecutionRecord, MemoryEntry)
- protocols.py: Interface definitions (ITaskStorage, IGeneralStorage, ICacheManager)
- storage/: Storage implementations
  - task_storage.py: Task execution history
  - general_storage.py: Category-based memory
- cache.py: LRU caching implementation
- monitor.py: System memory monitoring
- working_memory.py: Redis-backed session-scoped short-term memory
- essential_story.py: Always-loaded compact memory summary for LLM prompts
- agent_diary.py: Per-agent cross-session journal backed by knowledge base
- manager.py: Main UnifiedMemoryManager class (composes all subsystems)
- compat.py: Backward compatibility wrappers

All three memory subsystems (WorkingMemoryService, EssentialStoryGenerator,
AgentDiaryService) are exposed as properties on UnifiedMemoryManager so agents
access them via ``self.memory_manager.working_memory``, etc., without direct
subsystem imports.

For backward compatibility, all exports from the original unified_memory_manager.py
are re-exported here.
"""

# Memory Subsystems (exposed via UnifiedMemoryManager properties)
from .agent_diary import AgentDiaryService

# Cache and Monitor
from .cache import LRUCacheManager

# Backward Compatibility Wrappers
from .compat import (
    EnhancedMemoryManager,
    LongTermMemoryManager,
    get_enhanced_memory_manager,
    get_long_term_memory_manager,
)

# Enums
from .enums import MemoryCategory, StorageStrategy, TaskPriority, TaskStatus
from .essential_story import EssentialStoryGenerator

# Main Manager (composes all subsystems above)
from .manager import UnifiedMemoryManager

# Data Models
from .models import MemoryEntry, TaskExecutionRecord
from .monitor import MemoryMonitor

# Protocols
from .protocols import ICacheManager, IGeneralStorage, ITaskStorage

# Storage Components
from .storage import GeneralStorage, TaskStorage
from .working_memory import WorkingMemoryService

__all__ = [
    # Memory subsystems
    "AgentDiaryService",
    "EssentialStoryGenerator",
    "WorkingMemoryService",
    # Enums
    "TaskStatus",
    "TaskPriority",
    "MemoryCategory",
    "StorageStrategy",
    # Data Models
    "TaskExecutionRecord",
    "MemoryEntry",
    # Protocols
    "ITaskStorage",
    "IGeneralStorage",
    "ICacheManager",
    # Components
    "TaskStorage",
    "GeneralStorage",
    "LRUCacheManager",
    "MemoryMonitor",
    # Main Manager
    "UnifiedMemoryManager",
    # Compatibility Wrappers
    "EnhancedMemoryManager",
    "LongTermMemoryManager",
    # Global Instances
    "get_enhanced_memory_manager",
    "get_long_term_memory_manager",
]
