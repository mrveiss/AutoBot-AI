# Stale Import Paths After Folder Refactoring

**Issue Number**: #806
**Date Reported**: 2026-02-09
**Severity**: High
**Component**: Backend / Python Imports

---

## Symptoms

- `ModuleNotFoundError: No module named 'src.xxx'`
- `ImportError: cannot import name 'xxx' from 'src.yyy'`
- Tests fail with import errors
- Backend services crash on startup
- Pre-commit hooks fail on import validation

## Root Cause

After folder reorganization (#781), many files still used old `from src.*` import paths:
- Old: `from src.api.endpoints import users`
- New: `from api.endpoints import users`

**Scale**: 427+ stale imports across 210 files

## Quick Fix

```bash
# Find all stale imports
grep -r "from src\." autobot-user-backend/ --include="*.py" | wc -l

# Auto-fix common patterns (backup first!)
find autobot-user-backend -name "*.py" -type f -exec sed -i 's/from src\./from /g' {} \;
find autobot-user-backend -name "*.py" -type f -exec sed -i 's/import src\./import /g' {} \;

# Run tests to verify
pytest autobot-user-backend/
```

## Detailed Resolution Steps

### Step 1: Identify Stale Imports

```bash
# Search for src. imports
grep -r "from src\." autobot-user-backend/ --include="*.py" | head -20

# Get file list
grep -rl "from src\." autobot-user-backend/ --include="*.py" > /tmp/files_to_fix.txt

# Count affected files
wc -l /tmp/files_to_fix.txt
```

### Step 2: Understand Import Patterns

Common stale patterns:

| Old Import | New Import |
|------------|------------|
| `from src.api.endpoints` | `from api.endpoints` |
| `from src.services.llm` | `from services.llm` |
| `from src.utils.redis_client` | `from autobot_shared.redis_client` |
| `from src.config` | `from config` |
| `import src.api` | `import api` |

**Shared code moved to `autobot-shared/`**:
- `src.utils.redis_client` → `autobot_shared.redis_client`
- `src.utils.logging` → `autobot_shared.logging`
- `src.config.ssot_config` → `autobot_shared.ssot_config`

### Step 3: Fix Systematically

```bash
# Backup first!
git stash push -m "Before import path fix"

# Fix production code
find autobot-user-backend/api -name "*.py" -type f -exec sed -i 's/from src\./from /g' {} \;
find autobot-user-backend/services -name "*.py" -type f -exec sed -i 's/from src\./from /g' {} \;
find autobot-user-backend/agents -name "*.py" -type f -exec sed -i 's/from src\./from /g' {} \;

# Fix tests (colocated)
find autobot-user-backend -name "*_test.py" -type f -exec sed -i 's/from src\./from /g' {} \;

# Fix shared imports
find autobot-user-backend -name "*.py" -type f -exec sed -i 's/from src\.utils\./from autobot_shared./g' {} \;

# Verify no stale imports remain
grep -r "from src\." autobot-user-backend/ --include="*.py" | wc -l
# Should be 0
```

### Step 4: Handle Edge Cases

Some files need manual fixes:

**Infrastructure/debug scripts**:
```python
# If infrastructure/shared/scripts/xxx.py still has:
from src.api import xxx

# Fix depends on context:
# Option A: Add autobot-user-backend to path
import sys
sys.path.insert(0, '/opt/autobot/autobot-user-backend')
from api import xxx

# Option B: Use absolute imports
from autobot_user_backend.api import xxx
```

### Step 5: Fix Pre-commit Hook Violations

```bash
# Run pre-commit on fixed files
pre-commit run --files $(git diff --name-only --cached)

# Common violations after import fixes:
# - E501 (line too long) - break long imports
# - F401 (unused import) - remove if truly unused
# - I001 (import order) - run isort

# Auto-fix import order
isort autobot-user-backend/
```

### Step 6: Run Tests

```bash
# Run pytest on all tests
pytest autobot-user-backend/ -v

# If specific tests fail, check:
# 1. Colocated test imports
# 2. Fixture imports
# 3. Shared utility imports
```

## Verification

```bash
# 1. No stale imports remain
grep -r "from src\." autobot-user-backend/ --include="*.py"
# Expected: (empty)

# 2. All tests pass
pytest autobot-user-backend/ --tb=short

# 3. Backend starts without import errors
cd autobot-user-backend
python -m uvicorn main:app --reload
# Should start without ModuleNotFoundError

# 4. Pre-commit passes
git add -A
pre-commit run --all-files
```

**Success Indicators**:
- Zero `from src.*` imports
- All tests passing
- Backend starts successfully
- Pre-commit hooks pass
- No `ModuleNotFoundError` in logs

## Prevention

1. **Use absolute imports** from component root:
   ```python
   # Good
   from api.endpoints import users
   from services.llm import chat_service

   # Bad
   from src.api.endpoints import users
   from .endpoints import users  # relative imports
   ```

2. **Update imports immediately** after folder moves:
   ```bash
   git mv old_dir new_dir
   # Then immediately fix imports
   find . -name "*.py" -exec sed -i 's/from old_dir/from new_dir/g' {} \;
   ```

3. **Add pre-commit hook** to catch stale imports:
   ```yaml
   # .pre-commit-config.yaml
   - repo: local
     hooks:
       - id: no-src-imports
         name: Check for stale src. imports
         entry: bash -c 'grep -r "from src\." . --include="*.py" && exit 1 || exit 0'
         language: system
         types: [python]
   ```

4. **Run import checker** before major refactoring:
   ```bash
   pylint --disable=all --enable=import-error autobot-user-backend/
   ```

## Related Issues

- #781: Folder reorganization that caused stale imports
- #793, #795, #796: Follow-up fallout fixes
- #825: Code quality cleanup

## References

- PR #806: 427+ import fixes across 210 files
- Commit: `3f7a8b9d`
- Pattern: `s/from src\./from /g`
