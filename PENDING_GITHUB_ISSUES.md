# Pending GitHub Issues

This file tracks issues that should be created in GitHub when access is available.

## Issue 1: Monitor Week 1 Database Initialization Progress

**Title:** Monitor Week 1 Database Initialization - 3 agents running (22h estimated)

**Priority:** High

**Labels:** `task`, `week-1`, `database`, `monitoring`

**Description:**

### Background
Week 1 Database Initialization task (#145) is currently being executed by 3 background agents with an estimated completion time of 22 hours.

### Current Status
- **Agents Running:** 3 (background execution)
- **Estimated Time:** 22 hours
- **Started:** [Insert start timestamp when known]
- **Expected Completion:** [Insert completion timestamp]

### Monitoring Requirements
1. Check agent progress every 2-4 hours
2. Verify no agents have stalled or failed
3. Monitor system resources (CPU, memory) during execution
4. Review agent outputs for errors or warnings

### Completion Criteria
- [ ] All 3 agents complete successfully
- [ ] Database initialization verified
- [ ] No errors in agent logs
- [ ] Database integrity checks pass

### Related Issues
- #145 - Week 1 Database Initialization (parent task)

---

## Issue 2: Migrate Windows NPU Worker to Connection Pooling Redis Pattern

**Title:** Migrate Windows NPU Worker to use connection pooling Redis pattern

**Priority:** Medium

**Labels:** `bug`, `redis`, `windows-npu-worker`, `technical-debt`

**Description:**

### Current Problem

The Windows NPU worker creates Redis clients with direct `redis.Redis()` instantiation without connection pooling:

**File:** `resources/windows-npu-worker/app/npu_worker.py:304`

```python
async def initialize_redis(self):
    """Initialize Redis connection"""
    try:
        import redis.asyncio as redis
        self.redis_client = redis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            decode_responses=True
        )
        await self.redis_client.ping()
        logger.info("Connected to Redis")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        self.redis_client = None
```

### Why This Is a Problem

- **No connection pooling** - Creates new connections inefficiently
- **No retry logic** - Fails immediately on connection errors
- **No health monitoring** - Doesn't track connection health
- **Missing config params** - Doesn't use available config settings from `npu_worker.yaml`

### Available Config (npu_worker.yaml)

The configuration file already has comprehensive Redis settings:

```yaml
redis:
  host: "172.16.168.23"
  port: 6379
  db: 0
  max_connections: 20
  socket_timeout: 5
  socket_connect_timeout: 2
  retry_on_timeout: true
```

### Special Considerations

1. **Standalone Deployment** - Windows NPU worker is a standalone application
2. **Cannot import from src.utils** - Has separate requirements.txt
3. **Needs local utility** - Create `resources/windows-npu-worker/app/utils/redis_client.py`

### Recommended Solution

Create a standalone Redis client utility within the Windows NPU worker that:

1. **Implements connection pooling** using config values
2. **Adds retry logic** for resilient connections
3. **Uses all config parameters** from `npu_worker.yaml`
4. **Follows same pattern** as main codebase `src.utils.redis_client.get_redis_client()`

### Implementation Steps

1. Create `resources/windows-npu-worker/app/utils/__init__.py`
2. Create `resources/windows-npu-worker/app/utils/redis_client.py` with:
   - `get_redis_client()` function
   - Connection pooling (using `max_connections` config)
   - Timeout handling (using `socket_timeout`, `socket_connect_timeout` config)
   - Retry logic (using `retry_on_timeout` config)
   - Health monitoring
3. Update `npu_worker.py::initialize_redis()` to use the new utility
4. Test on Windows deployment

### Example Implementation

```python
# resources/windows-npu-worker/app/utils/redis_client.py
import redis.asyncio as redis
from typing import Optional
import logging

logger = logging.getLogger(__name__)

async def get_redis_client(config: dict) -> Optional[redis.Redis]:
    """
    Create Redis client with connection pooling and retry logic

    Args:
        config: Redis configuration from npu_worker.yaml

    Returns:
        Redis client or None if connection fails
    """
    try:
        pool = redis.ConnectionPool(
            host=config.get('host', '172.16.168.23'),
            port=config.get('port', 6379),
            db=config.get('db', 0),
            max_connections=config.get('max_connections', 20),
            socket_timeout=config.get('socket_timeout', 5),
            socket_connect_timeout=config.get('socket_connect_timeout', 2),
            retry_on_timeout=config.get('retry_on_timeout', True),
            decode_responses=True
        )

        client = redis.Redis(connection_pool=pool)

        # Test connection
        await client.ping()
        logger.info("✅ Connected to Redis with connection pooling")

        return client
    except Exception as e:
        logger.error(f"❌ Failed to connect to Redis: {e}")
        return None
```

### Testing

After implementation, test:
1. Connection pooling works correctly
2. Retry logic handles temporary failures
3. Timeouts are respected
4. All config parameters are used
5. Windows deployment works correctly

### Related Issues

- #89 - Migrate 15+ files from direct Redis to get_redis_client() (parent issue)

### Progress Status

- ✅ All production code in `src/` directory - CLEAN
- ✅ All production code in `backend/` directory - CLEAN
- ✅ Monitoring scripts - MIGRATED (commit 29f6a8f)
- ⏸️ Windows NPU worker - **Pending this issue**

---

## Instructions for Creating These Issues

When GitHub access is available, create these issues using:

```bash
# Issue 1
gh issue create \
  --title "Monitor Week 1 Database Initialization - 3 agents running (22h estimated)" \
  --body-file <(sed -n '/## Issue 1/,/^---$/p' PENDING_GITHUB_ISSUES.md) \
  --label "task,week-1,database,monitoring"

# Issue 2
gh issue create \
  --title "Migrate Windows NPU Worker to use connection pooling Redis pattern" \
  --body-file <(sed -n '/## Issue 2/,/^---$/p' PENDING_GITHUB_ISSUES.md) \
  --label "bug,redis,windows-npu-worker,technical-debt"
```

Or create manually through GitHub web interface using the descriptions above.

---

**Created:** 2025-11-18
**Status:** Pending GitHub access restoration
