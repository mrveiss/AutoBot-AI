# Logging Configuration Migration Guide

## Overview

This guide documents the migration from scattered `logging.basicConfig()` calls to the centralized `LoggingManager` system in `autobot-user-backend/utils/logging_manager.py`.

**Issue**: [#42 - Logging Configuration Standardization](https://github.com/paradiselabs-ai/AutoBot/issues/42)

---

## Why Centralized Logging?

### Problems with `logging.basicConfig()`:

1. **Configuration Conflicts** - Multiple calls overwrite each other
2. **No Categorization** - All logs mixed together, hard to filter
3. **No Rotation** - Log files grow unbounded
4. **Inconsistent Formatting** - Different formats across codebase
5. **No Environment Control** - Can't configure via env vars

### Benefits of Centralized Logging:

1. ✅ **Single Configuration Point** - `autobot-user-backend/utils/logging_manager.py`
2. ✅ **Category-Based Loggers** - backend, frontend, llm, debug, audit
3. ✅ **Automatic Log Rotation** - 10MB max size, 5 backups
4. ✅ **Environment-Based Config** - `AUTOBOT_LOG_LEVEL`, `AUTOBOT_LOGS_DIR`
5. ✅ **Consistent Formatting** - Same format across all modules
6. ✅ **Backward Compatible** - Convenience functions for easy migration

---

## Migration Pattern

### Core Production Files (COMPLETE - 6/6 ✅)

**Migrated Files:**
- ✅ `backend/main.py`
- ✅ `backend/app_factory_enhanced.py`
- ✅ `backend/utils/redis_compatibility.py`
- ✅ `src/project_state_manager.py`
- ✅ `autobot-user-backend/agents/research_agent.py`
- ✅ `autobot-user-backend/utils/system_context.py`

### Before Migration:

```python
import logging

# Module-level logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ... code ...

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    # ... test code ...
```

### After Migration:

```python
from src.utils.logging_manager import get_logger

# Get centralized logger
logger = get_logger(__name__, "backend")

# ... code ...

if __name__ == "__main__":
    # Logging configured via centralized logging_manager
    # ... test code ...
```

---

## Step-by-Step Migration

### Step 1: Update Imports

**Remove:**
```python
import logging
```

**Add:**
```python
from src.utils.logging_manager import get_logger
```

### Step 2: Replace Logger Initialization

**Replace:**
```python
logger = logging.getLogger(__name__)
```

**With:**
```python
logger = get_logger(__name__, "backend")  # or appropriate category
```

### Step 3: Remove `logging.basicConfig()` Calls

**Remove all instances of:**
```python
logging.basicConfig(level=logging.INFO)
logging.basicConfig(level=logging.DEBUG, format="...")
logging.basicConfig(...)
```

**Replace with comment:**
```python
# Logging configured via centralized logging_manager
```

### Step 4: Choose Appropriate Category

Select the correct category for your logger:

| Category | Use Case | Example Modules |
|----------|----------|-----------------|
| `backend` | Backend API, services, utilities | `autobot-user-backend/api/*.py`, `autobot-user-backend/utils/*.py` |
| `frontend` | Frontend-related backend code | Vue build scripts, frontend helpers |
| `llm` | LLM interactions, prompts | `src/llm_interface.py`, LLM services |
| `debug` | Debug/development logging | Test utilities, debug scripts |
| `audit` | Security audit logs | Security layer, auth modules |

---

## Common Migration Scenarios

### Scenario 1: Simple Module Logger

**Before:**
```python
import logging

logger = logging.getLogger(__name__)

def my_function():
    logger.info("Processing data")
```

**After:**
```python
from src.utils.logging_manager import get_logger

logger = get_logger(__name__, "backend")

def my_function():
    logger.info("Processing data")
```

### Scenario 2: Module with `basicConfig()`

**Before:**
```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
```

**After:**
```python
from src.utils.logging_manager import get_logger

logger = get_logger(__name__, "backend")
```

### Scenario 3: `__main__` Block with Logging

**Before:**
```python
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    main()
```

**After:**
```python
if __name__ == "__main__":
    # Logging configured via centralized logging_manager
    main()
```

### Scenario 4: Test Script with Multiple Loggers

**Before:**
```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
test_logger = logging.getLogger("test")

def test_function():
    logger.debug("Test starting")
    test_logger.info("Running tests")
```

**After:**
```python
from src.utils.logging_manager import get_logger

logger = get_logger(__name__, "debug")
test_logger = get_logger("test", "debug")

def test_function():
    logger.debug("Test starting")
    test_logger.info("Running tests")
```

### Scenario 5: Async Module with Logging

**Before:**
```python
import asyncio
import logging

logger = logging.getLogger(__name__)

async def async_task():
    logger.info("Async task started")
```

**After:**
```python
import asyncio
from src.utils.logging_manager import get_logger

logger = get_logger(__name__, "backend")

async def async_task():
    logger.info("Async task started")
```

---

## Testing Your Migration

### 1. Verify Imports

```bash
# Check that old logging imports are removed
grep -r "import logging" backend/ src/ --include="*.py"

# Should only see centralized logging_manager imports
grep -r "from src.utils.logging_manager import get_logger" backend/ src/
```

### 2. Verify No `basicConfig()` Calls

```bash
# Check for remaining basicConfig calls (excluding logging_manager.py itself)
grep -r "logging.basicConfig" backend/ src/ --include="*.py" \
  --exclude="logging_manager.py"
```

### 3. Test Logging Output

```python
# Test script to verify logging works
from src.utils.logging_manager import get_logger

logger = get_logger("test_migration", "debug")
logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

Expected output in `logs/backend.log`:
```
2025-01-14 10:30:00 - test_migration - DEBUG - Debug message
2025-01-14 10:30:00 - test_migration - INFO - Info message
2025-01-14 10:30:00 - test_migration - WARNING - Warning message
2025-01-14 10:30:00 - test_migration - ERROR - Error message
```

### 4. Verify Log Rotation

```bash
# Check that log files are created with rotation
ls -lh logs/
# Should see: backend.log, backend.log.1, backend.log.2, etc.
```

---

## Environment Configuration

Control logging via environment variables:

```bash
# Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
export AUTOBOT_LOG_LEVEL=DEBUG

# Set logs directory
export AUTOBOT_LOGS_DIR=/path/to/logs

# Set backup directory
export AUTOBOT_LOGS_BACKUP_DIR=/path/to/backups
```

---

## Remaining Files to Migrate

### Scripts (Low Priority)

**Pattern for scripts:**
- Replace `logging.basicConfig()` with centralized logger
- Use `debug` category for most scripts
- Keep print statements for user-facing output

**Examples:**
```bash
scripts/detect-hardcoded-values.sh  # Shell script - no migration needed
scripts/test_*.py                   # Use "debug" category
scripts/utilities/*.py              # Use "debug" category
```

### Tests (Low Priority)

**Pattern for tests:**
- Use `debug` category for test logging
- Keep test framework logging separate
- Only migrate test utilities, not test assertions

**Examples:**
```bash
tests/unit/*.py          # Use "debug" category
tests/integration/*.py   # Use "debug" category
```

### Migration Commands

```bash
# Find all files with logging.basicConfig
find backend/ src/ scripts/ tests/ -name "*.py" -exec grep -l "logging.basicConfig" {} \;

# Count remaining migrations
grep -r "logging.basicConfig" backend/ src/ scripts/ tests/ --include="*.py" \
  --exclude="logging_manager.py" | wc -l
```

---

## Backward Compatibility

The centralized logging system provides convenience functions for backward compatibility:

```python
# All of these work and map to appropriate categories:
from src.utils.logging_manager import (
    get_logger,           # General-purpose (preferred)
    get_backend_logger,   # backend category
    get_frontend_logger,  # frontend category
    get_llm_logger,       # llm category
    get_debug_logger,     # debug category
    get_audit_logger,     # audit category
)

# Usage:
backend_logger = get_backend_logger("my_module")
llm_logger = get_llm_logger("my_llm_code")
```

---

## Troubleshooting

### Issue: "No handlers could be found for logger"

**Solution:** Ensure `LoggingManager.initialize()` is called during app startup
- Already configured in `backend/main.py` and `backend/app_factory.py`
- For standalone scripts, logging is initialized on first `get_logger()` call

### Issue: Logs not appearing in file

**Solution:** Check log directory permissions and environment variables
```bash
# Verify logs directory exists and is writable
mkdir -p logs
chmod 755 logs

# Check environment variables
echo $AUTOBOT_LOG_LEVEL
echo $AUTOBOT_LOGS_DIR
```

### Issue: Log rotation not working

**Solution:** Verify `RotatingFileHandler` configuration in `logging_manager.py`
- Default: 10MB max size, 5 backups
- Check disk space and permissions

### Issue: Duplicate log entries

**Solution:** Remove any remaining `logging.basicConfig()` calls
```bash
# Find remaining basicConfig calls
grep -r "logging.basicConfig" . --include="*.py" --exclude="logging_manager.py"
```

---

## Migration Checklist

For each file being migrated:

- [ ] Replace `import logging` with `from src.utils.logging_manager import get_logger`
- [ ] Replace `logger = logging.getLogger(__name__)` with `logger = get_logger(__name__, category)`
- [ ] Remove all `logging.basicConfig()` calls
- [ ] Add comment `# Logging configured via centralized logging_manager`
- [ ] Choose appropriate category (backend, frontend, llm, debug, audit)
- [ ] Test that logging works correctly
- [ ] Verify no duplicate log entries
- [ ] Check log files are created in `logs/` directory

---

## Migration Progress

### Core Production Files: 6/6 (100%) ✅

- ✅ backend/main.py
- ✅ backend/app_factory_enhanced.py
- ✅ backend/utils/redis_compatibility.py
- ✅ src/project_state_manager.py
- ✅ autobot-user-backend/agents/research_agent.py
- ✅ autobot-user-backend/utils/system_context.py

### Remaining (Low Priority):

- Scripts: ~20-30 files
- Tests: ~70-80 files

**Total Migrated:** 6 core files (critical paths complete)
**Remaining:** Non-critical scripts and tests (can be migrated incrementally)

---

## References

- **Centralized Logging Implementation:** `autobot-user-backend/utils/logging_manager.py`
- **GitHub Issue:** [#42 - Logging Configuration Standardization](https://github.com/paradiselabs-ai/AutoBot/issues/42)
- **Python Logging Documentation:** https://docs.python.org/3/library/logging.html
- **RotatingFileHandler:** https://docs.python.org/3/library/logging.handlers.html#rotatingfilehandler

---

**Last Updated:** 2025-01-14
**Migration Status:** Core production files complete (6/6)
