# Redis Client Consolidation - Design Document

**Date**: 2025-11-11
**Target**: `src/utils/redis_client.py`
**Status**: Design Phase

---

## Design Principles

1. **Preserve existing API** - `get_redis_client(async_client=bool, database=str)` remains the canonical interface
2. **Backward compatibility** - Existing code continues to work without changes
3. **Feature enhancement** - Add best features from all 6 implementations
4. **Performance optimization** - Integrate TCP keepalive, idle cleanup, and pool statistics
5. **Comprehensive monitoring** - Enhanced statistics, health checks, and error tracking
6. **Type safety** - RedisDatabase enum for database selection
7. **Configuration flexibility** - Support both YAML files and service registry

---

## Current Architecture (redis_client.py)

### Class Structure
```python
class RedisConnectionManager:
    """Singleton manager for Redis connections"""

    _instance = None
    _sync_pools: Dict[str, redis.ConnectionPool]
    _async_pools: Dict[str, async_redis.ConnectionPool]

    # Circuit breaker state
    _circuit_breaker_failures: Dict[str, int]
    _circuit_breaker_last_attempt: Dict[str, datetime]
    _connection_states: Dict[str, str]  # "HEALTHY", "DEGRADED", "FAILED"

    def get_sync_client(self, database_name: str) -> redis.Redis
    def get_async_client(self, database_name: str) -> async_redis.Redis
    def _check_circuit_breaker(self, database_name: str) -> bool
    def _record_success(self, database_name: str)
    def _record_failure(self, database_name: str)
```

### Public API
```python
def get_redis_client(async_client: bool = False, database: str = "main"):
    """CANONICAL API - Get Redis client with circuit breaker and health monitoring"""
    manager = RedisConnectionManager()
    if async_client:
        return await manager.get_async_client(database)
    else:
        return manager.get_sync_client(database)
```

---

## Enhanced Architecture Design

### 1. Configuration Layer

**Add**: YAML configuration support + Service registry integration

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict
import yaml
import os

class RedisDatabase(Enum):
    """Type-safe database enumeration"""
    MAIN = 0
    KNOWLEDGE = 1
    PROMPTS = 2
    AGENTS = 3
    METRICS = 4
    SESSIONS = 5
    CACHE = 6
    VECTORS = 7
    TEMP = 8
    ANALYTICS = 9
    AUDIT = 10
    NOTIFICATIONS = 11
    JOBS = 12
    SEARCH = 13
    TIMESERIES = 14
    GRAPH = 15

@dataclass
class RedisConfig:
    """Redis database configuration"""
    name: str
    db: int
    host: str = "172.16.168.23"
    port: int = 6379
    password: Optional[str] = None
    decode_responses: bool = True
    max_connections: int = 20
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    socket_keepalive: bool = True
    socket_keepalive_options: Optional[Dict[int, int]] = None
    health_check_interval: int = 30
    retry_on_timeout: bool = True
    max_retries: int = 3

class RedisConfigLoader:
    """Load Redis configurations from multiple sources"""

    @staticmethod
    def load_from_yaml(yaml_path: str = None) -> Dict[str, RedisConfig]:
        """Load configurations from YAML file"""
        if yaml_path is None:
            # Auto-detect container vs host environment
            if os.path.exists("/app"):
                yaml_path = "/app/config/redis-databases.yaml"
            else:
                yaml_path = "./config/redis-databases.yaml"

        if not os.path.exists(yaml_path):
            return {}

        with open(yaml_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)

        configs = {}
        for db_name, db_config in config_data.get('databases', {}).items():
            configs[db_name] = RedisConfig(
                name=db_name,
                db=db_config.get('db', 0),
                host=db_config.get('host', '172.16.168.23'),
                port=db_config.get('port', 6379),
                password=db_config.get('password'),
                decode_responses=db_config.get('decode_responses', True),
                max_connections=db_config.get('max_connections', 20),
                socket_timeout=db_config.get('socket_timeout', 5.0),
            )
        return configs

    @staticmethod
    def load_from_service_registry() -> Dict[str, RedisConfig]:
        """Load configurations from service registry"""
        try:
            from src.utils.service_registry import service_registry
            redis_config = service_registry.get_service_config("redis")
            # Convert service registry format to RedisConfig
            return {...}
        except ImportError:
            return {}

    @staticmethod
    def load_timeout_config() -> dict:
        """Load centralized timeout configuration"""
        try:
            from src.config import timeout_config
            return timeout_config.REDIS_TIMEOUT_CONFIG
        except ImportError:
            return {
                "socket_timeout": 5.0,
                "socket_connect_timeout": 5.0,
                "retry_on_timeout": True,
                "max_retries": 3,
            }
