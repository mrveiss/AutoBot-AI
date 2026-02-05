# Consolidate Sync Enhanced Memory Manager (#742)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate all imports from `src/enhanced_memory_manager.py` to `src/memory/` package and delete the standalone file.

**Architecture:** The `src/memory/` package already provides `EnhancedMemoryManager` via `compat.py`. This task migrates 7 files to use the canonical import path, verifies API compatibility, and removes the duplicate file.

**Tech Stack:** Python 3.11, SQLite, asyncio

**Scope:** Sync-only migration (Option B). The async `enhanced_memory_manager_async.py` remains unchanged due to different data models and numeric priority enums.

---

## Pre-Implementation Checklist

- [ ] Verify `src/memory/compat.py` exports match original API
- [ ] Run existing tests to establish baseline
- [ ] Create backup branch

---

### Task 1: Verify API Compatibility

**Files:**
- Read: `src/enhanced_memory_manager.py`
- Read: `src/memory/compat.py`
- Read: `src/memory/__init__.py`

**Step 1: Compare exported symbols**

Verify these symbols are available from `src.memory`:
- `EnhancedMemoryManager` class
- `TaskPriority` enum (with values: LOW, MEDIUM, HIGH, CRITICAL)
- `TaskStatus` enum
- `TaskExecutionRecord` dataclass

**Step 2: Document any missing methods**

Original `EnhancedMemoryManager` methods to verify in `src/memory/`:
- `create_task_record()` → maps to `log_task()` or needs wrapper
- `start_task()` → maps to `update_task_status()`
- `complete_task()` → maps to `update_task_status()`
- `fail_task()` → maps to `update_task_status()`
- `add_markdown_reference()` → check if supported
- `store_embedding()` → check if supported
- `get_embedding()` → check if supported
- `get_task_history()` → direct mapping exists
- `get_task_statistics()` → direct mapping exists
- `cleanup_old_data()` → maps to cleanup methods

**Step 3: Create API mapping document**

If any methods are missing, document required additions to `compat.py`.

---

### Task 2: Add Missing API Methods to compat.py

**Files:**
- Modify: `src/memory/compat.py`
- Test: `tests/unit/test_memory_compat.py` (create if needed)

**Step 1: Write failing tests for missing methods**

```python
# tests/unit/test_memory_compat.py
import pytest
from src.memory import EnhancedMemoryManager, TaskPriority, TaskStatus

class TestEnhancedMemoryManagerCompat:
    """Test backward compatibility with original enhanced_memory_manager.py API"""

    def test_create_task_record(self, tmp_path):
        """Test create_task_record method exists and works"""
        db_path = str(tmp_path / "test.db")
        manager = EnhancedMemoryManager(db_path=db_path)

        task_id = manager.create_task_record(
            task_name="Test Task",
            description="Test description",
            priority=TaskPriority.HIGH,
            agent_type="test_agent",
        )

        assert task_id is not None
        assert len(task_id) > 0

    def test_start_task(self, tmp_path):
        """Test start_task method exists and works"""
        db_path = str(tmp_path / "test.db")
        manager = EnhancedMemoryManager(db_path=db_path)

        task_id = manager.create_task_record(
            task_name="Test Task",
            description="Test description",
        )

        result = manager.start_task(task_id)
        assert result is True

    def test_complete_task(self, tmp_path):
        """Test complete_task method exists and works"""
        db_path = str(tmp_path / "test.db")
        manager = EnhancedMemoryManager(db_path=db_path)

        task_id = manager.create_task_record(
            task_name="Test Task",
            description="Test description",
        )
        manager.start_task(task_id)

        result = manager.complete_task(task_id, outputs={"result": "success"})
        assert result is True

    def test_fail_task(self, tmp_path):
        """Test fail_task method exists and works"""
        db_path = str(tmp_path / "test.db")
        manager = EnhancedMemoryManager(db_path=db_path)

        task_id = manager.create_task_record(
            task_name="Test Task",
            description="Test description",
        )
        manager.start_task(task_id)

        result = manager.fail_task(task_id, error_message="Test error")
        assert result is True

    def test_task_priority_values(self):
        """Test TaskPriority enum has expected values"""
        assert TaskPriority.LOW.value == "low"
        assert TaskPriority.MEDIUM.value == "medium"
        assert TaskPriority.HIGH.value == "high"
        assert TaskPriority.CRITICAL.value == "critical"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_memory_compat.py -v
```

Expected: Tests fail with AttributeError for missing methods.

**Step 3: Implement missing methods in compat.py**

Add to `src/memory/compat.py` in the `EnhancedMemoryManager` class:

```python
def create_task_record(
    self,
    task_name: str,
    description: str,
    priority: TaskPriority = TaskPriority.MEDIUM,
    agent_type: Optional[str] = None,
    inputs: Optional[Dict[str, Any]] = None,
    parent_task_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Create a new task execution record (backward compatibility).

    Maps to log_task() with auto-generated task_id.
    """
    import hashlib
    from datetime import datetime

    # Generate task_id matching original implementation
    timestamp = datetime.now().isoformat()
    content = f"{task_name}_{timestamp}"
    task_id = hashlib.sha256(content.encode()).hexdigest()[:16]

    record = TaskExecutionRecord(
        task_id=task_id,
        task_name=task_name,
        description=description,
        status=TaskStatus.PENDING,
        priority=priority,
        created_at=datetime.now(),
        agent_type=agent_type,
        inputs=inputs,
        parent_task_id=parent_task_id,
        metadata=metadata,
    )

    self.log_task_sync(record)
    logger.info("Created task record: %s - %s", task_id, task_name)
    return task_id

def start_task(self, task_id: str) -> bool:
    """Mark task as started (backward compatibility)."""
    import asyncio
    from datetime import datetime

    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                self.update_task_status(
                    task_id,
                    TaskStatus.IN_PROGRESS,
                    started_at=datetime.now()
                )
            )
            return future.result()
    except RuntimeError:
        return asyncio.run(
            self.update_task_status(
                task_id,
                TaskStatus.IN_PROGRESS,
                started_at=datetime.now()
            )
        )

def complete_task(
    self,
    task_id: str,
    outputs: Optional[Dict[str, Any]] = None,
    status: TaskStatus = TaskStatus.COMPLETED,
) -> bool:
    """Mark task as completed (backward compatibility)."""
    import asyncio
    from datetime import datetime

    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                self.update_task_status(
                    task_id,
                    status,
                    completed_at=datetime.now(),
                    outputs=outputs
                )
            )
            return future.result()
    except RuntimeError:
        return asyncio.run(
            self.update_task_status(
                task_id,
                status,
                completed_at=datetime.now(),
                outputs=outputs
            )
        )

def fail_task(
    self,
    task_id: str,
    error_message: str,
    retry_count: int = 0,
) -> bool:
    """Mark task as failed (backward compatibility)."""
    import asyncio
    from datetime import datetime

    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                self.update_task_status(
                    task_id,
                    TaskStatus.FAILED,
                    completed_at=datetime.now(),
                    error_message=error_message,
                    retry_count=retry_count
                )
            )
            return future.result()
    except RuntimeError:
        return asyncio.run(
            self.update_task_status(
                task_id,
                TaskStatus.FAILED,
                completed_at=datetime.now(),
                error_message=error_message,
                retry_count=retry_count
            )
        )
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_memory_compat.py -v
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add src/memory/compat.py tests/unit/test_memory_compat.py
git commit -m "feat(memory): add backward compat methods to EnhancedMemoryManager (#742)"
```

---

### Task 3: Migrate voice_processing/system.py

**Files:**
- Modify: `src/voice_processing/system.py:17`

**Step 1: Update import**

Change:
```python
from src.enhanced_memory_manager import EnhancedMemoryManager
```

To:
```python
from src.memory import EnhancedMemoryManager
```

**Step 2: Verify no other changes needed**

Search for any direct usage of `TaskPriority` or `TaskStatus` from the old module.

**Step 3: Run related tests**

```bash
pytest tests/ -k "voice" -v --tb=short
```

**Step 4: Commit**

```bash
git add src/voice_processing/system.py
git commit -m "refactor(voice): migrate to src.memory imports (#742)"
```

---

### Task 4: Migrate context_aware_decision/system.py

**Files:**
- Modify: `src/context_aware_decision/system.py:19`

**Step 1: Update import**

Change:
```python
from src.enhanced_memory_manager import EnhancedMemoryManager
```

To:
```python
from src.memory import EnhancedMemoryManager
```

**Step 2: Run related tests**

```bash
pytest tests/ -k "context" -v --tb=short
```

**Step 3: Commit**

```bash
git add src/context_aware_decision/system.py
git commit -m "refactor(context): migrate to src.memory imports (#742)"
```

---

### Task 5: Migrate markdown_reference_system.py

**Files:**
- Modify: `src/markdown_reference_system.py:18`

**Step 1: Update import**

Change:
```python
from src.enhanced_memory_manager import EnhancedMemoryManager
```

To:
```python
from src.memory import EnhancedMemoryManager
```

**Step 2: Run related tests**

```bash
pytest tests/ -k "markdown" -v --tb=short
```

