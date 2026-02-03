# ADR-002: Redis Database Separation Strategy

## Status

**Status**: Accepted

## Date

**Date**: 2025-01-01

## Context

AutoBot uses Redis for multiple purposes:
- Vector storage for knowledge base (LlamaIndex)
- Session management
- Caching
- Message queues
- Configuration storage
- Analytics data

Initially, all data was stored in Redis database 0, which caused:
1. **Data conflicts**: Different services could overwrite each other's keys
2. **Maintenance difficulty**: Couldn't flush cache without losing vectors
3. **Backup complexity**: All-or-nothing backup strategy
4. **Performance impact**: Large vector scans affected cache performance

## Decision

We implement a named database abstraction layer that maps logical database names to Redis database numbers:

| Database Name | Redis DB | Purpose |
|---------------|----------|---------|
| `main` | 0 | General cache, queues, sessions |
| `knowledge` | 1 | Knowledge base vectors (LlamaIndex) |
| `prompts` | 2 | LLM prompts and templates |
| `analytics` | 3 | Analytics and metrics data |

Access is through a canonical utility function that enforces consistent usage:

```python
from src.utils.redis_client import get_redis_client

# Get client for specific database
client = get_redis_client(async_client=False, database="knowledge")
```

### Alternatives Considered

1. **Single Database with Key Prefixes**
   - Pros: Simple, no configuration needed
   - Cons: Can't flush specific data types, SCAN operations slower

2. **Separate Redis Instances**
   - Pros: Complete isolation, independent scaling
   - Cons: More memory overhead, port management complexity

3. **Redis Cluster**
   - Pros: Industry standard, automatic sharding
   - Cons: Overkill for current scale, complex setup

4. **Named Database Abstraction (Chosen)**
   - Pros: Logical separation, can flush by purpose, simple implementation
   - Cons: Limited to 16 databases, still shares memory

## Consequences

### Positive

- **Data Isolation**: Can flush cache (db0) without losing vectors (db1)
- **Self-Documenting Code**: `database="knowledge"` is clearer than `db=1`
- **Selective Backup**: Can backup knowledge base separately
- **Performance**: Vector scans don't affect cache operations
- **Maintenance**: Clear separation of concerns

### Negative

- **Migration Required**: Existing data needed migration
- **16 Database Limit**: Redis limits to 16 databases (0-15)
- **Memory Shared**: All databases still share Redis memory

### Neutral

- Requires developers to always use `get_redis_client()` utility
- Database mapping is centralized in one location

## Implementation Notes

### Key Files

- `src/utils/redis_client.py` - Canonical Redis client utility
- `src/utils/distributed_redis_client.py` - Distributed Redis operations
- `scripts/migrate_redis_databases.py` - Database migration script
- `scripts/analysis/check_all_redis_dbs.py` - Database analysis tool

### Database Mapping

```python
# src/utils/redis_client.py
REDIS_DATABASE_MAP = {
    "main": 0,
    "knowledge": 1,
    "prompts": 2,
    "analytics": 3,
}
```

### Usage Pattern

```python
from src.utils.redis_client import get_redis_client

# Synchronous client
redis_client = get_redis_client(async_client=False, database="main")

# Async client
async_redis = await get_redis_client(async_client=True, database="knowledge")

# FORBIDDEN - Never instantiate directly
import redis
client = redis.Redis(host="172.16.168.23", db=0)  # DON'T DO THIS
```

### Migration Script

```bash
# Analyze current database distribution
python scripts/analysis/check_all_redis_dbs.py

# Migrate data between databases
python scripts/migrate_redis_databases.py --from 0 --to 1 --pattern "llama_index/*"
```

### Backup Strategy

```bash
# Backup specific database
redis-cli -h 172.16.168.23 -n 1 --rdb knowledge_backup.rdb

# Backup all databases
redis-cli -h 172.16.168.23 BGSAVE
```

## Related ADRs

- [ADR-001](001-distributed-vm-architecture.md) - Redis runs on VM3 (172.16.168.23)

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
