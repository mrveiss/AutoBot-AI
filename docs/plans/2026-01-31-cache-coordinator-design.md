# Cache Coordinator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Create a unified cache management system that eliminates memory bottlenecks through coordinated eviction, connection pooling, and centralized configuration.

**Architecture:** A CacheCoordinator singleton orchestrates all 8 cache types (L1 in-memory, L2 Redis, L3 SQLite) with memory-pressure-aware eviction. Each phase is independently deployable.

**Tech Stack:** Python, asyncio, Redis, psutil, FastAPI

---

## Summary of Changes

| Phase | Scope | Files | Risk |
|-------|-------|-------|------|
| 1 | Critical fixes (asyncio crash, Redis pool) | 2 | Low |
| 2 | CacheCoordinator + cache registration | 12 | Medium |
| 3 | SSOT config + metrics endpoint | 3 | Low |

**Total:** 17 files touched across 3 phases

---

## Phase 1: Critical Fixes

### Task 1.1: Fix asyncio.run() Crash in manager.py

**Files:**
- Modify: `src/memory/manager.py:186`

**Problem:** `asyncio.run()` crashes when called from async context.

**Step 1: Read the current implementation**

```bash
grep -n "asyncio.run" src/memory/manager.py
```

**Step 2: Replace with context-aware implementation**

```python
# Before (crashes in async context)
def store_sync(self, category: str, content: str, metadata: dict) -> str:
    return asyncio.run(self.store(category, content, metadata))

# After (works in both contexts)
def store_sync(self, category: str, content: str, metadata: dict) -> str:
    try:
        loop = asyncio.get_running_loop()
        # Already in async context - use thread executor
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, self.store(category, content, metadata))
            return future.result()
    except RuntimeError:
        # No running loop - safe to use asyncio.run
        return asyncio.run(self.store(category, content, metadata))
```

**Step 3: Test the fix**

```bash
pytest tests/test_memory_package.py -v --tb=short
```

**Step 4: Commit**

```bash
git add src/memory/manager.py
git commit -m "fix(memory): handle asyncio.run in async context (#ISSUE)"
```

---

### Task 1.2: Add Redis Connection Pooling

**Files:**
- Modify: `src/utils/redis_client.py`

**Step 1: Add connection pool management**

```python
from typing import Dict, Optional
import redis
from redis import asyncio as aioredis

# Singleton connection pools per database
_sync_pools: Dict[str, redis.ConnectionPool] = {}
_async_pools: Dict[str, aioredis.ConnectionPool] = {}

def get_redis_client(
    database: str = "main",
    async_client: bool = False,
    max_connections: int = 20,
    socket_timeout: float = 5.0,
) -> redis.Redis:
    """Get Redis client with connection pooling."""
    if database not in _sync_pools:
        _sync_pools[database] = redis.ConnectionPool(
            host=config.redis.host,
            port=config.redis.port,
            db=REDIS_DATABASES[database],
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_timeout,
        )
    return redis.Redis(connection_pool=_sync_pools[database])
```

**Step 2: Add async pool support**

```python
async def get_async_redis_client(
    database: str = "main",
    max_connections: int = 20,
) -> aioredis.Redis:
    """Get async Redis client with connection pooling."""
    if database not in _async_pools:
        _async_pools[database] = aioredis.ConnectionPool.from_url(
            f"redis://{config.redis.host}:{config.redis.port}/{REDIS_DATABASES[database]}",
            max_connections=max_connections,
        )
    return aioredis.Redis(connection_pool=_async_pools[database])
```

**Step 3: Test Redis operations**

```bash
python -c "from src.utils.redis_client import get_redis_client; r = get_redis_client(); print(r.ping())"
```

**Step 4: Commit**

```bash
git add src/utils/redis_client.py
git commit -m "feat(redis): add connection pooling (#ISSUE)"
```

---

## Phase 2: CacheCoordinator

### Task 2.1: Create Cache Protocol

**Files:**
- Create: `src/cache/__init__.py`
- Create: `src/cache/protocols.py`

**Step 1: Create package directory**

```bash
mkdir -p src/cache
```

**Step 2: Create protocol definition**

```python
# src/cache/protocols.py
"""Cache protocol definitions for coordinator integration."""

from typing import Protocol, Dict, Any, runtime_checkable

@runtime_checkable
class CacheProtocol(Protocol):
    """Interface all caches must implement to register with coordinator."""

    @property
    def name(self) -> str:
        """Unique cache identifier."""
        ...

    @property
    def size(self) -> int:
        """Current number of items in cache."""
        ...

    @property
    def max_size(self) -> int:
        """Maximum capacity."""
        ...

    def evict(self, count: int) -> int:
        """Evict `count` items. Returns actual evicted count."""
        ...

    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        ...

    def clear(self) -> None:
        """Clear all items from cache."""
        ...
```

**Step 3: Create package init**

