# Redis Migration Exclusions

Files that use `redis.Redis()` directly but should **NOT** be migrated to `get_redis_client()`.

## Legitimate Redis Stack Features

These files use Redis Stack modules (RedisJSON, RediSearch, RedisGraph) that require direct instantiation with specific configurations:

### 1. `src/autobot_memory_graph.py`
**Redis DB**: 9
**Reason**: Uses **RedisJSON** and **RediSearch** for Memory MCP backend
**Features Used**:
- RedisJSON: Complex entity document storage
- RediSearch: Graph relationship queries
- Semantic embeddings: nomic-embed-text (768 dimensions)

**Purpose**: Backend for Memory MCP (`mcp__memory__*` tools)
- Entity storage (conversations, bugs, features, decisions, tasks)
- Bidirectional relationship tracking
- Hybrid search (RediSearch filters + Ollama embeddings)

**Migration Status**: ✅ **DO NOT MIGRATE** - Requires Redis Stack features

---

### 2. `backend/api/cache.py`
**Redis DB**: Multiple (0-11)
**Reason**: Custom multi-database cache management with service discovery
**Features Used**:
- Service discovery integration
- Custom connection pooling for multiple DBs
- Fast timeout configurations (0.5s connect)

**Purpose**: Cache management API with database-specific clearing
- Manages 12 separate Redis databases
- Uses cached service discovery endpoints
- Eliminates DNS resolution delays

**Migration Status**: ⏳ **COMPLEX MIGRATION** - Requires redesign of redis_database_manager to support DB number selection

---

## Utility Files (Keep As-Is)

These utility files are part of the Redis infrastructure itself:

### 3. `src/utils/redis_database_manager.py`
**Reason**: Backend infrastructure for `get_redis_client()`
**Status**: ✅ **CANONICAL BACKEND** - Do not migrate

### 4. `backend/utils/async_redis_manager.py`
**Reason**: Async Redis wrapper utility
**Status**: ⏳ **EVALUATE** - May need to integrate with redis_database_manager

---

## Phase 5 Special Cases: Infrastructure Utilities

Identified during Phase 5 Batch 3 analysis - these files provide infrastructure services and should not be migrated:

### 5. `src/utils/service_discovery.py`
**Redis DB**: Variable (arbitrary services)
**Reason**: Health check system using `redis.asyncio` for async TCP checks
**Features Used**:
- `redis.asyncio` (async client, not sync)
- Temporary connections for health verification
- Tests arbitrary Redis services (not just main infrastructure)

**Purpose**: Service discovery health monitoring
- Creates fresh connections per check (not pooled)
- Measures actual connectivity and response time
- Part of distributed system monitoring infrastructure

**Migration Status**: ✅ **DO NOT MIGRATE** - Infrastructure utility, requires async client, needs fresh connections per check

---

### 6. `src/utils/distributed_service_discovery.py`
**Redis DB**: Variable (arbitrary services)
**Reason**: Quick Redis connection tests using `redis.asyncio`
**Features Used**:
- `redis.asyncio` with immediate timeouts (100ms)
- Fast connection tests without retries
- Health check with response time measurement

**Purpose**: Distributed service discovery system
- Tests multiple service endpoints rapidly
- Requires non-pooled connections for accurate metrics
- Part of infrastructure monitoring layer

**Migration Status**: ✅ **DO NOT MIGRATE** - Infrastructure utility, async operations, health check system

---

### 7. `src/utils/optimized_redis_manager.py`
**Redis DB**: Multiple (pool creation)
**Reason**: Connection pool manager (creates pools for others)
**Features Used**:
- Connection pool creation (`redis.ConnectionPool`)
- Pool health checks
- Multi-database pool management

**Purpose**: Provides connection pooling infrastructure
- Creates and manages connection pools
- Used BY canonical utilities (not consumer of them)
- Lower-level infrastructure layer

**Migration Status**: ✅ **DO NOT MIGRATE** - Pool manager infrastructure, would create circular dependency

---

### 8. `monitoring/performance_monitor.py`
**Redis DB**: Multiple (0, 1, 4, 7, 8)
**Reason**: Health checks and database performance testing
**Features Used**:
- Temporary connections for service health checks
- Multi-database performance testing
- Connection time measurement

**Purpose**: Monitoring and performance measurement
- Tests Redis service availability
- Benchmarks multiple databases
- Measures connection performance (needs non-pooled connections)

**Migration Status**: ✅ **DO NOT MIGRATE** - Monitoring utility, needs fresh connections for accurate metrics

---

## Test/Analysis Scripts (Low Priority)

Scripts in `scripts/analysis/`, `analysis/`, and `tests/` directories:
- `scripts/analysis/redis_*.py` - Analysis scripts
- `analysis/migrate_*.py` - One-time migration scripts
- `tests/integration/test_*.py` - Test files

**Migration Status**: ⏳ **LOW PRIORITY** - Can migrate during cleanup sprint

---

## Archive Files (Already Deprecated)

Files in `archives/code/` and `archives/tests/`:
**Status**: ❌ **DO NOT MIGRATE** - Already archived/obsolete

---

## Summary

### DO NOT MIGRATE - Redis Stack Operations
- `src/autobot_memory_graph.py` - RedisJSON/RediSearch required

### DO NOT MIGRATE - Infrastructure Utilities (Phase 5 Findings)
- `src/utils/service_discovery.py` - Async health check system
- `src/utils/distributed_service_discovery.py` - Distributed service discovery
- `src/utils/optimized_redis_manager.py` - Connection pool manager
- `monitoring/performance_monitor.py` - Performance testing and health checks

### COMPLEX MIGRATION - Requires Architecture Changes
- `backend/api/cache.py` - Multi-DB cache manager

### CANONICAL UTILITIES - Keep As-Is
- `src/utils/redis_database_manager.py` - Backend for get_redis_client()
- `src/utils/redis_client.py` - Canonical client utility

### LOW PRIORITY - Test/Analysis Files
- Test files in `tests/`
- Analysis scripts in `scripts/analysis/`, `analysis/`
- One-time migration scripts
- Archived code in `archives/`

---

## Phase 5 Migration Results

**Production Files Migrated**: 11 files (15 instances) ✅
**Infrastructure Exclusions**: 4 files (5 instances) - Documented above
**Redis Stack Exclusions**: 1 file - Memory MCP backend
**Complex Migrations Deferred**: 1 file - Multi-DB cache manager
**Test/Analysis Files**: ~30 files - Low priority

**Migration Completion**: **55% of production code** (11 out of ~20 production files)
**Remaining Files**: Legitimate infrastructure utilities and special cases

See `PHASE_5_BATCH_3.md` for detailed analysis of infrastructure exclusions.

---

**Created**: 2025-10-26
**Updated**: 2025-10-26 (Phase 5 complete)
**Related**: `PHASE_5_BATCH_3.md`, `PHASE_5_SUMMARY.md`, `redis_helper_migration_plan.md`, `README.md`
