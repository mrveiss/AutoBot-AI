# Async Redis Manager for AutoBot

This document describes the new async Redis connection manager that replaces the 2-second timeout workaround with a proper async implementation.

## Overview

The Async Redis Manager provides:

- **Fully async Redis operations** using `redis.asyncio`
- **Connection pooling** with proper lifecycle management
- **Circuit breaker pattern** for Redis failures
- **Health monitoring** with automatic recovery
- **Retry logic** with exponential backoff
- **Singleton pattern** to share connections across the app
- **Comprehensive error handling** and logging
- **Support for all Redis databases** (0-10) as defined in config

## Architecture

```
AsyncRedisManager (Singleton)
├── AsyncRedisDatabase (per database)
│   ├── Connection Pool
│   ├── Circuit Breaker
│   ├── Health Monitor
│   └── Statistics Tracking
├── Configuration Management
├── Database Factory
└── Health Monitoring
```

## Key Files

- **`async_redis_manager.py`** - Core async Redis manager implementation
- **`redis_compatibility.py`** - Backward compatibility layer for existing code
- **`test_async_redis_manager.py`** - Comprehensive test suite
- **`README_async_redis.md`** - This documentation

## Quick Start

### Basic Usage

```python
from backend.utils.async_redis_manager import get_redis_manager

# Get manager instance
manager = await get_redis_manager()

# Access specific databases
main_db = await manager.main()
knowledge_db = await manager.knowledge()
cache_db = await manager.cache()

# Basic operations
await main_db.set("key", "value", ex=60)
value = await main_db.get("key")
await main_db.delete("key")
```

### Using Convenience Functions

```python
from backend.utils.async_redis_manager import get_async_redis, redis_connection

# Get database directly
db = await get_async_redis("main")

# Using context manager
async with redis_connection("cache") as cache_db:
    await cache_db.set("session_key", "session_data", ex=3600)
    data = await cache_db.get("session_key")
```

### Pipeline Operations

```python
# Use pipelines for batch operations
async with main_db.pipeline() as pipe:
    pipe.set("key1", "value1")
    pipe.set("key2", "value2")
    pipe.expire("key1", 60)
    results = await pipe.execute()
```

## Supported Operations

### Basic Operations
- `get(key)` - Get value by key
- `set(key, value, ex=None, px=None, nx=False, xx=False)` - Set key-value pair
- `delete(*keys)` - Delete one or more keys
- `exists(*keys)` - Check if keys exist
- `expire(key, seconds)` - Set key expiration
- `ttl(key)` - Get key time to live
- `ping()` - Test connection

### Hash Operations
- `hget(name, key)` - Get hash field value
- `hset(name, key, value)` - Set hash field value
- `hgetall(name)` - Get all hash fields and values

### List Operations
- `lpush(name, *values)` - Push to list (left)
- `rpush(name, *values)` - Push to list (right)
- `lpop(name)` - Pop from list (left)
- `rpop(name)` - Pop from list (right)
- `llen(name)` - Get list length

### Set Operations
- `sadd(name, *values)` - Add to set
- `srem(name, *values)` - Remove from set
- `smembers(name)` - Get all set members
- `scard(name)` - Get set cardinality

### Advanced Operations
- `scan(cursor=0, match=None, count=None)` - Scan keys
- `info(section=None)` - Get server information
- `pipeline()` - Get pipeline context manager

## Circuit Breaker Pattern

The circuit breaker protects against cascade failures:

```python
# Circuit breaker states
CLOSED    -> Normal operation
OPEN      -> Failing fast (Redis unavailable)
HALF_OPEN -> Testing recovery
```

**Configuration:**
- `failure_threshold` - Failures before opening circuit (default: 5)
- `recovery_timeout` - Seconds before testing recovery (default: 60)
- `success_threshold` - Successes needed to close circuit (default: 2)

## Health Monitoring

Automatic health checks run every 30 seconds:

```python
# Get health status
health = await manager.health_check()
print(health['overall_healthy'])  # True/False
print(health['databases'])        # Per-database status
```

## Performance Features

### Connection Pooling
- Maximum 20 connections per database
- Automatic connection reuse
- Proper connection lifecycle management

### Retry Logic
- Exponential backoff (0.5s to 10s)
- Maximum 3 retry attempts
- Configurable per database

### Statistics Tracking
- Response time monitoring
- Success/failure counters
- Circuit breaker trip counts
- Moving average calculations

## Configuration

### Environment Variables

```bash
AUTOBOT_REDIS_HOST=localhost      # Redis host
AUTOBOT_REDIS_PORT=6379          # Redis port  
AUTOBOT_REDIS_PASSWORD=          # Redis password (if needed)
```

### YAML Configuration

The manager loads database configuration from `config/redis-databases.yaml`:

```yaml
redis_databases:
  main:
    db: 0
    description: "Main application data"
  knowledge:
    db: 1
    description: "Knowledge base and documents"
  # ... other databases
```

## Migration Guide

### From Old Sync Redis

**Before (blocking):**
```python
import redis
r = redis.Redis(host="localhost", port=6379, socket_timeout=30)
r.set("key", "value")
value = r.get("key")
```

**After (async):**
```python
from backend.utils.async_redis_manager import get_async_redis

db = await get_async_redis("main")
await db.set("key", "value")
value = await db.get("key")
```

### Using Compatibility Layer

For gradual migration, use the compatibility wrapper:

```python
from backend.utils.redis_compatibility import get_redis_client_compat

compat = get_redis_client_compat("main")

# New async way (preferred)
await compat.aset("key", "value")
value = await compat.aget("key")

# Old sync way (deprecated, shows warnings)
compat.set("key", "value")  # Will show deprecation warning
value = compat.get("key")   # Will show deprecation warning
```

## Error Handling