```python
# src/cache/__init__.py
"""Cache management package."""

from .protocols import CacheProtocol
from .coordinator import CacheCoordinator, get_cache_coordinator

__all__ = ["CacheProtocol", "CacheCoordinator", "get_cache_coordinator"]
```

**Step 4: Commit**

```bash
git add src/cache/
git commit -m "feat(cache): add cache protocol definition (#ISSUE)"
```

---

### Task 2.2: Create CacheCoordinator

**Files:**
- Create: `src/cache/coordinator.py`

**Step 1: Implement coordinator**

```python
# src/cache/coordinator.py
"""Central cache coordinator with memory-pressure-aware eviction."""

import asyncio
import logging
from typing import Dict, Any, Optional
from .protocols import CacheProtocol
from src.memory.monitor import MemoryMonitor

logger = logging.getLogger(__name__)

class CacheCoordinator:
    """Orchestrates all registered caches with memory-aware eviction."""

    _instance: Optional["CacheCoordinator"] = None

    def __init__(self):
        self._caches: Dict[str, CacheProtocol] = {}
        self._monitor = MemoryMonitor()
        self._pressure_threshold = 0.80  # 80% system memory
        self._eviction_ratio = 0.20      # Evict 20% per cache
        self._pressure_triggered_count = 0
        self._lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "CacheCoordinator":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, cache: CacheProtocol) -> None:
        """Register a cache for coordinated management."""
        if not isinstance(cache, CacheProtocol):
            raise TypeError(f"Cache must implement CacheProtocol, got {type(cache)}")
        self._caches[cache.name] = cache
        logger.info(f"Registered cache: {cache.name} (max_size={cache.max_size})")

    def unregister(self, name: str) -> None:
        """Unregister a cache."""
        if name in self._caches:
            del self._caches[name]
            logger.info(f"Unregistered cache: {name}")

    async def check_pressure(self) -> bool:
        """Check memory pressure, trigger eviction if needed."""
        async with self._lock:
            mem_percent = self._monitor.get_memory_percent()
            if mem_percent > self._pressure_threshold:
                logger.warning(f"Memory pressure detected: {mem_percent:.1%}")
                await self._coordinated_evict()
                self._pressure_triggered_count += 1
                return True
            return False

    async def _coordinated_evict(self) -> Dict[str, int]:
        """Evict from all caches proportionally."""
        results = {}
        for name, cache in self._caches.items():
            evict_count = int(cache.size * self._eviction_ratio)
            if evict_count > 0:
                evicted = cache.evict(evict_count)
                results[name] = evicted
                logger.info(f"Evicted {evicted} items from {name}")
        return results

    def get_unified_stats(self) -> Dict[str, Any]:
        """Aggregate stats from all caches."""
        return {
            "caches": {name: cache.get_stats() for name, cache in self._caches.items()},
            "total_items": sum(c.size for c in self._caches.values()),
            "total_capacity": sum(c.max_size for c in self._caches.values()),
            "pressure_triggered_count": self._pressure_triggered_count,
            "system_memory_percent": self._monitor.get_memory_percent(),
        }

def get_cache_coordinator() -> CacheCoordinator:
    """Get the global cache coordinator instance."""
    return CacheCoordinator.get_instance()
```

**Step 2: Test coordinator**

```bash
python -c "from src.cache import CacheCoordinator; c = CacheCoordinator.get_instance(); print(c.get_unified_stats())"
```

**Step 3: Commit**

```bash
git add src/cache/coordinator.py
git commit -m "feat(cache): implement CacheCoordinator (#ISSUE)"
```

---

### Task 2.3: Add Cache Adapters to Existing Caches

**Files:**
- Modify: `src/memory/cache.py` (LRUCacheManager)
- Modify: `src/knowledge/embedding_cache.py`
- Modify: `src/llm_interface_pkg/cache.py`
- Modify: `src/code_intelligence/shared/ast_cache.py`
- Modify: `src/code_intelligence/shared/file_cache.py`
- Modify: `src/chat_history/cache.py`
- Modify: `src/utils/advanced_cache_manager.py`
- Modify: `src/utils/memory_optimization.py` (WeakCache)

**For each cache, add protocol methods:**

```python
# Example for LRUCacheManager in src/memory/cache.py

@property
def name(self) -> str:
    return "lru_memory"

@property
def size(self) -> int:
    return len(self._cache)

@property
def max_size(self) -> int:
    return self._max_size

def evict(self, count: int) -> int:
    """Evict oldest items from cache."""
    evicted = 0
    with self._lock:
        for _ in range(min(count, len(self._cache))):
            self._cache.popitem(last=False)
            evicted += 1
    return evicted

def get_stats(self) -> Dict[str, Any]:
    return {
        "size": self.size,
        "max_size": self.max_size,
        "hits": self._hits,
        "misses": self._misses,
        "hit_rate": self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0,
    }

def clear(self) -> None:
    with self._lock:
        self._cache.clear()
```

**Step: Register caches at module import**

```python
# At end of each cache module
from src.cache import get_cache_coordinator
get_cache_coordinator().register(cache_instance)
```

