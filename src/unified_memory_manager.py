# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified Memory Manager - Backward Compatibility Wrapper

This file maintains backward compatibility by re-exporting all components
from the modularized src/memory/ package.

ALL NEW CODE SHOULD IMPORT DIRECTLY FROM src.memory:
    from src.memory import UnifiedMemoryManager, TaskStatus, MemoryCategory

This file exists ONLY to support existing imports:
    from src.unified_memory_manager import UnifiedMemoryManager

The actual implementation has been refactored into src/memory/ package:
- src/memory/enums.py - Enumerations (TaskStatus, TaskPriority, etc.)
- src/memory/models.py - Data models (TaskExecutionRecord, MemoryEntry)
- src/memory/protocols.py - Interface definitions
- src/memory/storage/ - Storage implementations
- src/memory/cache.py - LRU caching
- src/memory/monitor.py - Memory monitoring
- src/memory/manager.py - Main UnifiedMemoryManager class
- src/memory/compat.py - Backward compatibility wrappers
"""

# Re-export everything from the modularized package
from src.memory import (
    EnhancedMemoryManager,
    GeneralStorage,
    ICacheManager,
    IGeneralStorage,
    ITaskStorage,
    LongTermMemoryManager,
    LRUCacheManager,
    MemoryCategory,
    MemoryEntry,
    MemoryMonitor,
    StorageStrategy,
    TaskExecutionRecord,
    TaskPriority,
    TaskStatus,
    TaskStorage,
    UnifiedMemoryManager,
    get_enhanced_memory_manager,
    get_long_term_memory_manager,
)

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