### Automatic Recovery
- Connection failures trigger circuit breaker
- Automatic retry with exponential backoff
- Health checks test recovery
- Graceful degradation during outages

### Exception Types
- `ConnectionError` - Redis server unavailable
- `TimeoutError` - Operation timeout
- `RedisError` - Redis protocol errors

### Best Practices

```python
try:
    db = await get_async_redis("main")
    await db.set("key", "value")
except ConnectionError:
    # Redis is unavailable - use fallback
    logger.error("Redis unavailable, using fallback storage")
    # Implement fallback logic
except TimeoutError:
    # Operation timed out - retry or fallback
    logger.warning("Redis operation timeout")
except Exception as e:
    # Unexpected error
    logger.error(f"Unexpected Redis error: {e}")
```

## Performance Optimization

### Use Pipelines for Batch Operations

```python
# Slow - individual operations
for i in range(100):
    await db.set(f"key_{i}", f"value_{i}")

# Fast - pipeline operations
async with db.pipeline() as pipe:
    for i in range(100):
        pipe.set(f"key_{i}", f"value_{i}")
    await pipe.execute()
```

### Connection Reuse

```python
# Good - reuse database connection
db = await manager.main()
for i in range(100):
    await db.get(f"key_{i}")

# Bad - new connection each time
for i in range(100):
    db = await get_async_redis("main")
    await db.get(f"key_{i}")
```

## Testing

### Run Comprehensive Tests

```bash
python test_async_redis_manager.py
```

### Test Individual Components

```python
# Test database operations
from backend.utils.async_redis_manager import AsyncRedisDatabase

db = AsyncRedisDatabase("test", 15)
await db.initialize()
await db.set("test", "value")
assert await db.get("test") == "value"

# Test migration readiness
from backend.utils.redis_compatibility import test_async_migration

results = await test_async_migration("main")
assert results['migration_ready']
```

## Monitoring and Debugging

### Get Statistics

```python
# Manager statistics
manager = await get_redis_manager()
stats = await manager.get_statistics()
print(f"Total databases: {stats['manager']['total_databases']}")

# Database statistics
main_db = await manager.main()
db_stats = main_db.get_stats()
print(f"Success rate: {db_stats['stats']['successful_operations']}")
print(f"Average response: {db_stats['stats']['average_response_time']}ms")
```

### Health Monitoring

```python
# Detailed health check
health = await manager.health_check()
for db_name, db_health in health['databases'].items():
    if not db_health['healthy']:
        print(f"Database {db_name} is unhealthy: {db_health.get('error')}")
```

### Debug Logging

```python
import logging
logging.getLogger('backend.utils.async_redis_manager').setLevel(logging.DEBUG)
```

## FastAPI Integration

The updated `fast_app_factory_fix.py` demonstrates integration:

```python
from backend.utils.async_redis_manager import get_redis_manager

@asynccontextmanager
async def create_lifespan_manager(app: FastAPI):
    # Initialize Redis manager
    redis_manager = await get_redis_manager()
    app.state.redis_manager = redis_manager
    
    yield
    
    # Cleanup on shutdown
    await redis_manager.close_all()

# Use in endpoints
@app.get("/api/data")
async def get_data():
    main_db = await app.state.redis_manager.main()
    return await main_db.get("data_key")
```

## Troubleshooting

### Common Issues

**Redis Connection Refused:**
```bash
# Check Redis is running
docker ps | grep redis
redis-cli ping

# Check configuration
cat config/redis-databases.yaml
```

**Circuit Breaker Open:**
```python
# Check circuit breaker status
db_stats = db.get_stats()
if db_stats['circuit_state'] == 'open':
    print("Circuit breaker is open - Redis may be down")
```

**High Response Times:**
```python
# Check performance statistics
stats = await manager.get_statistics()
for db_name, db_stats in stats['databases'].items():
    avg_time = db_stats['stats']['average_response_time']
    if avg_time > 100:  # ms
        print(f"Database {db_name} response time is high: {avg_time}ms")
```

### Performance Tuning

**Connection Pool Size:**
```python
# Increase for high-concurrency applications
database = AsyncRedisDatabase(
    name="high_traffic",
    db_number=1,
    max_connections=50  # Default: 20
)
```

**Timeout Configuration:**
```python
# Adjust for network conditions
database = AsyncRedisDatabase(
    name="slow_network",
    db_number=1,
    connection_timeout=10.0,  # Default: 5.0
    socket_timeout=10.0       # Default: 5.0
)
```

## Security Considerations

### Password Protection
```yaml
# config/redis-databases.yaml
password: your_redis_password_here
```

### Network Security
- Use Redis AUTH for authentication
- Configure Redis to bind to specific interfaces
- Use TLS encryption for production deployments
- Implement proper firewall rules

### Data Isolation
- Each component uses separate databases (0-10)
- Proper key naming conventions prevent conflicts
- Regular cleanup of temporary data

## Future Enhancements

### Planned Features
- **TLS/SSL support** for encrypted connections
- **Redis Cluster support** for horizontal scaling
- **Metrics export** to Prometheus/Grafana
- **Advanced caching patterns** (cache-aside, write-through)
- **Data compression** for large values
- **Key migration tools** for database reorganization

### Extension Points
- Custom circuit breaker policies
- Pluggable retry strategies  
- Custom health check logic
- Metrics collection backends

## Conclusion

The Async Redis Manager provides a robust, scalable, and maintainable solution for Redis operations in AutoBot. It eliminates the blocking timeout issues while providing enterprise-grade features like circuit breakers, health monitoring, and comprehensive error handling.

The migration from sync to async Redis operations should be gradual, using the compatibility layer to ensure stability during the transition.

For questions or issues, refer to the test suite (`test_async_redis_manager.py`) for examples and validation of functionality.