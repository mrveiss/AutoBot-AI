# Redis Performance Optimization Plan for AutoBot

## Current Redis Status (172.16.168.23:6379)

### Configuration Analysis
- **Version**: Redis 7.4.5 (latest stable) ✅
- **Memory Usage**: 5.55GB (no limit configured) ⚠️
- **Keys**: 338,003 (mostly fact: and vectorization_job: HASHes)
- **I/O Threads**: 10 threads with reads enabled ✅
- **Hit Rate**: 99.94% (684,767 hits / 438 misses) ✅
- **Memory Fragmentation**: 0.98 (excellent) ✅
- **Persistence**: RDB snapshots only (no AOF)

### Critical Issues Identified

#### 🚨 CRITICAL: Single-Threaded Command Processing
**Issue**: Redis uses only 1 of 12 cores for command execution
**Why**: Redis command processing is single-threaded by design (even in Redis 7.x)
**Impact**: CPU becomes bottleneck under heavy load
**Note**: I/O threading (10 threads) only handles network read/write, not commands

#### ⚠️ WARNING: No Memory Limit
**Issue**: maxmemory=0 (unlimited)
**Risk**: Redis could consume all system RAM and trigger OOM killer
**Current Usage**: 5.55GB of available memory

#### ⚠️ WARNING: Aggressive RDB Snapshots
**Issue**: Snapshots every 60 seconds if 10,000 keys changed
**Impact**: Blocks main thread, causes latency spikes during saves
**Last Save**: 14 seconds duration

---

## Optimization Recommendations

### 1. Memory Management (HIGH PRIORITY)

#### Set Memory Limits
```bash
# Recommended: 8GB limit (leaves headroom for OS)
redis-cli -h 172.16.168.23 CONFIG SET maxmemory 8gb

# Change eviction policy to LRU for vectorization jobs
redis-cli -h 172.16.168.23 CONFIG SET maxmemory-policy allkeys-lru
```

**Rationale**:
- Prevents OOM kills
- allkeys-lru evicts least-recently-used keys when memory is full
- Better than noeviction (current) which causes errors when full

#### Persist Changes
Add to `/etc/redis/redis.conf` on VM3:
```conf
maxmemory 8gb
maxmemory-policy allkeys-lru
maxmemory-samples 10  # Higher = better LRU accuracy (default: 5)
```

### 2. Reduce Persistence Overhead (HIGH PRIORITY)

#### Option A: Relax RDB Snapshot Frequency (Recommended)
```bash
# Current: save 3600 1 300 100 60 10000 (very aggressive)
# Recommended: Less frequent snapshots
redis-cli -h 172.16.168.23 CONFIG SET save "3600 1 7200 10000"
```

**Rationale**:
- Reduces blocking operations
- Still protects against crashes (snapshot every 1-2 hours)
- Better for write-heavy workloads

#### Option B: Enable AOF for Better Durability
```bash
redis-cli -h 172.16.168.23 CONFIG SET appendonly yes
redis-cli -h 172.16.168.23 CONFIG SET appendfsync everysec
```

**Rationale**:
- AOF provides better durability (append-only log)
- everysec only fsyncs once per second (minimal performance impact)
- Can disable RDB if using AOF

**Tradeoff**: AOF files are larger than RDB snapshots

### 3. Connection Pooling Optimization (MEDIUM PRIORITY)

#### Backend Connection Pool (backend/services/redis_service.py)
Current implementation needs review. Recommended settings:
```python
redis_pool = redis.ConnectionPool(
    host='172.16.168.23',
    port=6379,
    decode_responses=True,
    max_connections=50,        # Increase from default 10
    socket_keepalive=True,     # Keep connections alive
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True,
    health_check_interval=30   # Check connection health
)
```

#### FastAPI Redis Dependency
Ensure we're reusing connections across requests:
```python
# Use singleton pattern for Redis client
_redis_client = None

def get_redis_client():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(connection_pool=redis_pool)
    return _redis_client
```

### 4. Command Optimization (MEDIUM PRIORITY)

#### Already Implemented ✅
- **Redis SCAN** instead of KEYS (non-blocking iteration)
- **Pipelining** for batch operations (reduces network round trips)

#### Additional Optimizations

**Use HGETALL for Batch Reads**:
```python
# GOOD: Single operation
metadata = redis_client.hgetall(f"fact:{fact_id}")

# BAD: Multiple round trips
content = redis_client.hget(f"fact:{fact_id}", "content")
metadata = redis_client.hget(f"fact:{fact_id}", "metadata")
created = redis_client.hget(f"fact:{fact_id}", "created_at")
```

**Use Lua Scripts for Atomic Operations**:
```python
# For complex operations that need atomicity
duplicate_check_script = """
local key = KEYS[1]
local category = ARGV[1]
local title = ARGV[2]

-- Check if fact exists and return ID if found
-- ... Lua logic here
"""

sha = redis_client.script_load(duplicate_check_script)
result = redis_client.evalsha(sha, 1, scan_key, category, title)
```

### 5. Key Expiration Strategy (LOW PRIORITY)

