# Phase 5: Memory Managers Consolidation Audit

**Date**: 2025-11-11
**Status**: 📋 ANALYSIS PHASE
**Priority**: High (largest consolidation opportunity - 2,831 lines)

---

## Executive Summary

Found **5 memory manager implementations** with **2,831 total lines** across **30 files**:

| File | Lines | Usage | Type | Status |
|------|-------|-------|------|--------|
| `src/enhanced_memory_manager.py` | 664 | 7 files | Task execution history (sync) | ✅ DOMINANT |
| `src/enhanced_memory_manager_async.py` | 572 | Unknown | Task execution history (async) | Duplicate of sync |
| `src/memory_manager.py` | 850 | 2 files | General purpose memory (sync) | Migrate to enhanced |
| `src/memory_manager_async.py` | 517 | Unknown | General purpose memory (async) | Duplicate of sync |
| `src/utils/optimized_memory_manager.py` | 228 | **0 files** | LRU caching & monitoring | **UNUSED - Remove or integrate** |

**Net Impact**: 5 files → 1 unified manager, ~1,500 lines saved

---

## Current State Analysis

### 1. enhanced_memory_manager.py (664 lines) ✅ DOMINANT

**Purpose**: Task execution history and logging for AutoBot Phase 7

**Used by** (7 files):
- `src/voice_processing_system.py`
- `src/context_aware_decision_system.py`
- `src/markdown_reference_system.py`
- `src/computer_vision_system.py`
- `src/takeover_manager.py`
- `src/modern_ai_integration.py`
- `backend/api/enhanced_memory.py`

**Features**:
- SQLite backend with database pooling
- Task-centric data model (TaskExecutionRecord)
- Enums: TaskStatus, TaskPriority
- Comprehensive task tracking:
  - Task lifecycle (created → started → completed)
  - Duration tracking
  - Agent type attribution
  - Inputs/outputs logging
  - Error tracking
  - Retry count
  - Markdown references
  - Parent/subtask relationships
- Schema: `task_execution_history` table

**Key Classes**:
```python
class TaskStatus(Enum):
    PENDING, IN_PROGRESS, COMPLETED, FAILED, CANCELLED, RETRYING

class TaskPriority(Enum):
    LOW, MEDIUM, HIGH, CRITICAL

@dataclass
class TaskExecutionRecord:
    task_id, task_name, description, status, priority
    created_at, started_at, completed_at, duration_seconds
    agent_type, inputs, outputs, error_message, retry_count
    markdown_references, parent_task_id, subtask_ids, metadata
```

**Methods**:
- `log_task_execution()` - Record task execution
- `update_task_status()` - Update task status
- `get_task_history()` - Query task history
- `get_task_statistics()` - Task execution stats

---

### 2. memory_manager.py (850 lines)

**Purpose**: General purpose long-term memory with SQLite backend

**Used by** (2 files):
- `src/orchestrator.py`
- `analysis/refactoring/test_memory_path_utils.py`

**Features**:
- SQLite backend (agent_memory.db)
- Category-based data model (MemoryEntry)
- Categories: task, execution, state, config, fact, conversation
- Embedding storage support (optional vector storage)
- Retention policy (90 days default)
- Configuration integration
- Schema: `memory_entries` table

**Key Classes**:
```python
@dataclass
class MemoryEntry:
    id, category, content, metadata, timestamp
    reference_path, embedding  # Optional

class LongTermMemoryManager:
    def store_memory(category, content, metadata, embedding)
    def retrieve_memories(category, filters, limit)
    def search_by_metadata(metadata_query)
    def cleanup_old_memories()
```

**Differences from Enhanced**:
- More general purpose (not task-specific)
- Embedding support built-in
- Category-based organization vs task-centric
- Different schema and API

---

### 3. optimized_memory_manager.py (228 lines) ❌ UNUSED

**Purpose**: LRU caching and memory pressure monitoring

**Used by**: **0 files** (COMPLETELY UNUSED!)

**Features**:
- LRU cache with OrderedDict
- Memory monitoring with psutil
- Adaptive cleanup based on memory pressure
- Cache statistics (hits/misses/hit rate)
- Background monitoring task (60s interval)
- Configurable thresholds (80% memory usage trigger)

