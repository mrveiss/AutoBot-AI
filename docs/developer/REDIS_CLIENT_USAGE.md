# Redis Client Usage Guide

**Status**: 🔴 MANDATORY PATTERN - Always use canonical Redis utility

This guide provides detailed implementation instructions for the **ALWAYS USE CANONICAL REDIS UTILITY** policy.

> **⚠️ MANDATORY RULE**: ALWAYS use `src/utils/redis_client.py::get_redis_client()`

---

## 🎯 Canonical Redis Client Pattern

### Quick Start

```python
# ✅ CORRECT - Use canonical utility
from src.utils.redis_client import get_redis_client

# Get synchronous client for 'main' database
redis_client = get_redis_client(async_client=False, database="main")

# Get async client for 'knowledge' database
async_redis = await get_redis_client(async_client=True, database="knowledge")
```

### Why This Pattern?

**Benefits**:
- ✅ **Centralized configuration** - Single source of truth
- ✅ **Connection pooling** - Automatic resource management
- ✅ **Database separation** - Named databases (self-documenting)
- ✅ **Network abstraction** - Uses `NetworkConstants` internally
- ✅ **DRY principle** - No duplicate connection code

**Problems it solves**:
- ❌ Configuration drift across files
- ❌ Connection leaks from improper cleanup
- ❌ Unclear database purposes (db0, db1, db2?)
- ❌ Hardcoded IPs/ports scattered everywhere

---

## ❌ FORBIDDEN PATTERNS

### Direct Redis Instantiation

**NEVER instantiate Redis directly** - Violates DRY principle and causes configuration drift:

```python
# ❌ WRONG - Direct instantiation (67 files still violate this!)
import redis
client = redis.Redis(host="172.16.168.23", port=6379, db=0)

# ❌ WRONG - Custom connection pooling
pool = redis.ConnectionPool(host="172.16.168.23", port=6379, max_connections=10)
client = redis.Redis(connection_pool=pool)

# ❌ WRONG - Direct StrictRedis
from redis import StrictRedis
client = StrictRedis(host="172.16.168.23", port=6379)
```

### Deprecated Utilities

**NEVER use these archived utilities** (archived 2025-10-26):

```python
# ❌ WRONG - Using deprecated utilities
from src.utils.redis_consolidated import ...  # Archived: 521 lines, 0 users
from src.utils.redis_database_manager_fixed import ...  # Archived: Temporary patch
from src.utils.redis_helper import ...  # Low priority: Only 1 test uses it
```

**Archive location**: `archives/code/redis-utilities-2025-10-26/`

---

## 📚 Database Separation

### Named Databases

**Use named databases** instead of DB numbers for self-documenting code:

```python
# ✅ CORRECT - Named databases (self-documenting)
from src.utils.redis_client import get_redis_client

main_db = get_redis_client(database="main")          # General cache/queues
knowledge_db = get_redis_client(database="knowledge")  # Knowledge base vectors
prompts_db = get_redis_client(database="prompts")     # LLM prompts/templates
analytics_db = get_redis_client(database="analytics")  # Analytics data

# ❌ WRONG - Database numbers (unclear purpose)
import redis
db0 = redis.Redis(host="172.16.168.23", db=0)  # What is this for?
db1 = redis.Redis(host="172.16.168.23", db=1)  # What is this for?
db2 = redis.Redis(host="172.16.168.23", db=2)  # What is this for?
```

### Standard Database Names

| Database Name | Redis DB # | Purpose |
|--------------|------------|---------|
| `main` | 0 | General cache, queues, session data |
| `knowledge` | 1 | Knowledge base vectors, embeddings |
| `prompts` | 2 | LLM prompts, templates, system messages |
| `analytics` | 3 | Analytics data, metrics, telemetry |
| `cache` | 4 | Temporary cache, short-lived data |

**When to create new databases**:
- Clear functional separation needed
- Different data lifecycles (TTL policies)
- Isolate critical data from cache data

---

## 🔧 Advanced Usage

### Synchronous vs Async Clients

```python
from src.utils.redis_client import get_redis_client

# Synchronous client (for regular functions)
def cache_data(key, value):
    redis_client = get_redis_client(async_client=False, database="main")
    redis_client.set(key, value, ex=3600)  # 1 hour TTL
    return redis_client.get(key)

# Async client (for async functions)
async def cache_data_async(key, value):
    redis_client = await get_redis_client(async_client=True, database="main")
    await redis_client.set(key, value, ex=3600)
    return await redis_client.get(key)
```

