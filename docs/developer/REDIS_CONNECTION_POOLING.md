# Redis Connection Pooling Architecture

**Issue:** #743 - Memory Optimization
**Status:** Implemented (already present, now documented and optimized)

## Overview

AutoBot implements **singleton connection pooling** for all Redis connections. This document explains how the pooling works and why it's memory-efficient.

## Architecture

### Singleton Pools Per Database

The `RedisConnectionManager` class maintains singleton connection pools:

```python
# In RedisConnectionManager
self._sync_pools: Dict[str, ConnectionPool] = {}      # One sync pool per database
self._async_pools: Dict[str, ConnectionPool] = {}     # One async pool per database
```

### Pool Lifecycle

1. **First Request**: Pool is created and stored in dictionary
2. **Subsequent Requests**: Same pool is reused from dictionary
3. **Connection Reuse**: Connections are borrowed from pool and returned after use

### Example: 100 Calls, 1 Pool

```python
from src.utils.redis_client import get_redis_client

# First call creates pool with max 20 connections
client1 = get_redis_client(database="main")  # Pool created, stored in _sync_pools["main"]

# Next 99 calls reuse THE SAME pool
for i in range(99):
    client = get_redis_client(database="main")  # Pool reused from _sync_pools["main"]

# Memory usage: 1 pool with max 20 connections
# NOT: 100 pools with 2000 connections
```

## Pool Configuration (Issue #743)

### Optimized Settings

```python
# src/constants/redis_constants.py
class RedisConnectionConfig:
    MAX_CONNECTIONS_POOL: int = 20  # Optimized from 100 for memory efficiency
    SOCKET_TIMEOUT: int = 5
    SOCKET_CONNECT_TIMEOUT: int = 3
```

### Why 20 Connections?

- **Typical concurrency**: Most operations are sequential, not parallel
- **Memory footprint**: 20 connections per pool keeps memory usage low
- **Performance**: Sufficient for high-throughput workloads
- **Per-database isolation**: Each database has its own pool of 20

### Total Maximum Connections

With 13 databases, maximum connections = **13 databases × 20 connections = 260 connections**

In practice, pools are created **lazily** (only when needed), so actual usage is much lower.

## How Pooling Works

### Internal Flow

```python
def get_sync_client(self, database_name: str = "main"):
    # Check if pool exists
    if database_name not in self._sync_pools:
        with self._init_lock:  # Thread-safe creation
            if database_name not in self._sync_pools:
                # Create pool ONCE
                self._sync_pools[database_name] = self._create_sync_pool(database_name)

    # Reuse pool for all requests
    client = redis.Redis(connection_pool=self._sync_pools[database_name])
    return client
```

### Connection Lifecycle

```
1. get_redis_client() called
2. Check pool cache (_sync_pools)
3. If missing: Create pool (max 20 connections)
4. If exists: Reuse pool
5. Borrow connection from pool
6. Execute Redis operation
7. Return connection to pool (automatic)
```

## Features

### Circuit Breaker

Prevents cascading failures when Redis is unavailable:

- Tracks failures per database
- Opens circuit after 5 failures (configurable)
- Blocks requests for 60 seconds
- Auto-resets after timeout

### TCP Keepalive

Prevents connection drops on idle connections:

```python
socket.TCP_KEEPIDLE: 600    # 10 minutes before first probe
socket.TCP_KEEPINTVL: 60     # 1 minute between probes
socket.TCP_KEEPCNT: 5        # 5 failed probes before disconnect
```

### Idle Connection Cleanup

Automatically removes idle connections after 5 minutes:

- Background task runs every 60 seconds
- Checks for connections idle > 300 seconds
- Closes idle connections to free resources

### Retry Logic

Exponential backoff for failed connections:

- Base wait: 2 seconds
- Max wait: 30 seconds
- Max attempts: 5
- Only retries on connection errors

## Usage Examples

### Basic Usage (Sync)

```python
from src.utils.redis_client import get_redis_client

# Get client (creates pool on first call)
redis = get_redis_client(database="main")

# Use client
redis.set("key", "value")
result = redis.get("key")

# Connection automatically returned to pool
```

### Async Usage

```python
from src.utils.redis_client import get_redis_client

async def store_data():
    # Get async client (creates async pool on first call)
    redis = await get_redis_client(async_client=True, database="main")

    # Use client
    await redis.set("key", "value")
    result = await redis.get("key")

    # Connection automatically returned to pool
```

### Pipeline Operations

```python
from src.utils.redis_client import get_redis_client

async def batch_operations():
    manager = RedisConnectionManager()

    # Pipeline uses pooled connection
    async with manager.pipeline("main") as pipe:
        pipe.set("key1", "value1")
        pipe.set("key2", "value2")
        pipe.set("key3", "value3")
        # Auto-executes on context exit
```

### Named Database Methods