**Key Classes**:
```python
class OptimizedMemoryManager:
    def create_lru_cache(name, max_size=1000)
    def get_from_cache(cache_name, key)
    def put_in_cache(cache_name, key, value)
    def get_cache_stats()
    def adaptive_memory_cleanup()
    def start_memory_monitor()  # Background task
    def get_memory_usage()
    def cleanup_specific_cache(name, percentage)
```

**Helper Functions**:
```python
get_optimized_memory_manager()  # Global singleton
create_managed_cache(name, max_size)
cache_get(cache_name, key)
cache_put(cache_name, key, value)
```

**Analysis**: This is actually a **caching utility** (like advanced_cache_manager), not a "memory manager" for task/history storage. Should be:
1. **Removed** if truly unused, OR
2. **Integrated** into advanced_cache_manager if functionality is valuable

---

### 4. Async Versions (1,089 lines combined)

**memory_manager_async.py** (517 lines):
- Async version of memory_manager.py
- Uses aiosqlite instead of sqlite3
- Same API, different implementation

**enhanced_memory_manager_async.py** (572 lines):
- Async version of enhanced_memory_manager.py
- Uses aiosqlite instead of sqlite3
- Same API, different implementation

**Problem**: Maintaining separate sync/async files = code duplication

---

## Feature Comparison Matrix

| Feature | Enhanced | Memory | Optimized |
|---------|----------|--------|-----------|
| **Task Tracking** | ✅ (primary focus) | ✅ (category: task) | ❌ |
| **Execution History** | ✅ | ✅ (category: execution) | ❌ |
| **Agent State** | ⚠️ (via metadata) | ✅ (category: state) | ❌ |
| **Config Changes** | ⚠️ (via metadata) | ✅ (category: config) | ❌ |
| **Facts/Knowledge** | ⚠️ (markdown refs) | ✅ (category: fact) | ❌ |
| **Conversations** | ❌ | ✅ (category: conversation) | ❌ |
| **Embeddings** | ❌ | ✅ | ❌ |
| **LRU Caching** | ❌ | ❌ | ✅ |
| **Memory Monitoring** | ❌ | ❌ | ✅ |
| **Async Support** | ⚠️ (separate file) | ⚠️ (separate file) | ✅ (built-in) |
| **Database Backend** | SQLite | SQLite | In-memory |
| **Schema** | Task-centric | Category-based | N/A |
| **Retention Policy** | ❌ | ✅ (90 days) | ✅ (adaptive) |
| **Parent/Child Tasks** | ✅ | ❌ | ❌ |
| **Markdown References** | ✅ | ⚠️ (reference_path) | ❌ |
| **Statistics** | ✅ (task stats) | ⚠️ (basic counts) | ✅ (cache stats) |

---

## Consolidation Strategy

### ✅ RECOMMENDED: Unified Memory Manager

**Approach**: Extend `enhanced_memory_manager.py` with features from others

**Rationale**:
1. Most used (7 files vs 2 files vs 0 files)
2. Task-centric model fits AutoBot workflow
3. Already has comprehensive task tracking
4. Can add category-based storage as extension

**Design Principles** (Code Reusability Focus):

### 1. **Single Responsibility Principle**
- Core memory storage: SQLite operations
- LRU caching: Separate utility class
- Memory monitoring: Separate utility class
- Async/sync: Single implementation with async/await

### 2. **Interface Segregation**
```python
# Task-specific interface
class ITaskMemory:
    async def log_task(record: TaskExecutionRecord)
    async def get_task_history(filters)
    async def update_task_status(task_id, status)

# General purpose interface
class IGeneralMemory:
    async def store(category, content, metadata)
    async def retrieve(category, filters)
    async def search(query)

# Caching interface
class IMemoryCache:
    def get(key)
    def put(key, value)
    def evict(strategy)
```

### 3. **Dependency Injection**
```python
class UnifiedMemoryManager:
    def __init__(
        self,
        db_path: str,
        cache_manager: Optional[ICacheManager] = None,
        monitor: Optional[IMemoryMonitor] = None
    ):
        self.db = DatabaseAdapter(db_path)
        self.cache = cache_manager or LRUCacheManager()
        self.monitor = monitor or MemoryMonitor()
```

