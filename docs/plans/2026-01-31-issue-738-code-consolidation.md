# Issue #738: Code Consolidation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate duplicate files with forbidden naming patterns (`_unified`, `_optimized`, `_consolidated`) by migrating tests to canonical modules and deleting orphaned files.

**Architecture:** The codebase already has canonical implementations:
- `src/llm_interface.py` → facade delegating to `src/llm_interface_pkg/`
- `src/multimodal_processor.py` → facade delegating to `src/unified_multimodal_processor.py`

The orphaned files (`llm_interface_unified.py`, `unified_llm_interface.py`) duplicate functionality. Tests must be migrated to use canonical imports before deletion.

**Tech Stack:** Python, pytest, Git

---

## Summary of Files

### LLM Interface (3 files → 1)

| File | Lines | Status | Action |
|------|-------|--------|--------|
| `src/llm_interface.py` | 134 | ✅ Canonical facade | Keep |
| `src/llm_interface_pkg/` | ~1000 | ✅ Canonical implementation | Keep |
| `src/llm_interface_unified.py` | 767 | ❌ Orphaned | Delete after test migration |
| `src/unified_llm_interface.py` | 1170 | ❌ Orphaned | Delete after test migration |

### Multimodal Processor (3 files → 2)

| File | Lines | Status | Action |
|------|-------|--------|--------|
| `src/multimodal_processor.py` | 61 | ✅ Facade | Keep (rename later) |
| `src/unified_multimodal_processor.py` | 491 | ⚠️ Has `unified_` prefix | Rename to canonical |
| `src/multimodal_processor/unified.py` | 725 | ⚠️ Refactored package | Evaluate for consolidation |

### Tests Requiring Migration

| Test File | Imports From | Migrate To |
|-----------|--------------|------------|
| `tests/mock_llm_interface.py` | `src.llm_interface_unified` | `src.llm_interface` |
| `tests/test_unified_llm_interface.py` | `src.llm_interface_unified` | `src.llm_interface` |
| `tests/unit/test_unified_llm_interface_p6.py` | `src.unified_llm_interface` | `src.llm_interface` or delete |
| `tests/integration/test_multimodal_system.py` | `src.unified_multimodal_processor` | `src.multimodal_processor` |
| `tests/integration/test_config_migration.py` | `src.unified_multimodal_processor` | `src.multimodal_processor` |
| `tests/performance/test_system_benchmarks.py` | `src.unified_multimodal_processor` | `src.multimodal_processor` |

---

## Task 1: Verify Canonical LLM Interface Exports

**Files:**
- Read: `src/llm_interface.py`
- Read: `src/llm_interface_pkg/__init__.py`
- Read: `src/llm_interface_unified.py` (check what it exports)

**Step 1: Compare exports between canonical and orphaned files**

Run:
```bash
grep -E "^(class |def |async def )" src/llm_interface_unified.py | head -20
grep -E "^__all__" src/llm_interface.py -A 50
```

Expected: Identify any exports in orphaned file missing from canonical.

**Step 2: Document missing exports (if any)**

If orphaned file has exports not in canonical, note them for Task 2.

**Step 3: Commit analysis notes**

No code changes - analysis only.

---

## Task 2: Add Missing Exports to Canonical (if needed)

**Files:**
- Modify: `src/llm_interface.py` (if missing exports found)
- Modify: `src/llm_interface_pkg/__init__.py` (if missing exports found)

**Step 1: Add any missing re-exports**

Only if Task 1 found missing exports. Otherwise skip to Task 3.

**Step 2: Verify imports work**

Run:
```bash
python -c "from src.llm_interface import ProviderType, LLMType, LLMRequest, LLMResponse, LLMInterface, get_llm_interface; print('OK')"
```

Expected: `OK`

**Step 3: Commit if changes made**

```bash
git add src/llm_interface.py src/llm_interface_pkg/__init__.py
git commit -m "feat(llm): add missing exports to canonical interface (#738)"
```

---

## Task 3: Migrate tests/mock_llm_interface.py

**Files:**
- Modify: `tests/mock_llm_interface.py`

**Step 1: Update imports**

Replace:
```python
from src.llm_interface_unified import get_unified_llm_interface, ProviderType
```