**Commit after each file:**

```bash
git add <file>
git commit -m "feat(<module>): add CacheProtocol support (#ISSUE)"
```

---

## Phase 3: SSOT Config + Metrics

### Task 3.1: Add Cache Config to SSOT

**Files:**
- Modify: `src/config/ssot_config.py`

**Step 1: Add cache configuration section**

```python
# Add to SSOT config schema
cache:
  coordinator:
    pressure_threshold: 0.80    # Trigger eviction at 80% memory
    eviction_ratio: 0.20        # Evict 20% per cache
    check_interval: 30          # Seconds between pressure checks

  redis:
    max_connections: 20
    socket_timeout: 5.0
    socket_connect_timeout: 5.0

  l1:  # In-memory caches (item counts)
    lru_memory: 1000
    embedding: 1000
    llm_response: 100
    ast: 1000
    file_content: 500
    weak_cache: 128

  l2:  # Redis TTLs (seconds)
    llm_response: 300
    knowledge: 300
    session: 300
    user_prefs: 3600
    computed: 7200
```

**Step 2: Commit**

```bash
git add src/config/ssot_config.py
git commit -m "feat(config): add cache settings to SSOT (#ISSUE)"
```

---

### Task 3.2: Add Metrics API Endpoint

**Files:**
- Modify: `src/api/routes/system.py` (or appropriate routes file)

**Step 1: Add cache stats endpoint**

```python
from src.cache import get_cache_coordinator

@router.get("/api/cache/stats")
async def get_cache_stats():
    """Get unified cache statistics."""
    coordinator = get_cache_coordinator()
    return coordinator.get_unified_stats()

@router.post("/api/cache/evict")
async def trigger_eviction():
    """Manually trigger cache eviction."""
    coordinator = get_cache_coordinator()
    evicted = await coordinator._coordinated_evict()
    return {"evicted": evicted}

@router.post("/api/cache/clear/{cache_name}")
async def clear_cache(cache_name: str):
    """Clear a specific cache."""
    coordinator = get_cache_coordinator()
    if cache_name in coordinator._caches:
        coordinator._caches[cache_name].clear()
        return {"status": "cleared", "cache": cache_name}
    return {"status": "not_found", "cache": cache_name}
```

**Step 2: Test endpoints**

```bash
# Use SSOT backend URL (172.16.168.20:8001 from config.backend_url)
curl http://$(python -c "from src.config.ssot_config import config; print(f'{config.vm.main}:{config.port.backend}')")/api/cache/stats

# Or directly if you know the IP:
curl http://172.16.168.20:8001/api/cache/stats
```

**Step 3: Commit**

```bash
git add src/api/routes/system.py
git commit -m "feat(api): add cache stats endpoint (#ISSUE)"
```

---

### Task 3.3: Update Caches to Read from SSOT

**Files:**
- Modify: All cache modules to read from SSOT instead of hardcoded values

**Example:**

```python
# Before
class LRUCacheManager:
    def __init__(self, max_size: int = 1000):
        self._max_size = max_size

# After
from src.config.ssot_config import config

class LRUCacheManager:
    def __init__(self, max_size: int = None):
        self._max_size = max_size or config.cache.l1.lru_memory
```

**Commit:**

```bash
git add <files>
git commit -m "refactor(cache): read limits from SSOT config (#ISSUE)"
```

---

## Testing

### Phase 1 Tests

```bash
# Test asyncio fix
pytest tests/test_memory_package.py -v

# Test Redis pooling
python -c "
from src.utils.redis_client import get_redis_client
clients = [get_redis_client() for _ in range(30)]
print(f'Created {len(clients)} clients with pooling')
"
```

### Phase 2 Tests

```bash
# Test coordinator registration
pytest tests/test_cache_coordinator.py -v

# Test memory pressure simulation
python -c "
from src.cache import get_cache_coordinator
c = get_cache_coordinator()
print(c.get_unified_stats())
"
```

### Phase 3 Tests

```bash
# Test API endpoint
# Use SSOT backend URL (172.16.168.20:8001 from config.backend_url)
curl http://$(python -c "from src.config.ssot_config import config; print(f'{config.vm.main}:{config.port.backend}')")/api/cache/stats

# Or directly if you know the IP:
curl http://172.16.168.20:8001/api/cache/stats | jq

# Test SSOT config loading
python -c "
from src.config.ssot_config import config
print(f'L1 LRU size: {config.cache.l1.lru_memory}')
"
```

---

## Acceptance Criteria

- [ ] Phase 1: asyncio.run() crash fixed
- [ ] Phase 1: Redis connection pooling working
- [ ] Phase 2: CacheCoordinator singleton implemented
- [ ] Phase 2: All 8 caches implement CacheProtocol
- [ ] Phase 2: Memory pressure eviction working
- [ ] Phase 3: Cache config in SSOT
- [ ] Phase 3: /api/cache/stats endpoint working
- [ ] All tests passing
- [ ] No regressions in existing functionality