### 4. **Strategy Pattern for Storage**
```python
class StorageStrategy(Enum):
    TASK_EXECUTION = "task"
    GENERAL_MEMORY = "general"
    CACHED = "cached"

class UnifiedMemoryManager:
    async def store(
        self,
        data: Any,
        strategy: StorageStrategy = StorageStrategy.TASK_EXECUTION
    ):
        if strategy == StorageStrategy.TASK_EXECUTION:
            return await self._store_task(data)
        elif strategy == StorageStrategy.GENERAL_MEMORY:
            return await self._store_memory_entry(data)
        elif strategy == StorageStrategy.CACHED:
            return self.cache.put(data)
```

### 5. **Async First Design**
```python
# All public methods async
# Sync wrappers use asyncio.run()

class UnifiedMemoryManager:
    async def log_task(self, record):
        """Async implementation"""
        ...

    def log_task_sync(self, record):
        """Sync wrapper for backward compatibility"""
        return asyncio.run(self.log_task(record))
```

---

## Unified API Design (Reusable Code Focus)

### Core Classes

```python
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol
from datetime import datetime

# ========== Enums ==========
class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"

class TaskPriority(Enum):
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
    """Storage strategies for code reusability"""
    TASK_EXECUTION = "task_execution"  # Task-centric storage
    GENERAL_MEMORY = "general_memory"  # Category-based storage
    CACHED = "cached"                  # LRU cache only

# ========== Data Models ==========
@dataclass
class TaskExecutionRecord:
    """Task-centric memory record (from enhanced_memory_manager)"""
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
    """General purpose memory entry (from memory_manager)"""
    id: Optional[int]
    category: MemoryCategory
    content: str
    metadata: Dict[str, Any]
    timestamp: datetime
    reference_path: Optional[str] = None
    embedding: Optional[bytes] = None

# ========== Protocols (Interfaces) ==========
class ITaskStorage(Protocol):
    """Interface for task-specific storage"""
    async def log_task(self, record: TaskExecutionRecord) -> str: ...
    async def update_task(self, task_id: str, **updates) -> bool: ...
    async def get_task(self, task_id: str) -> Optional[TaskExecutionRecord]: ...
    async def get_task_history(self, filters: Dict) -> List[TaskExecutionRecord]: ...

class IGeneralStorage(Protocol):
    """Interface for general purpose storage"""
    async def store(self, entry: MemoryEntry) -> int: ...
    async def retrieve(self, category: MemoryCategory, filters: Dict) -> List[MemoryEntry]: ...
    async def search(self, query: str) -> List[MemoryEntry]: ...

class ICacheManager(Protocol):
    """Interface for caching layer"""
    def get(self, key: str) -> Optional[Any]: ...
    def put(self, key: str, value: Any) -> None: ...
    def evict(self, count: int) -> int: ...
    def stats(self) -> Dict: ...

# ========== Main Unified Class ==========
class UnifiedMemoryManager:
    """
    Unified Memory Manager for AutoBot - P5 Consolidation

    Combines features from:
    - enhanced_memory_manager.py (task execution history)
    - memory_manager.py (general purpose storage)
    - optimized_memory_manager.py (LRU caching & monitoring)

    Design Principles:
    - Single Responsibility: Each component has one job
    - Interface Segregation: Multiple interfaces for different use cases
    - Dependency Injection: Components can be replaced
    - Strategy Pattern: Different storage strategies
    - Async First: All operations async, sync wrappers available
    """

    def __init__(
        self,
        db_path: str = "data/unified_memory.db",
        enable_cache: bool = True,
        enable_monitoring: bool = False,
        cache_manager: Optional[ICacheManager] = None
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Core components
        self._task_storage = TaskStorage(self.db_path)
        self._general_storage = GeneralStorage(self.db_path)

        # Optional components (dependency injection)
        self._cache = cache_manager or (LRUCacheManager() if enable_cache else None)
        self._monitor = MemoryMonitor() if enable_monitoring else None

        # Initialize database
        asyncio.run(self._init_database())

    # ===== Task-Specific API (from enhanced_memory_manager) =====
    async def log_task(self, record: TaskExecutionRecord) -> str:
        """Log task execution (async)"""
        return await self._task_storage.log_task(record)

    def log_task_sync(self, record: TaskExecutionRecord) -> str:
        """Log task execution (sync wrapper for backward compatibility)"""
        return asyncio.run(self.log_task(record))

    async def update_task_status(
        self, task_id: str, status: TaskStatus, **kwargs
    ) -> bool:
        """Update task status and optional fields"""
        return await self._task_storage.update_task(
            task_id, status=status, **kwargs
        )

    async def get_task_history(
        self,
        agent_type: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[TaskExecutionRecord]:
        """Query task execution history with filters"""
        filters = {
            "agent_type": agent_type,
            "status": status,
            "priority": priority,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit
        }
        return await self._task_storage.get_task_history(filters)

    # ===== General Purpose API (from memory_manager) =====
    async def store_memory(
        self,
        category: MemoryCategory,
        content: str,
        metadata: Optional[Dict] = None,
        reference_path: Optional[str] = None,
        embedding: Optional[bytes] = None
    ) -> int:
        """Store general purpose memory entry"""
        entry = MemoryEntry(
            id=None,
            category=category,
            content=content,
            metadata=metadata or {},
            timestamp=datetime.now(),
            reference_path=reference_path,
            embedding=embedding
        )
        return await self._general_storage.store(entry)

    async def retrieve_memories(
        self,
        category: MemoryCategory,
        limit: int = 100,
        **filters
    ) -> List[MemoryEntry]:
        """Retrieve memories by category and filters"""
        return await self._general_storage.retrieve(category, filters)

    # ===== Caching API (from optimized_memory_manager) =====
    def cache_get(self, key: str) -> Optional[Any]:
        """Get item from cache"""
        if not self._cache:
            return None
        return self._cache.get(key)

    def cache_put(self, key: str, value: Any) -> None:
        """Put item in cache"""
        if self._cache:
            self._cache.put(key, value)

    def cache_stats(self) -> Dict:
        """Get cache statistics"""
        if not self._cache:
            return {"enabled": False}
        return self._cache.stats()

    # ===== Unified Storage API (Strategy Pattern) =====
    async def store(
        self,
        data: Union[TaskExecutionRecord, MemoryEntry, Any],
        strategy: StorageStrategy = StorageStrategy.TASK_EXECUTION
    ) -> Union[str, int]:
        """
        Unified storage interface with strategy pattern

        This method demonstrates code reusability by providing
        a single interface for different storage strategies.
        """
        if strategy == StorageStrategy.TASK_EXECUTION:
            if not isinstance(data, TaskExecutionRecord):
                raise TypeError("TASK_EXECUTION requires TaskExecutionRecord")
            return await self.log_task(data)

        elif strategy == StorageStrategy.GENERAL_MEMORY:
            if not isinstance(data, MemoryEntry):
                raise TypeError("GENERAL_MEMORY requires MemoryEntry")
            return await self.store_memory(
                data.category, data.content, data.metadata,
                data.reference_path, data.embedding
            )

        elif strategy == StorageStrategy.CACHED:
            # Generate cache key
            key = hashlib.sha256(str(data).encode()).hexdigest()[:16]
            self.cache_put(key, data)
            return key

        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    # ===== Statistics & Monitoring =====
    async def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics"""
        return {
            "task_storage": await self._task_storage.get_stats(),
            "general_storage": await self._general_storage.get_stats(),
            "cache": self.cache_stats(),
            "system_memory": self._monitor.get_usage() if self._monitor else None
        }
```

