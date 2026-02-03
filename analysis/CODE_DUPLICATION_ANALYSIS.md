# Code Duplication & Refactoring Analysis

**Date**: 2025-10-25
**Scope**: AutoBot Backend Codebase
**Analysis Type**: Systematic duplication detection and refactoring opportunities

---

## Executive Summary

### Findings:
- **328 instances** of `HTTPException(status_code=500)` - Could benefit from centralized error handling
- **79 files** with generic `except Exception as e:` handlers
- **40+ instances** of duplicated exception handling patterns
- **11 inline** `import traceback` statements - Should be at module level
- **Multiple inline** `import json` statements in functions
- **20+ duplicated** timeout patterns with `asyncio.wait_for()`

### Impact Assessment:
- **High**: Error handling and HTTP exception patterns
- **Medium**: Inline imports and timeout configurations
- **Low**: Logging patterns (stylistic)

---

## Pattern 1: HTTPException Error Handling (HIGH PRIORITY)

### Current State:
```python
# Pattern appears 328 times:
try:
    # ... operation ...
except Exception as e:
    logger.error(f"Failed to {operation}: {e}")
    raise HTTPException(status_code=500, detail=f"Failed to {operation}: {str(e)}")
```

### Distribution:
- **328 instances** of status_code=500
- **76 instances** of status_code=404
- **41 instances** of status_code=400
- **22 instances** of status_code=503

### Recommendation:
Create centralized error handler decorators or context managers.

**Proposed Solution**:
```python
# backend/utils/error_handlers.py
from functools import wraps
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

def handle_api_errors(operation_name: str, status_code: int = 500):
    """Decorator to standardize API error handling."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise  # Re-raise HTTP exceptions as-is
            except Exception as e:
                logger.error(f"Failed to {operation_name}: {e}")
                raise HTTPException(
                    status_code=status_code,
                    detail=f"Failed to {operation_name}: {str(e)}"
                )
        return wrapper
    return decorator

# Usage:
@router.get("/endpoint")
@handle_api_errors("fetch data")
async def get_data():
    # ... operation ...
```

**Benefits**:
- Reduces 328+ duplicated try/except blocks to simple decorators
- Consistent error responses across all endpoints
- Easier to add features (e.g., error tracking, metrics)
- Single place to modify error handling behavior

---

## Pattern 2: Inline Imports (MEDIUM PRIORITY)

### Current State:
Found **11 inline** `import traceback` and **multiple** `import json` inside functions.

**Examples**:
```python
# backend/services/agent_terminal_service.py:302
except Exception as e:
    logger.error(f"Failed: {e}")
    import traceback  # ❌ Should be at top
    logger.error(f"Traceback: {traceback.format_exc()}")

# backend/api/knowledge.py (multiple locations)
def some_function():
    import json  # ❌ Should be at top
    data = json.loads(...)
```

### Recommendation:
Move all imports to module level (PEP 8 compliance).

**Proposed Solution**:
```python
# At top of file
import json
import traceback
import logging

logger = logging.getLogger(__name__)

# In function
except Exception as e:
    logger.error(f"Failed: {e}")
    logger.error(f"Traceback: {traceback.format_exc()}")
```

**Benefits**:
- Faster execution (imports happen once)
- Better code organization
- Easier dependency tracking
- PEP 8 compliance

---

## Pattern 3: Redis Access Patterns (MEDIUM PRIORITY)

### Current State:
Multiple patterns for Redis access across the codebase:
- `redis_client.get()` / `redis_client.set()`
- `aioredis_client.get()` / `aioredis_client.set()`
- `redis_client.hgetall()` / `aioredis_client.hgetall()`

**Found in**: `backend/api/knowledge.py` (20+ instances)

### Issues:
- Mix of sync and async Redis clients
- No consistent error handling
- No timeout protection on blocking operations
- Duplicated cache key generation logic

### Recommendation:
Create Redis utility class with standardized methods.

**Proposed Solution**:
```python
# backend/utils/redis_helper.py
class RedisHelper:
    """Centralized Redis operations with consistent error handling."""

    def __init__(self, sync_client, async_client):
        self.sync = sync_client
        self.async_client = async_client

    async def get_with_timeout(self, key: str, timeout: float = 2.0):
        """Get with timeout protection."""
        try:
            return await asyncio.wait_for(
                self.async_client.get(key),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Redis GET timeout for key: {key}")
            return None
        except Exception as e:
            logger.error(f"Redis GET failed for key {key}: {e}")
            return None

    async def cache_json(self, key: str, data: dict, ttl: int = 60):
        """Cache JSON data with TTL."""
        try:
            await self.async_client.setex(
                key, ttl, json.dumps(data)
            )
        except Exception as e:
            logger.error(f"Cache write failed for {key}: {e}")
```