**Step 3: Commit**

```bash
git add src/markdown_reference_system.py
git commit -m "refactor(markdown): migrate to src.memory imports (#742)"
```

---

### Task 6: Migrate takeover_manager.py

**Files:**
- Modify: `src/takeover_manager.py:17`

**Step 1: Update import**

Change:
```python
from src.enhanced_memory_manager import EnhancedMemoryManager, TaskPriority
```

To:
```python
from src.memory import EnhancedMemoryManager, TaskPriority
```

**Step 2: Run related tests**

```bash
pytest tests/ -k "takeover" -v --tb=short
```

**Step 3: Commit**

```bash
git add src/takeover_manager.py
git commit -m "refactor(takeover): migrate to src.memory imports (#742)"
```

---

### Task 7: Migrate computer_vision/system.py

**Files:**
- Modify: `src/computer_vision/system.py:16`

**Step 1: Update import**

Change:
```python
from src.enhanced_memory_manager import EnhancedMemoryManager, TaskPriority
```

To:
```python
from src.memory import EnhancedMemoryManager, TaskPriority
```

**Step 2: Run related tests**

```bash
pytest tests/ -k "computer_vision" -v --tb=short
```

**Step 3: Commit**

```bash
git add src/computer_vision/system.py
git commit -m "refactor(cv): migrate to src.memory imports (#742)"
```

---

### Task 8: Migrate computer_vision/screen_analyzer.py

**Files:**
- Modify: `src/computer_vision/screen_analyzer.py:23`

**Step 1: Update import**

Change:
```python
from src.enhanced_memory_manager import TaskPriority
```

To:
```python
from src.memory import TaskPriority
```

**Step 2: Run related tests**

```bash
pytest tests/ -k "screen_analyzer" -v --tb=short
```

**Step 3: Commit**

```bash
git add src/computer_vision/screen_analyzer.py
git commit -m "refactor(screen_analyzer): migrate to src.memory imports (#742)"
```

---

### Task 9: Migrate modern_ai_integration.py

**Files:**
- Modify: `src/modern_ai_integration.py:20`

**Step 1: Update import**

Change:
```python
from src.enhanced_memory_manager import EnhancedMemoryManager, TaskPriority
```

To:
```python
from src.memory import EnhancedMemoryManager, TaskPriority
```

**Step 2: Run related tests**

```bash
pytest tests/ -k "ai_integration" -v --tb=short
```

**Step 3: Commit**

```bash
git add src/modern_ai_integration.py
git commit -m "refactor(ai): migrate to src.memory imports (#742)"
```

---

### Task 10: Run Full Test Suite

**Step 1: Run all tests**

```bash
pytest tests/ -v --tb=short
```

**Step 2: Fix any failures**

Address any test failures before proceeding.

**Step 3: Run type checking**

```bash
mypy src/memory/ src/voice_processing/ src/context_aware_decision/ src/computer_vision/ --ignore-missing-imports
```

---

### Task 11: Delete enhanced_memory_manager.py

**Files:**
- Delete: `src/enhanced_memory_manager.py`

**Step 1: Verify no remaining imports**

```bash
grep -r "from src.enhanced_memory_manager import" src/ --include="*.py"
grep -r "from src import enhanced_memory_manager" src/ --include="*.py"
```

Expected: No matches (only async file should remain).

**Step 2: Delete the file**

```bash
rm src/enhanced_memory_manager.py
```

**Step 3: Run full test suite again**

```bash
pytest tests/ -v --tb=short
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(memory): delete enhanced_memory_manager.py (#742)

All imports migrated to src.memory package.
enhanced_memory_manager_async.py remains (different data model)."
```

---

### Task 12: Update Issue and Documentation

**Step 1: Update GitHub issue #742**

Add comment with migration summary:
- 7 files migrated
- `enhanced_memory_manager.py` deleted
- `enhanced_memory_manager_async.py` retained (Option B)
- Tests passing

**Step 2: Update acceptance criteria**

Mark completed:
- [x] All imports migrated to `src.memory`
- [x] `enhanced_memory_manager.py` deleted
- [ ] `enhanced_memory_manager_async.py` deleted (N/A - Option B)
- [x] Tests passing
- [x] No breaking changes

**Step 3: Close issue if all criteria met**

---

## Verification Checklist

After completing all tasks:

- [ ] `grep -r "enhanced_memory_manager" src/` shows only async file and memory package references
- [ ] `pytest tests/` passes
- [ ] All 7 files import from `src.memory`
- [ ] `src/enhanced_memory_manager.py` is deleted
- [ ] `src/enhanced_memory_manager_async.py` is unchanged