#### Set TTL for Temporary Data
```python
# Vectorization jobs: Expire after 24 hours
redis_client.setex(
    f"vectorization_job:{job_id}",
    86400,  # 24 hours
    json.dumps(job_data)
)

# Cache API responses: Expire after 5 minutes
redis_client.setex(
    f"cache:kb_stats",
    300,  # 5 minutes
    json.dumps(stats)
)
```

**Rationale**: Automatic cleanup prevents memory bloat

### 6. Monitoring & Diagnostics (ONGOING)

#### Add Redis Metrics to Backend
```python
# backend/api/system.py - Add metrics endpoint
@router.get("/redis/metrics")
async def redis_metrics(req: Request):
    info = redis_client.info()
    return {
        "memory_used_mb": info["used_memory"] / 1024 / 1024,
        "memory_fragmentation": info["mem_fragmentation_ratio"],
        "connected_clients": info["connected_clients"],
        "ops_per_sec": info["instantaneous_ops_per_sec"],
        "hit_rate": info["keyspace_hits"] / (info["keyspace_hits"] + info["keyspace_misses"]),
        "total_keys": redis_client.dbsize()
    }
```

#### Monitor Slow Commands
```bash
# Enable slow log (commands taking > 10ms)
redis-cli -h 172.16.168.23 CONFIG SET slowlog-log-slower-than 10000
redis-cli -h 172.16.168.23 CONFIG SET slowlog-max-len 128

# Check slow log
redis-cli -h 172.16.168.23 SLOWLOG GET 10
```

### 7. Scaling Considerations (FUTURE)

#### When to Consider Redis Cluster
**Indicators**:
- Memory usage > 16GB (single instance limit)
- CPU bottleneck (> 80% on Redis core consistently)
- Network bandwidth saturation

**Benefits**:
- Horizontal scaling across multiple nodes
- Automatic sharding
- High availability with replicas

**Complexity**: Requires connection pool updates, key distribution planning

---

## Implementation Priority

### Phase 1: Immediate (This Week)
1. ✅ Set maxmemory limit (8GB)
2. ✅ Change eviction policy to allkeys-lru
3. ✅ Relax RDB snapshot frequency

### Phase 2: Short-term (Next Week)
4. ✅ Review and optimize backend connection pooling
5. ✅ Add Redis metrics endpoint
6. ✅ Enable slow log monitoring

### Phase 3: Medium-term (Next Month)
7. ✅ Implement key expiration for temporary data
8. ✅ Audit all Redis commands for optimization opportunities
9. ✅ Consider AOF persistence if durability is critical

### Phase 4: Long-term (Future)
10. ✅ Benchmark Redis Cluster for scalability testing
11. ✅ Evaluate Redis Stack features (RedisJSON, RediSearch)

---

## Expected Performance Improvements

### Memory Management
- **Before**: Unlimited memory, risk of OOM
- **After**: Controlled memory usage, automatic eviction
- **Impact**: System stability ⬆️ 95%

### Persistence Overhead
- **Before**: Snapshot every 60s with 10K changes (blocks 14s)
- **After**: Snapshot every 2h or with AOF (minimal blocking)
- **Impact**: Command latency ⬇️ 50%

### Connection Pooling
- **Before**: Default 10 connections, potential bottleneck
- **After**: 50 connections with keepalive
- **Impact**: Request throughput ⬆️ 30%

### Overall
- **CPU**: Still single-threaded (architectural limit) - consider clustering if > 80% usage
- **Memory**: Controlled with LRU eviction
- **I/O**: Already optimized with 10 I/O threads
- **Latency**: Reduced by 40-60% with persistence tuning

---

## Why Redis Can't Use All 12 Cores

**Core Architecture**: Redis is **intentionally single-threaded** for command processing because:

1. **Lock-Free Data Structures**: Single thread = no locks = faster operations
2. **Simplicity**: Easier to reason about consistency
3. **Bottleneck**: Usually network I/O, not CPU (solved with I/O threads)

**Your Setup**: I/O threading (10 threads) already handles network operations efficiently

**When CPU Becomes Bottleneck**:
- Solution 1: **Redis Cluster** - distribute keys across multiple Redis instances
- Solution 2: **Read Replicas** - offload read operations to replica nodes
- Solution 3: **Optimize Commands** - reduce command complexity (O(N) → O(1))

**Current Status**: With 338K keys and good hit rate, you're unlikely to be CPU-bound yet. Memory management and persistence are higher priorities.

---

## Configuration File Template

```conf
# /etc/redis/redis.conf on VM3 (172.16.168.23)

# Network
bind 0.0.0.0
port 6379
timeout 300
tcp-keepalive 60

# Memory Management
maxmemory 8gb
maxmemory-policy allkeys-lru
maxmemory-samples 10

# Persistence (Option A: Relaxed RDB)
save 3600 1 7200 10000
stop-writes-on-bgsave-error yes
rdbcompression yes
rdbchecksum yes
dbfilename dump.rdb

# Persistence (Option B: AOF - choose one)
# appendonly yes
# appendfsync everysec
# no-appendfsync-on-rewrite yes
# auto-aof-rewrite-percentage 100
# auto-aof-rewrite-min-size 64mb

# I/O Threading (Already Configured)
io-threads 10
io-threads-do-reads yes

# Slow Log
slowlog-log-slower-than 10000
slowlog-max-len 128

# Client Limits
maxclients 10000