```

---

### 2. Statistics and Monitoring Layer

**Add**: Comprehensive statistics tracking

```python
from dataclasses import dataclass, field
from datetime import datetime
import weakref

@dataclass
class RedisStats:
    """Per-database Redis statistics"""
    database_name: str
    total_connections: int = 0
    active_connections: int = 0
    failed_connections: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    total_retry_attempts: int = 0
    circuit_breaker_trips: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    uptime_seconds: float = 0.0

@dataclass
class PoolStatistics:
    """Connection pool statistics"""
    database_name: str
    created_connections: int
    available_connections: int
    in_use_connections: int
    max_connections: int
    idle_connections: int
    last_cleanup: Optional[datetime] = None

@dataclass
class ManagerStats:
    """Overall manager statistics"""
    total_databases: int
    healthy_databases: int
    degraded_databases: int
    failed_databases: int
    total_operations: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    uptime_seconds: float = 0.0
    database_stats: Dict[str, RedisStats] = field(default_factory=dict)
```

---

### 3. Enhanced Connection Manager

**Add**: All advanced features while preserving existing structure

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from contextlib import asynccontextmanager
import weakref

class RedisConnectionManager:
    """
    Enhanced Redis connection manager with comprehensive features.

    Features consolidated from:
    - redis_client.py: Circuit breaker, health monitoring, unified API
    - backend/async_redis_manager.py: Loading dataset handling, YAML config, named methods,
      WeakSet tracking, pipeline managers, comprehensive stats, tenacity retry
    - optimized_redis_manager.py: TCP keepalive tuning, idle cleanup, pool stats
    - redis_database_manager.py: Enum type safety, service registry, path auto-detection
    - redis_helper.py: Centralized timeout config, parameter filtering
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        # Existing attributes
        self._sync_pools: Dict[str, redis.ConnectionPool] = {}
        self._async_pools: Dict[str, async_redis.ConnectionPool] = {}
        self._circuit_breaker_failures: Dict[str, int] = {}
        self._circuit_breaker_last_attempt: Dict[str, datetime] = {}
        self._connection_states: Dict[str, str] = {}  # "HEALTHY", "DEGRADED", "FAILED"

        # NEW: Configuration management
        self._configs: Dict[str, RedisConfig] = {}
        self._load_configurations()

        # NEW: WeakSet connection tracking (doesn't prevent GC)
        self._active_sync_connections: weakref.WeakSet = weakref.WeakSet()
        self._active_async_connections: weakref.WeakSet = weakref.WeakSet()

        # NEW: Statistics tracking
        self._database_stats: Dict[str, RedisStats] = {}
        self._manager_stats = ManagerStats(total_databases=0, healthy_databases=0,
                                          degraded_databases=0, failed_databases=0)
        self._start_time = datetime.now()

        # NEW: Background tasks
        self._health_check_tasks: Dict[str, asyncio.Task] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

        # NEW: TCP keepalive configuration (from optimized_redis_manager.py)
        self._tcp_keepalive_options = {
            1: 600,  # TCP_KEEPIDLE - Seconds before sending keepalive probes
            2: 60,   # TCP_KEEPINTVL - Interval between keepalive probes
            3: 5,    # TCP_KEEPCNT - Number of keepalive probes
        }

        # NEW: Idle connection cleanup configuration
        self._max_idle_time_seconds = 300  # 5 minutes
        self._cleanup_interval_seconds = 60  # Check every minute

        self._initialized = True
        logger.info("Enhanced Redis Connection Manager initialized")

    def _load_configurations(self):
        """Load configurations from multiple sources with priority"""
        # Priority 1: YAML file
        yaml_configs = RedisConfigLoader.load_from_yaml()
        self._configs.update(yaml_configs)

        # Priority 2: Service registry (if not in YAML)
        registry_configs = RedisConfigLoader.load_from_service_registry()
        for name, config in registry_configs.items():
            if name not in self._configs:
                self._configs[name] = config

        # Priority 3: Default configuration with timeout config
        timeout_config = RedisConfigLoader.load_timeout_config()
        default_config = RedisConfig(
            name="main",
            db=0,
            socket_timeout=timeout_config.get('socket_timeout', 5.0),
            socket_connect_timeout=timeout_config.get('socket_connect_timeout', 5.0),
            retry_on_timeout=timeout_config.get('retry_on_timeout', True),
            max_retries=timeout_config.get('max_retries', 3),
            socket_keepalive_options=self._tcp_keepalive_options,
        )
        if "main" not in self._configs:
            self._configs["main"] = default_config

    # NEW: Loading dataset state handling (from backend/async_redis_manager.py)
    async def _wait_for_redis_ready(self, client: async_redis.Redis,
                                    database_name: str, max_wait: int = 60) -> bool:
        """
        Wait for Redis to finish loading dataset and be ready.

        Handles: "LOADING Redis is loading the dataset in memory" errors
        Critical during Redis startup/restart.
        """
        start_time = datetime.now()

        while (datetime.now() - start_time).total_seconds() < max_wait:
            try:
                await client.ping()
                logger.info(f"Redis database '{database_name}' is ready")
                return True
            except async_redis.ResponseError as e:
                if "LOADING" in str(e):
                    logger.warning(f"Redis '{database_name}' loading dataset, waiting...")
                    await asyncio.sleep(2)
                else:
                    raise
            except Exception as e:
                logger.error(f"Error checking Redis readiness: {e}")
                return False

        logger.error(f"Redis '{database_name}' did not become ready within {max_wait}s")
        return False

    # NEW: Tenacity retry wrapper (from backend/async_redis_manager.py)
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((async_redis.ConnectionError, asyncio.TimeoutError)),
    )
    async def _create_async_pool_with_retry(self, database_name: str,
                                           config: RedisConfig) -> async_redis.ConnectionPool:
        """Create async pool with retry logic using tenacity"""
        pool = async_redis.ConnectionPool(
            host=config.host,
            port=config.port,
            db=config.db,
            password=config.password,
            decode_responses=config.decode_responses,
            max_connections=config.max_connections,
            socket_timeout=config.socket_timeout,
            socket_connect_timeout=config.socket_connect_timeout,
            socket_keepalive=config.socket_keepalive,
            socket_keepalive_options=config.socket_keepalive_options,
            retry_on_timeout=config.retry_on_timeout,
        )

        # Test connection and wait for Redis to be ready
        client = async_redis.Redis(connection_pool=pool)
        ready = await self._wait_for_redis_ready(client, database_name)

        if not ready:
            raise async_redis.ConnectionError(
                f"Redis database '{database_name}' not ready after waiting"
            )

        return pool

    # NEW: TCP keepalive for sync pools (from optimized_redis_manager.py)
    def _create_sync_pool_with_keepalive(self, database_name: str,
                                        config: RedisConfig) -> redis.ConnectionPool:
        """Create sync pool with TCP keepalive tuning"""
        return redis.ConnectionPool(
            host=config.host,
            port=config.port,
            db=config.db,
            password=config.password,
            decode_responses=config.decode_responses,
            max_connections=config.max_connections,
            socket_timeout=config.socket_timeout,
            socket_connect_timeout=config.socket_connect_timeout,
            socket_keepalive=True,
            socket_keepalive_options=self._tcp_keepalive_options,
            retry_on_timeout=config.retry_on_timeout,
        )

    # NEW: Pool statistics (from optimized_redis_manager.py)
    def get_pool_statistics(self, database: str) -> PoolStatistics:
        """Get detailed connection pool statistics"""
        pool = self._sync_pools.get(database)
        if not pool:
            raise ValueError(f"No pool for database '{database}'")

        return PoolStatistics(
            database_name=database,
            created_connections=pool._created_connections,
            available_connections=len(pool._available_connections),
            in_use_connections=len(pool._in_use_connections),
            max_connections=pool.max_connections,
            idle_connections=len([c for c in pool._available_connections
                                 if hasattr(c, '_last_use') and
                                 (datetime.now() - c._last_use).total_seconds() > 60]),
        )

    # NEW: Idle connection cleanup (from optimized_redis_manager.py)
    async def _cleanup_idle_connections_task(self):
        """Background task to clean up idle connections"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval_seconds)
                await self._cleanup_idle_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in idle connection cleanup: {e}")

    async def _cleanup_idle_connections(self):
        """Clean up idle connections older than max_idle_time"""
        for database_name, pool in self._sync_pools.items():
            try:
                # Identify idle connections
                idle_count = 0
                for conn in list(pool._available_connections):
                    if hasattr(conn, '_last_use'):
                        idle_time = (datetime.now() - conn._last_use).total_seconds()
                        if idle_time > self._max_idle_time_seconds:
                            pool._available_connections.remove(conn)
                            conn.disconnect()
                            idle_count += 1

                if idle_count > 0:
                    logger.info(f"Cleaned up {idle_count} idle connections for '{database_name}'")
            except Exception as e:
                logger.error(f"Error cleaning up '{database_name}': {e}")

    # NEW: Named database convenience methods (from backend/async_redis_manager.py)
    async def main(self) -> async_redis.Redis:
        """Get async client for main database"""
        return await self.get_async_client("main")

    async def knowledge(self) -> async_redis.Redis:
        """Get async client for knowledge database"""
        return await self.get_async_client("knowledge")

    async def prompts(self) -> async_redis.Redis:
        """Get async client for prompts database"""
        return await self.get_async_client("prompts")

    # ... (similar methods for all databases)

    # NEW: Pipeline context manager (from backend/async_redis_manager.py)
    @asynccontextmanager
    async def pipeline(self, database: str = "main"):
        """Context manager for Redis pipeline operations"""
        client = await self.get_async_client(database)
        pipe = client.pipeline()
        try:
            yield pipe
            await pipe.execute()
        except Exception as e:
            logger.error(f"Pipeline error for '{database}': {e}")
            raise
        finally:
            await pipe.reset()

    # ENHANCED: get_sync_client with all features
    def get_sync_client(self, database_name: str = "main") -> Optional[redis.Redis]:
        """
        Get synchronous Redis client with all enhanced features.

        Features:
        - Circuit breaker protection
        - TCP keepalive tuning
        - WeakSet connection tracking
        - Statistics collection
        - Parameter filtering
        """
        # Check circuit breaker (existing)
        if not self._check_circuit_breaker(database_name):
            logger.warning(f"Circuit breaker open for '{database_name}'")
            return None

        try:
            # Get or create pool with TCP keepalive
            if database_name not in self._sync_pools:
                config = self._configs.get(database_name, self._configs["main"])
                self._sync_pools[database_name] = self._create_sync_pool_with_keepalive(
                    database_name, config
                )

            # Create client
            pool = self._sync_pools[database_name]
            client = redis.Redis(connection_pool=pool)

            # Test connection
            client.ping()

            # Track connection in WeakSet
            self._active_sync_connections.add(client)

            # Record success
            self._record_success(database_name)

            # Update statistics
            self._update_stats(database_name, success=True)

            return client

        except Exception as e:
            logger.error(f"Failed to get sync client for '{database_name}': {e}")
            self._record_failure(database_name)
            self._update_stats(database_name, success=False, error=str(e))
            return None

    # ENHANCED: get_async_client with all features
    async def get_async_client(self, database_name: str = "main") -> Optional[async_redis.Redis]:
        """
        Get asynchronous Redis client with all enhanced features.

        Features:
        - Circuit breaker protection
        - Loading dataset handling
        - Tenacity retry logic
        - TCP keepalive tuning
        - WeakSet connection tracking
        - Statistics collection
        """
        # Check circuit breaker
        if not self._check_circuit_breaker(database_name):
            logger.warning(f"Circuit breaker open for '{database_name}'")
            return None

        try:
            # Get or create pool with retry and loading dataset handling
            if database_name not in self._async_pools:
                config = self._configs.get(database_name, self._configs["main"])
                self._async_pools[database_name] = await self._create_async_pool_with_retry(
                    database_name, config
                )

            # Create client
            pool = self._async_pools[database_name]
            client = async_redis.Redis(connection_pool=pool)

            # Track connection in WeakSet
            self._active_async_connections.add(client)

            # Record success
            self._record_success(database_name)

            # Update statistics
            self._update_stats(database_name, success=True)

            return client

        except Exception as e:
            logger.error(f"Failed to get async client for '{database_name}': {e}")
            self._record_failure(database_name)
            self._update_stats(database_name, success=False, error=str(e))
            return None

    # NEW: Statistics update
    def _update_stats(self, database_name: str, success: bool, error: str = None):
        """Update database statistics"""
        if database_name not in self._database_stats:
            self._database_stats[database_name] = RedisStats(database_name=database_name)

        stats = self._database_stats[database_name]
        if success:
            stats.successful_operations += 1
        else:
            stats.failed_operations += 1
            stats.last_error = error
            stats.last_error_time = datetime.now()

    # NEW: Get comprehensive statistics
    def get_statistics(self) -> ManagerStats:
        """Get comprehensive manager statistics"""
        self._manager_stats.total_databases = len(self._configs)
        self._manager_stats.healthy_databases = sum(
            1 for state in self._connection_states.values() if state == "HEALTHY"
        )
        self._manager_stats.degraded_databases = sum(
            1 for state in self._connection_states.values() if state == "DEGRADED"
        )
        self._manager_stats.failed_databases = sum(
            1 for state in self._connection_states.values() if state == "FAILED"
        )
        self._manager_stats.uptime_seconds = (datetime.now() - self._start_time).total_seconds()
        self._manager_stats.database_stats = self._database_stats.copy()

        return self._manager_stats

    # Existing methods remain unchanged
    def _check_circuit_breaker(self, database_name: str) -> bool:
        """Check if circuit breaker allows connection attempts"""
        # ... (existing implementation)
        pass

    def _record_success(self, database_name: str):
        """Record successful connection"""
        # ... (existing implementation)
        pass

    def _record_failure(self, database_name: str):
        """Record failed connection"""
        # ... (existing implementation)
        pass
```