---

## Migration Plan

### Files to Migrate (2 total)

**From memory_manager.py** (2 files):
1. `src/orchestrator.py` - Migrate to unified API
2. `analysis/refactoring/test_memory_path_utils.py` - Update imports

**Migration Path**:
```python
# OLD (memory_manager):
from src.memory_manager import LongTermMemoryManager, MemoryEntry

manager = LongTermMemoryManager()
await manager.store_memory("task", content, metadata)

# NEW (unified_memory_manager):
from src.unified_memory_manager import (
    UnifiedMemoryManager,
    MemoryEntry,
    MemoryCategory
)

manager = UnifiedMemoryManager()
await manager.store_memory(MemoryCategory.TASK, content, metadata)
# OR use general API:
entry = MemoryEntry(...)
await manager.store(entry, strategy=StorageStrategy.GENERAL_MEMORY)
```

**Already Using Enhanced** (7 files - no changes needed):
- All 7 files continue using same API (backward compatible)

---

## Backward Compatibility Strategy

### 1. Compatibility Wrappers

```python
# In unified_memory_manager.py

# ===== Enhanced Memory Manager Compatibility =====
class EnhancedMemoryManager(UnifiedMemoryManager):
    """
    Backward compatibility wrapper for enhanced_memory_manager.py
    All existing code continues to work without changes.
    """
    def __init__(self, db_path: str = "data/enhanced_memory.db"):
        super().__init__(db_path)

    # All existing methods map directly to unified API
    # (no code changes needed)

# ===== Long-Term Memory Manager Compatibility =====
class LongTermMemoryManager:
    """
    Backward compatibility wrapper for memory_manager.py
    """
    def __init__(self, config_path: Optional[str] = None):
        self._unified = UnifiedMemoryManager(
            db_path="data/agent_memory.db"
        )

    async def store_memory(
        self,
        category: str,
        content: str,
        metadata: Optional[Dict] = None,
        embedding: Optional[bytes] = None
    ):
        """Map old API to new unified API"""
        cat = MemoryCategory[category.upper()]
        return await self._unified.store_memory(
            cat, content, metadata, embedding=embedding
        )

    # Map other methods...

# ===== Optimized Memory Manager Compatibility =====
# (Actually just remove - it's unused!)
```

