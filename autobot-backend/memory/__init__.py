# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
- manager.py: Main UnifiedMemoryManager class
- compat.py: Backward compatibility wrappers

For backward compatibility, all exports from the original unified_memory_manager.py
are re-exported here.
"""

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

# Main Manager
from .manager import UnifiedMemoryManager

# Data Models
from .models import MemoryEntry, TaskExecutionRecord
from .monitor import MemoryMonitor

# Protocols
from .protocols import ICacheManager, IGeneralStorage, ITaskStorage

# Storage Components
from .storage import GeneralStorage, TaskStorage

__all__ = [
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