### Connection Pooling

**Connection pooling is automatic** - handled by `get_redis_client()`:

```python
# ✅ CORRECT - Pooling handled automatically
from src.utils.redis_client import get_redis_client

# Each call reuses existing connection pool
redis1 = get_redis_client(database="main")
redis2 = get_redis_client(database="main")  # Reuses pool
redis3 = get_redis_client(database="knowledge")  # Different pool
```

**Do NOT create custom pools**:
```python
# ❌ WRONG - Custom pooling (defeats the purpose)
import redis
pool = redis.ConnectionPool(host="...", port=..., max_connections=10)
client = redis.Redis(connection_pool=pool)
```

### Error Handling

```python
from src.utils.redis_client import get_redis_client
import redis

def safe_redis_operation():
    try:
        redis_client = get_redis_client(database="main")
        result = redis_client.get("some_key")
        return result
    except redis.ConnectionError as e:
        # Handle connection issues
        logger.error(f"Redis connection error: {e}")
        return None
    except redis.TimeoutError as e:
        # Handle timeout issues
        logger.error(f"Redis timeout: {e}")
        return None
    except Exception as e:
        # Handle other Redis errors
        logger.error(f"Redis error: {e}")
        return None
```

---

## 🏗️ Backend Infrastructure

### Component Overview

| Component | Location | Purpose | Usage |
|-----------|----------|---------|-------|
| **`redis_client.py`** | `src/utils/` | High-level API | 66 files use this ✅ |
| **`redis_database_manager.py`** | `src/utils/` | Backend pooling | 28 files use this |
| **`NetworkConstants`** | `src/constants/` | IP/Port config | Provides `REDIS_VM_IP` and `REDIS_PORT` |

### How It Works

```
┌─────────────────┐
│   Your Code     │
└────────┬────────┘
         │ get_redis_client(database="main")
         ▼
┌─────────────────┐
│ redis_client.py │ (High-level API)
└────────┬────────┘
         │ Uses NetworkConstants for IP/port
         ▼
┌──────────────────────────┐
│ redis_database_manager.py │ (Connection pooling)
└────────┬─────────────────┘
         │ Manages connection pools
         ▼
┌─────────────────┐
│  Redis Server   │ (172.16.168.23:6379)
└─────────────────┘
```

### NetworkConstants Integration

The canonical utility uses `NetworkConstants` internally:

```python
# Inside redis_client.py (you don't need to do this manually)
from src.constants.network_constants import NetworkConstants

# Automatic - no hardcoded IPs!
redis_host = NetworkConstants.REDIS_VM_IP  # 172.16.168.23
redis_port = NetworkConstants.REDIS_PORT    # 6379
```

---

## 📊 Migration Status

### Current State (as of 2025-10-26)

| Status | Files | Pattern |
|--------|-------|---------|
| ✅ **Correct** | 66 files | Use `get_redis_client()` |
| ❌ **Violating** | 67 files | Use direct `redis.Redis()` instantiation |
| 📋 **Plan** | 5 phases | Stored in Memory MCP entity |

### Migration Plan Reference

**Stored in Memory MCP**: Entity name "Redis Utilities Audit 2025-10-26"

**Search before refactoring**:
```bash
mcp__memory__search_nodes --query "Redis Utilities Audit"
```

### When Refactoring Redis Code

**Required steps**:

1. **Search Memory MCP** for "Redis Utilities Audit" before starting
2. **Use `get_redis_client()`** for all new Redis connections
3. **Replace direct instantiation** patterns during code changes
4. **Reference archived utilities README** for migration guidance

**Example refactoring**:

```python
# ❌ BEFORE (direct instantiation)
import redis

class MyService:
    def __init__(self):
        self.redis = redis.Redis(host="172.16.168.23", port=6379, db=0)

    def cache_data(self, key, value):
        self.redis.set(key, value)

# ✅ AFTER (canonical utility)
from src.utils.redis_client import get_redis_client

class MyService:
    def __init__(self):
        self.redis = get_redis_client(database="main")

    def cache_data(self, key, value):
        self.redis.set(key, value)
```

---

## 🔍 Finding Violations

### Grep for Direct Instantiation