With:
```python
from src.llm_interface import get_llm_interface, ProviderType
```

**Step 2: Update function calls**

Replace:
```python
llm = get_unified_llm_interface()
```

With:
```python
llm = get_llm_interface()
```

**Step 3: Update deprecation notice**

Update the module docstring to reference `src.llm_interface` instead.

**Step 4: Run tests to verify**

Run:
```bash
pytest tests/mock_llm_interface.py -v --tb=short 2>/dev/null || echo "No tests in this file (it's a mock module)"
```

**Step 5: Commit**

```bash
git add tests/mock_llm_interface.py
git commit -m "refactor(tests): migrate mock_llm_interface to canonical imports (#738)"
```

---

## Task 4: Evaluate test_unified_llm_interface.py

**Files:**
- Read: `tests/test_unified_llm_interface.py`

**Step 1: Analyze test coverage**

Check if tests cover functionality already tested elsewhere or unique to orphaned file.

Run:
```bash
wc -l tests/test_unified_llm_interface.py
grep -c "def test_" tests/test_unified_llm_interface.py
```

**Step 2: Decision point**

- If tests are for orphaned-specific code → Delete test file
- If tests cover general LLM functionality → Migrate imports

**Step 3: Migrate or delete**

If migrating, update imports:
```python
# Old
from src.llm_interface_unified import (
    UnifiedLLMInterface, LLMRequest, LLMResponse,
    ProviderType, LLMType, ProviderConfig,
    OllamaProvider, OpenAIProvider, MockProvider,
    get_unified_llm_interface
)

# New
from src.llm_interface import (
    LLMInterface, LLMRequest, LLMResponse,
    ProviderType, LLMType,
    get_llm_interface
)
from src.llm_interface_pkg import OllamaProvider, OpenAIProvider, MockHandler
```

If deleting:
```bash
git rm tests/test_unified_llm_interface.py
```

**Step 4: Commit**

```bash
git add tests/test_unified_llm_interface.py
git commit -m "refactor(tests): migrate/remove test_unified_llm_interface (#738)"
```

---

## Task 5: Evaluate test_unified_llm_interface_p6.py

**Files:**
- Read: `tests/unit/test_unified_llm_interface_p6.py`

**Step 1: Analyze test purpose**

This tests Phase 6 consolidation code in `src/unified_llm_interface.py`.

Run:
```bash
grep -c "def test_" tests/unit/test_unified_llm_interface_p6.py
head -30 tests/unit/test_unified_llm_interface_p6.py
```

**Step 2: Decision - likely delete**

Since `unified_llm_interface.py` will be deleted, these tests become orphaned. Check if any test logic should be preserved in new tests for `llm_interface_pkg`.

**Step 3: Delete orphaned test file**

```bash
git rm tests/unit/test_unified_llm_interface_p6.py
```

**Step 4: Commit**

```bash
git commit -m "refactor(tests): remove orphaned test_unified_llm_interface_p6 (#738)"
```

---

## Task 6: Migrate Multimodal Processor Tests

**Files:**
- Modify: `tests/integration/test_multimodal_system.py`
- Modify: `tests/integration/test_config_migration.py`
- Modify: `tests/performance/test_system_benchmarks.py`

**Step 1: Update imports in test_multimodal_system.py**

Replace:
```python
from src.unified_multimodal_processor import (
    ModalityType, ProcessingIntent, ...
)
```

With:
```python
from src.multimodal_processor import (
    ModalityType, ProcessingIntent, ...
)
```

**Step 2: Update patch paths**

Replace all occurrences of:
```python
patch('src.unified_multimodal_processor.get_config_section', ...)
```

With:
```python
patch('src.multimodal_processor.unified_processor.get_config_section', ...)
```

Or if the facade properly re-exports:
```python
patch('src.multimodal_processor.get_config_section', ...)
```

**Step 3: Update test_config_migration.py**

Same import changes.

**Step 4: Update test_system_benchmarks.py**

Same import changes.

**Step 5: Run tests to verify**

```bash
pytest tests/integration/test_multimodal_system.py -v --tb=short -x
pytest tests/integration/test_config_migration.py::TestConfigMigration::test_unified_multimodal_processor_config_usage -v
pytest tests/performance/test_system_benchmarks.py -v --tb=short -x
```