### 2. Global Instances

```python
# For drop-in replacement

# Enhanced Memory Manager (used by 7 files)
enhanced_memory = EnhancedMemoryManager()

# Long-Term Memory Manager (used by 2 files)
long_term_memory = LongTermMemoryManager()

# Make them importable from original locations
# src/enhanced_memory_manager.py:
from src.unified_memory_manager import EnhancedMemoryManager, TaskStatus, TaskPriority

# src/memory_manager.py:
from src.unified_memory_manager import LongTermMemoryManager, MemoryEntry
```

---

## Testing Strategy

### Test Suite (10+ tests)

```python
# tests/test_memory_consolidation_p5.py

async def test_task_execution_logging():
    """Test task execution history (enhanced_memory features)"""
    manager = UnifiedMemoryManager()
    record = TaskExecutionRecord(
        task_id="test-001",
        task_name="Test Task",
        description="Testing",
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
        created_at=datetime.now()
    )
    task_id = await manager.log_task(record)
    assert task_id == "test-001"

async def test_general_memory_storage():
    """Test general purpose memory (memory_manager features)"""
    manager = UnifiedMemoryManager()
    entry_id = await manager.store_memory(
        MemoryCategory.FACT,
        "AutoBot is awesome",
        metadata={"source": "test"}
    )
    assert entry_id > 0

    memories = await manager.retrieve_memories(MemoryCategory.FACT)
    assert len(memories) > 0

def test_lru_caching():
    """Test LRU cache (optimized_memory features)"""
    manager = UnifiedMemoryManager(enable_cache=True)
    manager.cache_put("key1", "value1")
    assert manager.cache_get("key1") == "value1"

    stats = manager.cache_stats()
    assert stats["enabled"] == True

async def test_strategy_pattern():
    """Test unified storage with different strategies"""
    manager = UnifiedMemoryManager()

    # Task strategy
    task = TaskExecutionRecord(...)
    task_id = await manager.store(task, StorageStrategy.TASK_EXECUTION)

    # Memory strategy
    entry = MemoryEntry(...)
    entry_id = await manager.store(entry, StorageStrategy.GENERAL_MEMORY)

    # Cache strategy
    cache_key = await manager.store({"data": "test"}, StorageStrategy.CACHED)

async def test_backward_compatibility_enhanced():
    """Test EnhancedMemoryManager compatibility wrapper"""
    # Old code should work exactly as before
    from src.unified_memory_manager import EnhancedMemoryManager, TaskStatus

    manager = EnhancedMemoryManager()
    # Use old API...

async def test_backward_compatibility_longterm():
    """Test LongTermMemoryManager compatibility wrapper"""
    from src.unified_memory_manager import LongTermMemoryManager

    manager = LongTermMemoryManager()
    await manager.store_memory("task", "content", {})

def test_sync_wrappers():
    """Test sync wrappers for backward compatibility"""
    manager = UnifiedMemoryManager()

    # Sync version (uses asyncio.run internally)
    record = TaskExecutionRecord(...)
    task_id = manager.log_task_sync(record)
    assert task_id is not None

async def test_statistics():
    """Test comprehensive statistics"""
    manager = UnifiedMemoryManager()
    stats = await manager.get_statistics()

    assert "task_storage" in stats
    assert "general_storage" in stats
    assert "cache" in stats

def test_dependency_injection():
    """Test custom cache manager injection"""
    class CustomCache:
        def get(self, key): return None
        def put(self, key, value): pass
        def stats(self): return {"custom": True}

    manager = UnifiedMemoryManager(
        cache_manager=CustomCache()
    )
    assert manager.cache_stats()["custom"] == True

async def test_all_features_preserved():
    """Test 10: Verify all features from 3 managers preserved"""
    manager = UnifiedMemoryManager(enable_cache=True, enable_monitoring=True)

    # Enhanced features
    assert hasattr(manager, 'log_task')
    assert hasattr(manager, 'update_task_status')
    assert hasattr(manager, 'get_task_history')

    # Memory features
    assert hasattr(manager, 'store_memory')
    assert hasattr(manager, 'retrieve_memories')

    # Optimized features
    assert hasattr(manager, 'cache_get')
    assert hasattr(manager, 'cache_put')
    assert hasattr(manager, 'cache_stats')

    # Unified features
    assert hasattr(manager, 'store')  # Strategy pattern
    assert hasattr(manager, 'get_statistics')
```