---

### 4. Public API (Unchanged)

**PRESERVE**: Existing API for backward compatibility

```python
def get_redis_client(
    async_client: bool = False,
    database: str = "main"
) -> Union[redis.Redis, async_redis.Redis, None]:
    """
    Get a Redis client instance with circuit breaker and health monitoring.

    This is the CANONICAL method for Redis access in AutoBot.

    Features (consolidated from 6 implementations):
    - Circuit breaker protection
    - Connection pooling with TCP keepalive tuning
    - Loading dataset state handling (waits for Redis startup)
    - Comprehensive retry logic with tenacity
    - WeakSet connection tracking
    - Statistics collection
    - Health monitoring

    Args:
        async_client: If True, return async client. If False, return sync client.
        database: Database name (e.g., "main", "knowledge", "prompts")

    Returns:
        Redis client instance (sync or async) or None if circuit breaker open

    Examples:
        >>> # Synchronous usage
        >>> redis_client = get_redis_client(async_client=False, database="main")
        >>> redis_client.set("key", "value")

        >>> # Asynchronous usage
        >>> redis_client = await get_redis_client(async_client=True, database="knowledge")
        >>> await redis_client.set("embedding:123", vector_data)

        >>> # Using named database enum (type-safe)
        >>> from src.utils.redis_client import RedisDatabase
        >>> redis_client = get_redis_client(database=RedisDatabase.PROMPTS.name.lower())
    """
    manager = RedisConnectionManager()

    if async_client:
        return await manager.get_async_client(database)
    else:
        return manager.get_sync_client(database)
```