**Step 6: Commit**

```bash
git add tests/integration/test_multimodal_system.py tests/integration/test_config_migration.py tests/performance/test_system_benchmarks.py
git commit -m "refactor(tests): migrate multimodal tests to canonical imports (#738)"
```

---

## Task 7: Delete Orphaned LLM Interface Files

**Files:**
- Delete: `src/llm_interface_unified.py`
- Delete: `src/unified_llm_interface.py`

**Step 1: Verify no remaining imports**

Run:
```bash
grep -r "llm_interface_unified\|unified_llm_interface" src/ tests/ --include="*.py" | grep -v "\.pyc" | grep -v "__pycache__"
```

Expected: No results (or only in docs/comments).

**Step 2: Delete files**

```bash
git rm src/llm_interface_unified.py
git rm src/unified_llm_interface.py
```

**Step 3: Run full test suite**

```bash
pytest tests/ -x --tb=short -q
```

Expected: All tests pass.

**Step 4: Commit**

```bash
git commit -m "refactor(llm): remove orphaned llm_interface_unified files (#738)"
```

---

## Task 8: Rename unified_multimodal_processor.py (Optional)

**Files:**
- Rename: `src/unified_multimodal_processor.py` → integrate into `src/multimodal_processor.py`

**Step 1: Evaluate approach**

Option A: Keep facade pattern (simpler)
- `multimodal_processor.py` stays as facade
- `unified_multimodal_processor.py` renamed to `multimodal_processor_impl.py`

Option B: Merge into single file
- Combine both into `multimodal_processor.py`

**Decision:** Option A is safer for this issue. Full merge can be separate issue.

**Step 2: Rename implementation file**

```bash
git mv src/unified_multimodal_processor.py src/multimodal_processor_impl.py
```

**Step 3: Update facade imports**

In `src/multimodal_processor.py`, change:
```python
from src.unified_multimodal_processor import (
```

To:
```python
from src.multimodal_processor_impl import (
```

**Step 4: Update all other imports**

```bash
grep -rl "unified_multimodal_processor" src/ tests/ --include="*.py" | xargs sed -i 's/unified_multimodal_processor/multimodal_processor_impl/g'
```

**Step 5: Run tests**

```bash
pytest tests/integration/test_multimodal_system.py tests/performance/test_system_benchmarks.py -v --tb=short
```

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor(multimodal): rename unified_multimodal_processor to multimodal_processor_impl (#738)"
```

---

## Task 9: Update Documentation References

**Files:**
- Modify: `docs/LLM_Interface_Migration_Guide.md`
- Modify: `docs/guides/LLM_Interface_Migration_Guide.md`
- Modify: `analysis/refactoring/LLM_INTERFACE_CONSOLIDATION_COMPLETE_P6.md`

**Step 1: Update migration guide**

Remove references to deprecated files, update import examples.

**Step 2: Archive analysis docs**

Move Phase 6 analysis to archive or update to reflect completion.

**Step 3: Commit**

```bash
git add docs/
git commit -m "docs: update migration guides for consolidated imports (#738)"
```

---

## Task 10: Final Verification

**Step 1: Run full test suite**

```bash
pytest tests/ --tb=short -q
```

Expected: All tests pass.

**Step 2: Verify no forbidden naming patterns remain**

```bash
find src/ -name "*_unified*.py" -o -name "*unified_*.py" -o -name "*_consolidated*.py" -o -name "*_optimized*.py" 2>/dev/null
```

Expected: No results (except `multimodal_processor_impl.py` which is acceptable).

**Step 3: Update issue with completion summary**

Add comment to GitHub issue #738 with:
- Files deleted
- Tests migrated
- Verification results

**Step 4: Close issue**

```bash
gh issue close 738 --comment "Consolidation complete. See commits for details."
```

---

## Acceptance Criteria Checklist

- [ ] Single `llm_interface.py` facade with all features from `llm_interface_pkg`
- [ ] `llm_interface_unified.py` deleted
- [ ] `unified_llm_interface.py` deleted
- [ ] No files with `_consolidated`, `_unified`, `_optimized` suffixes (except impl)
- [ ] All imports updated to use canonical files
- [ ] Tests updated and passing
- [ ] Documentation updated