**Benefits**:
- Consistent timeout handling
- Centralized error logging
- Single source of truth for Redis patterns
- Easier to add monitoring/metrics

---

## Pattern 4: Timeout Configurations (MEDIUM PRIORITY)

### Current State:
15+ different timeout patterns with varying timeout values:
- `timeout=5`, `timeout=10`, `timeout=15`, `timeout=2.0`, `timeout=1.0`

**No consistency** in timeout duration for similar operations.

### Recommendation:
Create timeout constants configuration.

**Proposed Solution**:
```python
# backend/utils/timeout_config.py
from dataclasses import dataclass

@dataclass
class TimeoutConfig:
    """Centralized timeout configurations."""
    REDIS_GET: float = 2.0
    REDIS_SET: float = 2.0
    LLM_REQUEST: float = 15.0
    KB_SEARCH: float = 10.0
    PROCESS_WAIT: float = 5.0
    MCP_TASK: float = 10.0

timeouts = TimeoutConfig()

# Usage:
response = await asyncio.wait_for(
    llm_task,
    timeout=timeouts.LLM_REQUEST
)
```

**Benefits**:
- Consistent timeout values
- Single place to tune performance
- Self-documenting code
- Easy to adjust based on environment

---

## Pattern 5: Duplicated Logging Patterns (LOW PRIORITY)

### Current State:
Inconsistent logging patterns:
- `logger.error(f"Failed to {operation}: {e}")`
- `logger.warning(f"[DEBUG] ...")`
- Mix of log levels for similar operations

### Recommendation:
Standardize logging patterns and remove debug logs in production code.

**Proposed Solution**:
```python
# Use structured logging
logger.error(
    "Operation failed",
    extra={
        "operation": "fetch_data",
        "error": str(e),
        "user_id": user_id
    }
)
```

---

## Recommended Refactoring Priority

### Phase 1 (High Impact):
1. ✅ **DONE**: Chat integration helper method (`_save_command_to_chat()`)
2. **TODO**: Create centralized error handler decorator
3. **TODO**: Implement Redis helper class

### Phase 2 (Code Quality):
4. **TODO**: Move inline imports to module level
5. **TODO**: Create timeout configuration
6. **TODO**: Standardize logging patterns

### Phase 3 (Architecture):
7. **TODO**: Create base API router with error handling
8. **TODO**: Implement request/response interceptors
9. **TODO**: Add centralized metrics collection

---

## Estimated Impact

### Code Reduction:
- **Phase 1**: ~400 lines of duplicated error handling → ~50 lines of reusable utilities
- **Phase 2**: ~100 lines of duplicated imports/config → ~30 lines centralized
- **Total**: ~450 lines reduction (~15% of backend code)

### Maintainability:
- Single source of truth for common patterns
- Easier onboarding for new developers
- Consistent behavior across all endpoints
- Simplified testing (test utilities once)

### Performance:
- Reduced import overhead (inline imports eliminated)
- Consistent timeout handling prevents hanging requests
- Better error tracking and debugging

---

## Implementation Plan

### Week 1: High-Priority Refactoring
- [ ] Create `backend/utils/error_handlers.py`
- [ ] Migrate 10 endpoints to use decorator (pilot)
- [ ] Measure error tracking improvements
- [ ] Migrate remaining endpoints

### Week 2: Code Quality
- [ ] Move all inline imports to module level
- [ ] Create timeout configuration
- [ ] Implement Redis helper class
- [ ] Update knowledge.py to use Redis helper

### Week 3: Testing & Documentation
- [ ] Add tests for new utilities
- [ ] Update developer documentation
- [ ] Code review and refinement

---

## Conclusion

The codebase has significant opportunities for reducing duplication and improving maintainability. The proposed refactoring will:

1. **Reduce code by ~15%** (450+ lines)
2. **Improve consistency** across all API endpoints
3. **Simplify debugging** with centralized error handling
4. **Enhance performance** by eliminating inline imports
5. **Make future changes easier** with single source of truth

**Next Steps**: Prioritize Phase 1 items and implement incrementally with proper testing.