---

## Implementation Plan

### Phase 1: Add Configuration Layer (2 hours)
- [ ] Add RedisDatabase enum
- [ ] Add RedisConfig dataclass
- [ ] Add RedisConfigLoader class
- [ ] Add YAML loading
- [ ] Add service registry integration
- [ ] Add timeout config loading

### Phase 2: Add Statistics Layer (1 hour)
- [ ] Add RedisStats dataclass
- [ ] Add PoolStatistics dataclass
- [ ] Add ManagerStats dataclass
- [ ] Add statistics tracking to manager

### Phase 3: Enhance Connection Manager (3 hours)
- [ ] Add WeakSet connection tracking
- [ ] Add "loading dataset" handling
- [ ] Add tenacity retry wrapper
- [ ] Add TCP keepalive configuration
- [ ] Enhance sync client creation
- [ ] Enhance async client creation

### Phase 4: Add Advanced Features (2 hours)
- [ ] Add named database methods
- [ ] Add pipeline context manager
- [ ] Add pool statistics method
- [ ] Add idle connection cleanup
- [ ] Add background cleanup task

### Phase 5: Testing (2 hours)
- [ ] Test sync client with all features
- [ ] Test async client with all features
- [ ] Test circuit breaker
- [ ] Test loading dataset handling
- [ ] Test statistics collection
- [ ] Test idle cleanup
- [ ] Test pipeline manager