---

## Code Reusability Principles Applied

### 1. **Single Responsibility Principle** ✅
- TaskStorage: Handles task-specific operations
- GeneralStorage: Handles general memory operations
- LRUCacheManager: Handles caching only
- MemoryMonitor: Handles monitoring only

### 2. **Interface Segregation** ✅
- ITaskStorage: Task-specific interface
- IGeneralStorage: General memory interface
- ICacheManager: Caching interface
- Clients only depend on interfaces they use

### 3. **Dependency Injection** ✅
```python
UnifiedMemoryManager(
    cache_manager=CustomCache(),  # Inject custom implementation
    monitor=CustomMonitor()        # Inject custom monitor
)
```

### 4. **Strategy Pattern** ✅
```python
await manager.store(data, strategy=StorageStrategy.TASK_EXECUTION)
await manager.store(data, strategy=StorageStrategy.GENERAL_MEMORY)
await manager.store(data, strategy=StorageStrategy.CACHED)
```

### 5. **Composition Over Inheritance** ✅
- UnifiedMemoryManager composes TaskStorage + GeneralStorage + Cache
- Not using deep inheritance hierarchies

### 6. **Don't Repeat Yourself (DRY)** ✅
- No separate async/sync files (single async implementation)
- Sync wrappers use asyncio.run() - no code duplication

### 7. **Open/Closed Principle** ✅
- Open for extension: Add new storage strategies
- Closed for modification: Core logic unchanged

### 8. **Backward Compatibility** ✅
- Compatibility wrappers for existing code
- No breaking changes required

---

## Estimated Impact

**Before**:
```
src/enhanced_memory_manager.py:        664 lines
src/enhanced_memory_manager_async.py:  572 lines
src/memory_manager.py:                 850 lines
src/memory_manager_async.py:           517 lines
src/utils/optimized_memory_manager.py: 228 lines
--------------------------------------------------
Total:                                2,831 lines
Files to maintain:                    5
```

**After**:
```
src/unified_memory_manager.py:        ~1,300 lines
(includes all features + backward compatibility wrappers)
--------------------------------------------------
Total:                                ~1,300 lines
Files to maintain:                    1
Net reduction:                        ~1,531 lines (-54%)
```

---

## Next Steps

### Phase 1: Implementation (3-4 hours)
1. ✅ Analysis complete (this document)
2. Create `src/unified_memory_manager.py`
3. Implement core UnifiedMemoryManager class
4. Implement TaskStorage, GeneralStorage components
5. Implement LRUCacheManager (from optimized)
6. Create backward compatibility wrappers

### Phase 2: Migration (1 hour)
1. Update 2 files using memory_manager
2. Add deprecation warnings to old files
3. Update imports in all files

### Phase 3: Testing (1-2 hours)
1. Write 10+ comprehensive tests
2. Verify all 9 files still work (7 enhanced + 2 memory)
3. Backend startup verification

### Phase 4: Review & Commit (1 hour)
1. Code review with code-reviewer agent (mandatory)
2. Create P5 archive
3. Update centralization summary
4. Commit with detailed message

**Total Estimated Time**: 6-8 hours

---

## Decision Required

**Proceed with P5 Memory Managers Consolidation?**

✅ **RECOMMENDED** - Largest consolidation (1,531 lines saved), lowest risk (only 2 files to migrate), strong focus on code reusability

---

**Generated**: 2025-11-11
**Analysis**: Claude Code
**Status**: Ready for Implementation
