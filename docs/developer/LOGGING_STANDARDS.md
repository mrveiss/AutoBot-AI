# Logging Standards Guide

**Author**: mrveiss
**Copyright**: 2025 mrveiss

This document defines the logging standards for the AutoBot platform, ensuring consistent, traceable, and useful logs across all components.

---

## Table of Contents

1. [Why Structured Logging](#why-structured-logging)
2. [Frontend Logging (Vue/TypeScript)](#frontend-logging-vuetypescript)
3. [Backend Logging (Python)](#backend-logging-python)
4. [Log Levels](#log-levels)
5. [Best Practices](#best-practices)
6. [Common Patterns](#common-patterns)
7. [Pre-commit Enforcement](#pre-commit-enforcement)

---

## Why Structured Logging

**Problems with console.log/print():**
- No log levels - can't filter by severity
- No timestamps - hard to trace when events occurred
- No context - which component/module logged this?
- No control - can't disable in production
- Inconsistent format - hard to parse or search

**Benefits of structured logging:**
- **Filterable**: Enable/disable logs by level or module
- **Contextual**: Know exactly where each log originated
- **Consistent**: Same format across entire codebase
- **Configurable**: Adjust verbosity without code changes
- **Searchable**: Easier to grep/search through logs

---

## Frontend Logging (Vue/TypeScript)

### Pattern

```typescript
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ComponentName')

// Use throughout the component
logger.debug('Detailed debugging info', { someData })
logger.info('Normal operation event')
logger.warn('Warning condition detected', { context })
logger.error('Error occurred', error)
```

### Location

The `createLogger` utility is defined in `autobot-vue/src/utils/debugUtils.ts`.

### Configuration

Log levels can be controlled via:
- Development mode automatically enables debug logs
- Production mode filters to warn/error only
- Specific modules can be enabled/disabled

### Example: Vue Component

```vue
<script setup lang="ts">
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('UserProfile')

const loadProfile = async (userId: string) => {
  logger.debug('Loading profile', { userId })

  try {
    const profile = await api.getProfile(userId)
    logger.info('Profile loaded successfully')
    return profile
  } catch (error) {
    logger.error('Failed to load profile', error)
    throw error
  }
}
</script>
```

### Example: Composable

```typescript
import { createLogger } from '@/utils/debugUtils'

export function useWebSocket(url: string) {
  const logger = createLogger('useWebSocket')

  const connect = () => {
    logger.debug('Connecting to WebSocket', { url })
    // ...
  }

  const onMessage = (data: unknown) => {
    logger.debug('Message received', { data })
    // ...
  }

  const onError = (error: Event) => {
    logger.error('WebSocket error', error)
    // ...
  }

  return { connect }
}
```

---

## Backend Logging (Python)

### Pattern

```python
import logging

logger = logging.getLogger(__name__)

# Use throughout the module
logger.debug("Detailed debugging info: %s", data)
logger.info("Normal operation event")
logger.warning("Warning condition: %s", context)
logger.error("Error occurred: %s", error, exc_info=True)
```

### Configuration

Logging is configured in `backend/core/logging_config.py` with:
- Console handler for development
- File handler for production
- JSON formatting for structured logs
- Configurable log levels per module

### Example: FastAPI Endpoint

```python
import logging
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/users/{user_id}")
async def get_user(user_id: int):
    logger.debug("Fetching user: %s", user_id)

    try:
        user = await user_service.get(user_id)
        logger.info("User retrieved: %s", user_id)
        return user
    except UserNotFoundError:
        logger.warning("User not found: %s", user_id)
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        logger.error("Failed to fetch user: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")
```

### Example: Service Class

```python
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self):
        logger.info("CacheService initialized")

    async def get(self, key: str) -> Optional[str]:
        logger.debug("Cache get: %s", key)
        value = await self._redis.get(key)

        if value is None:
            logger.debug("Cache miss: %s", key)
        else:
            logger.debug("Cache hit: %s", key)

        return value

    async def set(self, key: str, value: str, ttl: int = 300) -> None:
        logger.debug("Cache set: %s (ttl=%d)", key, ttl)
        try:
            await self._redis.setex(key, ttl, value)
        except Exception as e:
            logger.error("Cache set failed: %s - %s", key, e)
            raise
```

---

## Log Levels

| Level | When to Use | Examples |
|-------|-------------|----------|
| **DEBUG** | Detailed info for debugging; disabled in production | Variable values, function entry/exit, internal state |
| **INFO** | Normal operation events worth recording | Service started, user action completed, configuration loaded |
| **WARNING** | Unexpected but handled conditions | Deprecated API used, retry needed, fallback activated |
| **ERROR** | Errors that prevent operation completion | Exception caught, operation failed, service unavailable |
| **CRITICAL** | System-level failures requiring immediate attention | Database connection lost, out of memory, security breach |

### Guidelines

```python
# DEBUG - Development/troubleshooting only
logger.debug("Processing item %d of %d: %s", i, total, item)

# INFO - Normal operations
logger.info("User %s logged in successfully", username)

# WARNING - Recovered issues
logger.warning("Rate limit approaching: %d/%d requests", current, limit)

# ERROR - Failed operations (with stack trace when helpful)
logger.error("Failed to process payment: %s", error, exc_info=True)

# CRITICAL - System-level issues
logger.critical("Database connection pool exhausted!")
```

---

## Best Practices

### 1. Never Log Sensitive Data

```python
# BAD - Logs password
logger.info("User login: %s, password: %s", user, password)

# GOOD - Masks sensitive data
logger.info("User login: %s", user)
```

### 2. Include Context

```python
# BAD - No context
logger.error("Failed")

# GOOD - Actionable context
logger.error("Failed to save user %s: %s", user_id, error)
```

### 3. Use String Formatting (Python)

```python
# BAD - String concatenation (always evaluated)
logger.debug("Processing: " + str(expensive_operation()))

# GOOD - Lazy formatting (only evaluated if debug enabled)
logger.debug("Processing: %s", expensive_operation())
```

### 4. Log at Appropriate Level

```python
# BAD - Error for expected condition
logger.error("Cache miss for key: %s", key)

# GOOD - Debug for expected condition
logger.debug("Cache miss for key: %s", key)
```

### 5. Include Stack Traces for Errors

```python
try:
    result = await risky_operation()
except Exception as e:
    # Include exc_info=True for stack trace
    logger.error("Operation failed: %s", e, exc_info=True)
```

### 6. Use Consistent Prefixes (Frontend)

```typescript
// Scope should match component/module name
const logger = createLogger('UserProfileCard')    // Component
const logger = createLogger('useAuthentication')   // Composable
const logger = createLogger('apiClient')           // Utility
```

---

## Common Patterns

### API Request Logging

```typescript
const logger = createLogger('apiClient')

async function request<T>(config: RequestConfig): Promise<T> {
  logger.debug('API request', { method: config.method, url: config.url })

  try {
    const response = await axios(config)
    logger.debug('API response', { status: response.status })
    return response.data
  } catch (error) {
    logger.error('API error', { url: config.url, error })
    throw error
  }
}
```

### Async Operation Logging

```python
logger = logging.getLogger(__name__)

async def process_batch(items: list) -> list:
    logger.info("Starting batch processing: %d items", len(items))

    results = []
    for i, item in enumerate(items):
        logger.debug("Processing item %d/%d: %s", i + 1, len(items), item.id)
        try:
            result = await process_item(item)
            results.append(result)
        except Exception as e:
            logger.warning("Item %s failed: %s", item.id, e)

    logger.info("Batch complete: %d/%d successful", len(results), len(items))
    return results
```

### Service Initialization

```python
logger = logging.getLogger(__name__)

class DatabaseService:
    def __init__(self, config: DatabaseConfig):
        logger.info("Initializing DatabaseService")
        logger.debug("Database config: host=%s, port=%d", config.host, config.port)

        self._pool = self._create_pool(config)
        logger.info("DatabaseService ready: pool_size=%d", config.pool_size)

    async def close(self):
        logger.info("Closing DatabaseService")
        await self._pool.close()
        logger.debug("Database connections closed")
```

---

## Pre-commit Enforcement

A pre-commit hook prevents new `console.*` and `print()` statements from being committed.

### How It Works

1. When you commit, the hook runs `scripts/detect-logging-violations.sh --staged-only`
2. It checks staged Python/TypeScript/Vue files for violations
3. If violations found, commit is blocked with fix instructions

### Excluded Files

**Python:**
- `if __name__ == "__main__":` blocks (test/demo code)
- CLI tools (`service_registry_cli.py`)
- Test files

**Frontend:**
- `debugUtils.ts` (logger implementation)
- RUM tools (`RumAgent.ts`, `RumConsoleHelper.ts`)
- Example/demo components

### Bypass (Emergency Only)

```bash
git commit --no-verify
```

**Warning**: Bypassing is strongly discouraged. Fix the violation properly.

### Manual Check

```bash
# Check all files
./scripts/detect-logging-violations.sh

# Check only staged files
./scripts/detect-logging-violations.sh --staged-only
```

---

## Quick Reference

### Frontend

```typescript
import { createLogger } from '@/utils/debugUtils'
const logger = createLogger('ModuleName')

logger.debug('msg', data)   // Development only
logger.info('msg')          // Normal operation
logger.warn('msg', context) // Recovered issues
logger.error('msg', error)  // Failures
```

### Backend

```python
import logging
logger = logging.getLogger(__name__)

logger.debug("msg: %s", data)      # Development only
logger.info("msg")                  # Normal operation
logger.warning("msg: %s", context)  # Recovered issues
logger.error("msg: %s", e, exc_info=True)  # Failures
```

---

## Related Documentation

- [CLAUDE.md](../../CLAUDE.md) - Development guidelines
- [UTF8_ENFORCEMENT.md](UTF8_ENFORCEMENT.md) - Encoding standards
- [CODE_QUALITY_ENFORCEMENT.md](CODE_QUALITY_ENFORCEMENT.md) - Quality standards