**Total Estimated Time**: 10 hours

---

## Backward Compatibility

**All existing code continues to work**:

```python
# ✅ Existing code - NO CHANGES NEEDED
from src.utils.redis_client import get_redis_client

# Still works exactly the same
redis_client = get_redis_client(async_client=False, database="main")
redis_client.set("key", "value")

# Async usage - NO CHANGES NEEDED
async_redis = await get_redis_client(async_client=True, database="knowledge")
await async_redis.set("embedding:123", data)
```

**New features available optionally**:

```python
# ✅ NEW: Type-safe database selection
from src.utils.redis_client import RedisDatabase

redis_client = get_redis_client(database=RedisDatabase.PROMPTS.name.lower())

# ✅ NEW: Named database methods
manager = RedisConnectionManager()
main_client = await manager.main()
knowledge_client = await manager.knowledge()

# ✅ NEW: Pipeline context manager
async with manager.pipeline("main") as pipe:
    pipe.set("key1", "value1")
    pipe.set("key2", "value2")
    # Auto-executes on context exit

# ✅ NEW: Statistics
stats = manager.get_statistics()
print(f"Healthy databases: {stats.healthy_databases}")
print(f"Total operations: {stats.total_operations}")

# ✅ NEW: Pool statistics
pool_stats = manager.get_pool_statistics("main")
print(f"Active connections: {pool_stats.in_use_connections}")
```

---

## Files to Archive After Implementation

```bash
archives/2025-11-11_redis_consolidation/
├── README.md
├── async_redis_manager.py (from backend/utils/)
├── async_redis_manager.py (from src/utils/)
├── optimized_redis_manager.py (from src/utils/)
├── redis_database_manager.py (from src/utils/)
└── redis_helper.py (from src/utils/)
```

**Files to KEEP (not archived)**:
- `src/utils/redis_client.py` - CANONICAL (enhanced implementation)
- `backend/services/redis_service_manager.py` - Infrastructure management (different responsibility)

---

## Success Criteria

- [ ] All 15+ unique features integrated
- [ ] Existing API unchanged (backward compatible)
- [ ] All tests passing
- [ ] Statistics tracking functional
- [ ] Idle cleanup working
- [ ] Pipeline managers working
- [ ] Loading dataset handling working
- [ ] TCP keepalive configured
- [ ] YAML configuration loading
- [ ] Service registry integration
- [ ] Documentation updated
- [ ] Migration guide created

---

**Next Step**: Begin Phase 1 - Add Configuration Layer
