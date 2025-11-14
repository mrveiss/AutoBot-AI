# Redis Consolidation Migration Guide

**Date**: 2025-11-14
**Status**: Complete - All 5 Redis managers consolidated
**Canonical Implementation**: `src/utils/redis_client.py`

---

## Overview

This guide helps you migrate from the **5 archived Redis manager implementations** to the canonical `src/utils/redis_client.py`.

**Why migrate?**
- ✅ Single source of truth for Redis connections
- ✅ All 17 unique features preserved from all 5 implementations
- ✅ Circuit breaker, retry logic, connection pooling
- ✅ "Loading dataset" handling for production stability
- ✅ TCP keepalive tuning prevents connection drops
- ✅ Comprehensive statistics and monitoring

**Archive location**: `archives/2025-11-11_redis_consolidation/`

---

## Quick Migration (TL;DR)

### Before (any of 5 old managers)
\`\`\`python
from backend.utils.async_redis_manager import AsyncRedisManager
from src.utils.redis_database_manager import get_redis_database
from src.utils.redis_helper import get_redis_connection

# Old patterns varied across 5 implementations
\`\`\`

### After (canonical)
\`\`\`python
from src.utils.redis_client import get_redis_client

# Simple usage - synchronous
client = get_redis_client(async_client=False, database="main")

# Simple usage - asynchronous
client = await get_redis_client(async_client=True, database="knowledge")
\`\`\`

---

## Migration Patterns

### 1. From \`backend/utils/async_redis_manager.py\`

**Archived**: \`archives/2025-11-11_redis_consolidation/async_redis_manager.py\`

#### Old Code
\`\`\`python
from backend.utils.async_redis_manager import AsyncRedisManager

# Initialize manager
manager = AsyncRedisManager()
await manager.initialize()

# Get specific database
client = await manager.main()
client = await manager.knowledge()
client = await manager.prompts()

# Use pipeline
async with manager.pipeline() as pipe:
    pipe.set("key", "value")
    await pipe.execute()
\`\`\`

#### New Code
\`\`\`python
from src.utils.redis_client import get_redis_client, RedisConnectionManager

# Simple usage (recommended)
main_client = await get_redis_client(async_client=True, database="main")
knowledge_client = await get_redis_client(async_client=True, database="knowledge")
prompts_client = await get_redis_client(async_client=True, database="prompts")

# Advanced usage (if you need manager features)
manager = RedisConnectionManager()
client = await manager.main()

# Pipeline
client = await get_redis_client(async_client=True, database="main")
async with client.pipeline() as pipe:
    pipe.set("key", "value")
    await pipe.execute()
\`\`\`

**What changed?**
- ✅ No separate \`initialize()\` required - handled automatically
- ✅ All features preserved ("Loading dataset" wait, tenacity retry, WeakSet tracking)
- ✅ Same named database methods (\`main()\`, \`knowledge()\`, \`prompts()\`)
- ✅ Same pipeline support

---

### 2. From \`src/utils/async_redis_manager.py\`

**Archived**: \`archives/2025-11-11_redis_consolidation/async_redis_manager_src.py\`

#### Old Code
\`\`\`python
from src.utils.async_redis_manager import AsyncRedisManager

manager = AsyncRedisManager(host="172.16.168.23", port=6379)
await manager.connect()
client = manager.client
\`\`\`

#### New Code
\`\`\`python
from src.utils.redis_client import get_redis_client

client = await get_redis_client(
    async_client=True,
    database="main",  # or whichever database you need
    host="172.16.168.23",  # optional - uses NetworkConstants.REDIS_VM_IP by default
    port=6379  # optional - uses default
)
\`\`\`

**What changed?**
- ✅ No separate \`connect()\` step - happens automatically
- ✅ Tenacity retry logic preserved
- ✅ Auto-reconnection on health check failure preserved

---

### 3. From \`src/utils/optimized_redis_manager.py\`

**Archived**: \`archives/2025-11-11_redis_consolidation/optimized_redis_manager.py\`

#### Old Code
\`\`\`python
from src.utils.optimized_redis_manager import OptimizedRedisManager

manager = OptimizedRedisManager()
client = manager.get_client(db=0)

# Check pool stats
stats = manager.get_pool_stats()
print(f"Available: {stats['available_connections']}")
\`\`\`

#### New Code
\`\`\`python
from src.utils.redis_client import get_redis_client, RedisConnectionManager

# Get client (TCP keepalive tuning applied automatically)
client = get_redis_client(async_client=False, database="main")

# Get pool stats (if using manager)
manager = RedisConnectionManager()
stats = manager.get_statistics()
\`\`\`

**What changed?**
- ✅ TCP keepalive tuning preserved and applied automatically
- ✅ Pool statistics available through \`get_statistics()\`
- ✅ Idle connection cleanup handled automatically

---

## Database Name Mapping

All 5 implementations supported these named databases:

| Database Name | DB Number | Purpose |
|--------------|-----------|---------|
| \`main\` | 0 | General cache/queues |
| \`knowledge\` | 1 | Knowledge base vectors |
| \`prompts\` | 2 | LLM prompts/templates |
| \`analytics\` | 3 | Analytics data |
| \`access_control\` | 4 | Permissions/roles |
| \`feature_flags\` | 5 | Feature toggles |
| \`conversations\` | 6 | Chat history |
| \`workflows\` | 7 | Workflow state |
| \`tasks\` | 8 | Task queue |
| \`locks\` | 9 | Distributed locks |

---

## Feature Comparison

All unique features from 5 implementations are **preserved**:

| Feature | Source | Status |
|---------|--------|--------|
| Circuit breaker | redis_client.py (original) | ✅ Preserved |
| "Loading dataset" handling | backend/async_redis_manager.py | ✅ CRITICAL |
| TCP keepalive tuning | optimized_redis_manager.py | ✅ CRITICAL |
| Tenacity retry library | backend/async_redis_manager.py | ✅ CRITICAL |
| Connection pooling (sync + async) | redis_client.py (original) | ✅ Preserved |
| RedisDatabase enum | redis_database_manager.py | ✅ Preserved |

Full feature matrix: See \`archives/2025-11-11_redis_consolidation/README.md\`

---

## Troubleshooting

### "Loading dataset in memory" Errors

The canonical implementation automatically waits (up to 60 seconds). No code changes needed.

### Connection Drops After Idle

TCP keepalive tuning is automatically applied. No configuration needed.

### Import Errors

Update to canonical imports:

\`\`\`python
# ❌ Old (deprecated)
from backend.utils.async_redis_manager import AsyncRedisManager

# ✅ New (canonical)
from src.utils.redis_client import get_redis_client
\`\`\`

---

## Verification Checklist

- [ ] All imports updated to \`from src.utils.redis_client import ...\`
- [ ] \`get_redis_client()\` used instead of old manager classes
- [ ] Database names specified correctly
- [ ] Async/sync mode specified with \`async_client\` parameter
- [ ] Tests passing
- [ ] No deprecated warnings in logs

---

## Support

- Archive README: \`archives/2025-11-11_redis_consolidation/README.md\`
- Code Review: \`reports/code-review/REDIS_CONSOLIDATION_CODE_REVIEW.md\`
- Canonical Implementation: \`src/utils/redis_client.py\`
- GitHub Issue: #36

**Status**: ✅ Production Ready - All Features Preserved