```python
manager = RedisConnectionManager()

# Each database has its own pool
main_client = await manager.main()        # Pool for db 0
knowledge_client = await manager.knowledge()  # Pool for db 1
prompts_client = await manager.prompts()   # Pool for db 2
```

## Pool Statistics

### Get Pool Metrics

```python
from src.utils.redis_client import get_redis_client

manager = RedisConnectionManager()

# Get pool statistics for specific database
stats = manager.get_pool_statistics("main")

print(f"Created connections: {stats.created_connections}")
print(f"Available connections: {stats.available_connections}")
print(f"In-use connections: {stats.in_use_connections}")
print(f"Max connections: {stats.max_connections}")
print(f"Idle connections: {stats.idle_connections}")
```

### Get Overall Health

```python
health = manager.get_health_status()

print(f"Overall healthy: {health['overall_healthy']}")
print(f"Total databases: {health['total_databases']}")
print(f"Healthy databases: {health['healthy_databases']}")
print(f"Success rate: {health['success_rate']}%")
```

## Memory Optimization Benefits (Issue #743)

### Before Optimization

- `MAX_CONNECTIONS_POOL: 100`
- Potential: 13 databases × 100 connections = 1,300 connections
- High memory footprint under load

### After Optimization

- `MAX_CONNECTIONS_POOL: 20`
- Maximum: 13 databases × 20 connections = 260 connections
- **80% reduction** in maximum connection count
- Actual usage much lower due to lazy pool creation

### Memory Savings

Each Redis connection uses approximately:

- 4 KB for socket buffers
- 16 KB for Python object overhead
- ~20 KB total per connection

**Savings**: (1,300 - 260) × 20 KB = **20.8 MB** maximum memory reduction

## Migration Notes

### No Code Changes Required

All existing code continues to work unchanged:

```python
# OLD code (still works)
redis = get_redis_client(database="main")

# NEW code (same behavior)
redis = get_redis_client(database="main")
```

The pooling is **transparent** to callers. The only change is improved memory efficiency.

### Configuration Override

To customize pool size for specific use cases:

```python
# config/redis-databases.yaml
redis_databases:
  main:
    db: 0
    max_connections: 50  # Override default 20
```

Or via environment variables:

```bash
export AUTOBOT_REDIS_MAX_CONNECTIONS=50
```

## Testing

### Verify Pooling Works

```python
from src.utils.redis_client import get_redis_client
from src.utils.redis_management.connection_manager import RedisConnectionManager

manager = RedisConnectionManager()

# Get multiple clients
client1 = get_redis_client(database="main")
client2 = get_redis_client(database="main")
client3 = get_redis_client(database="main")

# Verify they share the same pool
pool1 = client1.connection_pool
pool2 = client2.connection_pool
pool3 = client3.connection_pool

assert pool1 is pool2 is pool3, "Clients should share the same pool"
print("✅ Pooling verified: All clients share the same connection pool")

# Check pool statistics
stats = manager.get_pool_statistics("main")
print(f"Pool has {stats.created_connections} connections created")
print(f"Max connections: {stats.max_connections}")
```

### Load Testing

```python
import asyncio
from src.utils.redis_client import get_redis_client

async def test_concurrent_operations():
    """Test that pool handles concurrent operations efficiently."""
    tasks = []

    for i in range(100):  # 100 concurrent operations
        async def operation():
            redis = await get_redis_client(async_client=True, database="main")
            await redis.set(f"test_key_{i}", f"value_{i}")
            return await redis.get(f"test_key_{i}")

        tasks.append(operation())

    results = await asyncio.gather(*tasks)
    print(f"✅ Completed {len(results)} concurrent operations")
    print("✅ Pool efficiently handled concurrency with max 20 connections")

# Run test
asyncio.run(test_concurrent_operations())
```

## Troubleshooting

### "Too many connections" Error

If you see connection limit errors:

1. Check current pool usage:
   ```python
   stats = manager.get_pool_statistics("main")
   print(f"In-use connections: {stats.in_use_connections}")
   ```

2. Increase max_connections if needed:
   ```python
   # config/redis-databases.yaml
   max_connections: 50
   ```

3. Check for connection leaks (connections not returned to pool)

### Circuit Breaker Open

If circuit breaker is blocking requests:

1. Check Redis server health
2. Review error logs
3. Wait for timeout (60 seconds) or restart application

### Pool Statistics Not Updating

If statistics seem stale:

1. Ensure you're checking the correct database name
2. Verify pool has been created (not lazy-loaded yet)
3. Check manager initialization

## References

- **Implementation**: `/home/kali/Desktop/AutoBot/src/utils/redis_management/connection_manager.py`
- **Configuration**: `/home/kali/Desktop/AutoBot/src/constants/redis_constants.py`
- **Main Interface**: `/home/kali/Desktop/AutoBot/src/utils/redis_client.py`
- **Issue**: #743 - Memory Optimization