```bash
# Find files using direct Redis instantiation
grep -r "redis.Redis(" --include="*.py" .

# Find imports of redis module (potential violations)
grep -r "import redis$" --include="*.py" .
grep -r "from redis import" --include="*.py" .

# Find deprecated utility usage
grep -r "redis_consolidated" --include="*.py" .
grep -r "redis_database_manager_fixed" --include="*.py" .
```

### Check File Usage

```bash
# Check which files import deprecated utilities
grep -l "from src.utils.redis_consolidated" **/*.py
grep -l "from src.utils.redis_database_manager_fixed" **/*.py

# Check which files correctly use get_redis_client
grep -l "from src.utils.redis_client import get_redis_client" **/*.py
```

---

## ✅ Best Practices

### 1. Always Use Canonical Utility

```python
# ✅ DO THIS
from src.utils.redis_client import get_redis_client
redis_client = get_redis_client(database="main")

# ❌ NOT THIS
import redis
redis_client = redis.Redis(host="...", port=...)
```

### 2. Use Named Databases

```python
# ✅ DO THIS - Clear purpose
knowledge_db = get_redis_client(database="knowledge")
cache_db = get_redis_client(database="cache")

# ❌ NOT THIS - Unclear purpose
db1 = get_redis_client(database="db1")  # What is this?
db2 = get_redis_client(database="db2")  # What is this?
```

### 3. Let Connection Pooling Work

```python
# ✅ DO THIS - Reuse connections
def my_function():
    redis_client = get_redis_client(database="main")
    # Use client...

# ❌ NOT THIS - Custom pooling
def my_function():
    pool = redis.ConnectionPool(...)  # Don't do this!
    redis_client = redis.Redis(connection_pool=pool)
```

### 4. Handle Errors Properly

```python
# ✅ DO THIS - Proper error handling
try:
    redis_client = get_redis_client(database="main")
    result = redis_client.get(key)
except redis.ConnectionError:
    logger.error("Redis connection failed")
    # Handle gracefully

# ❌ NOT THIS - Ignore errors
redis_client = get_redis_client(database="main")
result = redis_client.get(key)  # What if connection fails?
```

---

## 🐛 Troubleshooting

### Connection Refused

**Issue**: `redis.exceptions.ConnectionRefusedError`

**Solution**:
```bash
# Check Redis VM is running
ssh autobot@172.16.168.23 "systemctl status redis"

# Check Redis is listening
redis-cli -h 172.16.168.23 ping
# Should return: PONG

# Verify NetworkConstants
python3 -c "from src.constants.network_constants import NetworkConstants; print(NetworkConstants.REDIS_VM_IP)"
```

### Connection Timeout

**Issue**: `redis.exceptions.TimeoutError`

**Solution**:
```bash
# Check network connectivity
ping 172.16.168.23

# Check Redis configuration
ssh autobot@172.16.168.23 "cat /etc/redis/redis.conf | grep bind"
# Should bind to 0.0.0.0 or 172.16.168.23

# Check timeout settings
ssh autobot@172.16.168.23 "cat /etc/redis/redis.conf | grep timeout"
```

### Database Number Confusion

**Issue**: Not sure which database to use

**Solution**: Use named databases and check the table in "Database Separation" section above. If creating new purpose, add to the table.

---

## 📚 Related Documentation

- **Network Constants**: `src/constants/network_constants.py`
- **Redis Database Manager**: `src/utils/redis_database_manager.py`
- **Hardcoding Prevention**: `docs/developer/HARDCODING_PREVENTION.md`
- **Infrastructure Setup**: `docs/developer/INFRASTRUCTURE_DEPLOYMENT.md`

---

## 🎯 Summary Checklist

**Before writing Redis code**:
- [ ] Import `get_redis_client` from `src.utils.redis_client`
- [ ] Use named database (not db numbers)
- [ ] Use async_client parameter correctly (True for async, False for sync)
- [ ] Add proper error handling

**When refactoring existing code**:
- [ ] Search Memory MCP for "Redis Utilities Audit"
- [ ] Replace direct `redis.Redis()` with `get_redis_client()`
- [ ] Replace db numbers with named databases
- [ ] Remove custom connection pooling
- [ ] Test thoroughly after changes

**Avoid**:
- [ ] No direct `redis.Redis()` instantiation
- [ ] No custom connection pools
- [ ] No deprecated utilities (redis_consolidated, etc.)
- [ ] No hardcoded IPs/ports
- [ ] No database numbers (use names)

---
