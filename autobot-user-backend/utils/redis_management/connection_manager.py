# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Connection Manager Module

Centralized Redis connection manager with circuit breaker and health monitoring.

Features:
- Connection pooling with TCP keepalive
- Circuit breaker pattern
- Health monitoring
- Statistics tracking
- WeakSet connection tracking
- Async and sync support

Extracted from redis_client.py as part of Issue #381 refactoring.
"""

import asyncio
import logging
import socket
import time
import weakref
from contextlib import asynccontextmanager
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional, Union

import redis
import redis.asyncio as async_redis
from redis.asyncio.connection import SSLConnection as AsyncSSLConnection
from redis.backoff import ExponentialBackoff
from redis.connection import ConnectionPool, SSLConnection
from redis.exceptions import ConnectionError, ResponseError
from redis.retry import Retry

from src.config import config as config_manager
from src.constants.network_constants import NetworkConstants
from src.constants.threshold_constants import RetryConfig, TimingConstants
from src.monitoring.prometheus_metrics import get_metrics_manager
from src.utils.redis_management.config import PoolConfig, RedisConfig, RedisConfigLoader
from src.utils.redis_management.statistics import (
    ConnectionMetrics,
    ManagerStats,
    PoolStatistics,
    RedisStats,
)
from src.utils.redis_management.types import DATABASE_MAPPING, ConnectionState

logger = logging.getLogger(__name__)


class RedisConnectionManager:
    """
    Centralized Redis connection manager with circuit breaker and health monitoring.

    CONNECTION POOLING (Issue #743):
    =================================
    This manager implements SINGLETON CONNECTION POOLS for memory efficiency:

    - Pools are created ONCE per database and reused for all requests
    - _sync_pools: Dict[str, ConnectionPool] - one sync pool per database
    - _async_pools: Dict[str, ConnectionPool] - one async pool per database
    - Each pool maintains up to MAX_CONNECTIONS_POOL connections (default: 20)
    - Connections are borrowed from pool and returned after use
    - Idle connections are automatically cleaned up

    When you call get_sync_client("main") 100 times, you get 100 client objects
    but they all share THE SAME underlying connection pool of max 20 connections.

    Consolidates features from:
    - redis_pool_manager.py: Connection pooling, metrics
    - async_redis_manager.py: Circuit breaker, health monitoring
    - redis_client.py: Database name mapping, convenience functions
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        """Singleton pattern for connection manager."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initialize connection manager (only once due to singleton).

        Features:
        - WeakSet tracking
        - Loading dataset handling
        - Tenacity retry
        - TCP keepalive
        - Idle cleanup
        - Comprehensive statistics

        Refactored for Issue #620.
        """
        if hasattr(self, "_initialized"):
            return

        # Initialize all subsystems using helper methods. Issue #620.
        self._init_pool_and_client_storage()
        self._init_circuit_breaker_state()
        self._init_tcp_keepalive_options()
        self._init_connection_tracking()
        self._init_configurations()
        self._init_statistics_tracking()
        self._init_cleanup_configuration()

        self._initialized = True
        logger.info(
            "Enhanced Redis Connection Manager initialized with consolidated features"
        )

    def _init_pool_and_client_storage(self):
        """
        Initialize pool and client storage dictionaries.

        Sets up storage for sync/async pools, clients, metrics, and states.
        Issue #620.
        """
        self._sync_pools: Dict[str, ConnectionPool] = {}
        self._async_pools: Dict[str, async_redis.ConnectionPool] = {}
        self._clients: Dict[str, Union[redis.Redis, async_redis.Redis]] = {}
        self._metrics: Dict[str, ConnectionMetrics] = {}
        self._states: Dict[str, ConnectionState] = {}
        self._init_lock = Lock()
        self._async_lock = asyncio.Lock()

    def _init_circuit_breaker_state(self):
        """
        Initialize circuit breaker state tracking.

        Sets up failure counts, timing, and circuit state dictionaries.
        Issue #620.
        """
        self._failure_counts: Dict[str, int] = {}
        self._last_failure_times: Dict[str, float] = {}
        self._circuit_open: Dict[str, bool] = {}

    def _init_tcp_keepalive_options(self):
        """
        Initialize TCP keepalive configuration.

        Configures keepalive probes to detect dead connections.
        Must be called before _init_configurations. Issue #620.
        """
        self._tcp_keepalive_options = {
            socket.TCP_KEEPIDLE: 600,  # Seconds before sending keepalive probes
            socket.TCP_KEEPINTVL: 60,  # Interval between keepalive probes
            socket.TCP_KEEPCNT: 5,  # Number of keepalive probes
        }

    def _init_connection_tracking(self):
        """
        Initialize connection tracking structures.

        Sets up response time tracking, active connections, and WeakSet tracking.
        Issue #620.
        """
        # Response time tracking
        self._request_times: Dict[str, List[float]] = {}
        self._max_response_times = 100  # Keep last 100 response times

        # Active connections tracking
        self._active_connections: Dict[str, weakref.WeakSet] = {}

        # WeakSet connection tracking (doesn't prevent GC)
        self._active_sync_connections: weakref.WeakSet = weakref.WeakSet()
        self._active_async_connections: weakref.WeakSet = weakref.WeakSet()

    def _init_configurations(self):
        """
        Initialize and load all configurations.

        Loads from multiple sources with priority ordering.
        Issue #620.
        """
        # Load configurations from multiple sources
        self._configs: Dict[str, RedisConfig] = {}
        self._load_configurations()

        # Load existing configuration (backward compatibility)
        self._config = self._load_redis_config()
        self._pool_config = self._load_pool_config()

    def _init_statistics_tracking(self):
        """
        Initialize enhanced statistics tracking.

        Sets up database stats, manager stats, and start time.
        Issue #620.
        """
        self._database_stats: Dict[str, RedisStats] = {}
        self._manager_stats = ManagerStats(
            total_databases=0,
            healthy_databases=0,
            degraded_databases=0,
            failed_databases=0,
        )
        self._start_time = datetime.now()

    def _init_cleanup_configuration(self):
        """
        Initialize idle connection cleanup and background tasks.

        Configures cleanup intervals and task storage.
        Issue #620.
        """
        # Idle connection cleanup configuration
        self._max_idle_time_seconds = 300  # 5 minutes
        self._cleanup_interval_seconds = 60  # Check every minute

        # Background tasks
        self._health_check_tasks: Dict[str, asyncio.Task] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    def _load_redis_config(self) -> Dict[str, Any]:
        """Load Redis configuration from unified config."""
        redis_config = config_manager.get_redis_config()

        return {
            "host": redis_config.get("host", NetworkConstants.REDIS_VM_IP),
            "port": redis_config.get("port", NetworkConstants.REDIS_PORT),
            "password": redis_config.get("password"),
            "enabled": redis_config.get("enabled", True),
        }

    def _load_pool_config(self) -> PoolConfig:
        """Load pool configuration from unified config."""
        redis_config = config_manager.get_redis_config()

        return PoolConfig(
            max_connections=redis_config.get("max_connections", 100),
            socket_timeout=redis_config.get("socket_timeout", 5.0),
            socket_connect_timeout=redis_config.get("socket_connect_timeout", 5.0),
            retry_on_timeout=redis_config.get("retry_on_timeout", True),
            max_retries=redis_config.get("max_retries", RetryConfig.DEFAULT_RETRIES),
            health_check_interval=redis_config.get("health_check_interval", 30.0),
            circuit_breaker_threshold=redis_config.get("circuit_breaker_threshold", 5),
            circuit_breaker_timeout=redis_config.get("circuit_breaker_timeout", 60),
        )

    def _load_configurations(self):
        """
        Load configurations from multiple sources with priority.

        Priority order:
        1. YAML file configuration
        2. Service registry configuration
        3. Default configuration with timeout config
        """
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
            socket_timeout=timeout_config.get("socket_timeout", 5.0),
            socket_connect_timeout=timeout_config.get("socket_connect_timeout", 5.0),
            retry_on_timeout=timeout_config.get("retry_on_timeout", True),
            max_retries=timeout_config.get("max_retries", RetryConfig.DEFAULT_RETRIES),
            socket_keepalive_options=(
                self._tcp_keepalive_options
                if hasattr(self, "_tcp_keepalive_options")
                else None
            ),
        )
        if "main" not in self._configs:
            self._configs["main"] = default_config

        logger.debug("Loaded configurations for %s databases", len(self._configs))

    # =========================================================================
    # Advanced Connection Methods
    # =========================================================================

    async def _wait_for_redis_ready(
        self, client: async_redis.Redis, database_name: str, max_wait: int = 60
    ) -> bool:
        """
        Wait for Redis to finish loading dataset and be ready.

        Handles: "LOADING Redis is loading the dataset in memory" errors.
        Essential during Redis startup/restart.

        Args:
            client: Async Redis client to test
            database_name: Database name for logging
            max_wait: Maximum wait time in seconds

        Returns:
            True if Redis is ready, False if timeout
        """
        start_time = datetime.now()

        while (datetime.now() - start_time).total_seconds() < max_wait:
            try:
                await client.ping()
                logger.info("Redis database '%s' is ready", database_name)
                return True
            except ResponseError as e:
                if "LOADING" in str(e):
                    logger.warning(
                        f"Redis '{database_name}' loading dataset, waiting... "
                        f"({int((datetime.now() - start_time).total_seconds())}s elapsed)"
                    )
                    await asyncio.sleep(TimingConstants.STANDARD_DELAY)
                else:
                    raise
            except Exception as e:
                logger.error(
                    f"Error checking Redis readiness for '{database_name}': {e}"
                )
                return False

        logger.error(
            "Redis '%s' did not become ready within %ss", database_name, max_wait
        )
        return False

    def _build_async_pool_params(self, config: RedisConfig, database_name: str) -> dict:
        """
        Build connection pool parameters for async Redis.

        Issue #665: Extracted from _create_async_pool_with_retry to reduce function length.

        Args:
            config: Redis configuration
            database_name: Name of database for logging

        Returns:
            Dictionary of pool parameters
        """
        pool_params = {
            "host": config.host,
            "port": config.port,
            "db": config.db,
            "password": config.password,
            "decode_responses": config.decode_responses,
            "max_connections": config.max_connections,
            "socket_timeout": config.socket_timeout,
            "socket_connect_timeout": config.socket_connect_timeout,
            "socket_keepalive": config.socket_keepalive,
            "socket_keepalive_options": config.socket_keepalive_options
            or self._tcp_keepalive_options,
            "retry_on_timeout": config.retry_on_timeout,
            "health_check_interval": 0,
        }

        # Add TLS parameters if enabled
        # Use connection_class=AsyncSSLConnection for proper TLS handling
        if config.ssl:
            pool_params["connection_class"] = AsyncSSLConnection
            if config.ssl_ca_certs:
                pool_params["ssl_ca_certs"] = config.ssl_ca_certs
            if config.ssl_certfile:
                pool_params["ssl_certfile"] = config.ssl_certfile
            if config.ssl_keyfile:
                pool_params["ssl_keyfile"] = config.ssl_keyfile
            pool_params["ssl_cert_reqs"] = config.ssl_cert_reqs or "required"
            logger.info(f"TLS enabled for async Redis connection '{database_name}'")

        return pool_params

    async def _create_async_pool_with_retry(
        self, database_name: str, config: RedisConfig
    ) -> async_redis.ConnectionPool:
        """
        Create async pool with retry logic.

        Issue #665: Refactored to use _build_async_pool_params helper.

        Features:
        - Manual retry with exponential backoff
        - Up to 5 attempts
        - TCP keepalive configuration
        """
        logger.warning(f"Creating async pool for '{database_name}' with MANUAL RETRY")
        max_attempts, base_wait, max_wait = 5, 2, 30

        for attempt in range(max_attempts):
            try:
                # Issue #665: Use helper to build params
                pool_params = self._build_async_pool_params(config, database_name)
                pool = async_redis.ConnectionPool(**pool_params)

                # Test connection and wait for Redis to be ready
                client = async_redis.Redis(connection_pool=pool)
                ready = await self._wait_for_redis_ready(client, database_name)
                await client.aclose()

                if not ready:
                    await pool.disconnect()
                    raise ConnectionError(
                        f"Redis database '{database_name}' not ready after waiting"
                    )

                logger.info(
                    f"Created async pool for '{database_name}' with retry protection"
                )
                return pool

            except (ConnectionError, asyncio.TimeoutError) as e:
                if attempt < max_attempts - 1:
                    wait_time = min(base_wait * (2**attempt), max_wait)
                    logger.warning(
                        f"Redis connection attempt {attempt + 1}/{max_attempts} failed "
                        f"for '{database_name}', retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"All {max_attempts} connection attempts failed for '{database_name}'"
                    )
                    raise

    def _apply_tls_params(
        self, pool_params: Dict[str, Any], config: RedisConfig, database_name: str
    ) -> None:
        """Apply TLS parameters to pool configuration if TLS is enabled.

        Args:
            pool_params: Pool parameters dictionary to modify in-place
            config: Redis configuration with TLS settings
            database_name: Name of database for logging. Issue #620.
        """
        if not config.ssl:
            return

        pool_params["connection_class"] = SSLConnection
        if config.ssl_ca_certs:
            pool_params["ssl_ca_certs"] = config.ssl_ca_certs
        if config.ssl_certfile:
            pool_params["ssl_certfile"] = config.ssl_certfile
        if config.ssl_keyfile:
            pool_params["ssl_keyfile"] = config.ssl_keyfile
        pool_params["ssl_cert_reqs"] = config.ssl_cert_reqs or "required"
        logger.info(f"TLS enabled for sync Redis connection '{database_name}'")

    def _create_sync_pool_with_keepalive(
        self, database_name: str, config: RedisConfig
    ) -> redis.ConnectionPool:
        """
        Create sync pool with TCP keepalive tuning.

        Features:
        - TCP keepalive configuration (prevents connection drops)
        - Exponential backoff retry
        - Parameter filtering
        """
        retry_policy = Retry(
            backoff=ExponentialBackoff(base=0.008, cap=10.0),
            retries=config.max_retries,
        )

        pool_params = {
            "host": config.host,
            "port": config.port,
            "db": config.db,
            "password": config.password,
            "decode_responses": config.decode_responses,
            "max_connections": config.max_connections,
            "socket_timeout": config.socket_timeout,
            "socket_connect_timeout": config.socket_connect_timeout,
            "socket_keepalive": True,
            "socket_keepalive_options": (
                config.socket_keepalive_options or self._tcp_keepalive_options
            ),
            "retry_on_timeout": config.retry_on_timeout,
            "retry": retry_policy,
        }

        self._apply_tls_params(pool_params, config, database_name)
        pool_params = {k: v for k, v in pool_params.items() if v is not None}

        logger.info(
            f"Created sync pool for '{database_name}' with TCP keepalive tuning"
        )
        return redis.ConnectionPool(**pool_params)

    def _update_stats(self, database_name: str, success: bool, error: str = None):
        """
        Update database statistics.

        Tracks operations, errors, and timing for monitoring.
        Includes Prometheus metrics integration.
        """
        if database_name not in self._database_stats:
            self._database_stats[database_name] = RedisStats(
                database_name=database_name
            )

        stats = self._database_stats[database_name]
        if success:
            stats.successful_operations += 1
            stats.last_success_time = datetime.now()
        else:
            stats.failed_operations += 1
            stats.last_error = error
            stats.last_error_time = datetime.now()

        # Update manager stats
        self._manager_stats.total_operations += 1
        self._manager_stats.uptime_seconds = (
            datetime.now() - self._start_time
        ).total_seconds()

        # Record to Prometheus metrics
        try:
            metrics = get_metrics_manager()
            metrics.record_request(
                database=database_name, operation="general", success=success
            )
        except Exception as e:
            logger.debug("Failed to record Prometheus metrics: %s", e)

    def _get_database_number(self, database_name: str) -> int:
        """Get database number for a given database name."""
        if database_name not in DATABASE_MAPPING:
            logger.warning(
                f"Unknown database name '{database_name}', defaulting to DB 0. "
                f"Available: {sorted(DATABASE_MAPPING)}"
            )
        return DATABASE_MAPPING.get(database_name, 0)

    def _check_circuit_breaker(self, database_name: str) -> bool:
        """Check if circuit breaker is open for a database."""
        if database_name not in self._circuit_open:
            self._circuit_open[database_name] = False
            self._failure_counts[database_name] = 0

        # Check if circuit should be reset
        if self._circuit_open[database_name]:
            last_failure = self._last_failure_times.get(database_name, 0)
            if time.time() - last_failure > self._pool_config.circuit_breaker_timeout:
                logger.info(
                    f"Circuit breaker reset for database '{database_name}' after timeout"
                )
                self._circuit_open[database_name] = False
                self._failure_counts[database_name] = 0

        return self._circuit_open[database_name]

    def _record_failure(self, database_name: str, error: Exception):
        """Record a connection failure and update circuit breaker."""
        if database_name not in self._failure_counts:
            self._failure_counts[database_name] = 0
            self._circuit_open[database_name] = False

        self._failure_counts[database_name] += 1
        self._last_failure_times[database_name] = time.time()

        # Update metrics
        if database_name not in self._metrics:
            self._metrics[database_name] = ConnectionMetrics()

        metrics = self._metrics[database_name]
        metrics.failed_connections += 1
        metrics.failed_requests += 1
        metrics.last_error = str(error)
        metrics.last_error_time = time.time()

        # Open circuit breaker if threshold exceeded
        if (
            self._failure_counts[database_name]
            >= self._pool_config.circuit_breaker_threshold
        ):
            self._circuit_open[database_name] = True
            metrics.circuit_breaker_state = "open"
            logger.error(
                f"Circuit breaker opened for database '{database_name}' after "
                f"{self._failure_counts[database_name]} failures"
            )

            # Record circuit breaker event to Prometheus
            try:
                prom_metrics = get_metrics_manager()
                prom_metrics.record_circuit_breaker_event(
                    database=database_name,
                    event="opened",
                    reason=str(error)[:100],
                )
                prom_metrics.update_circuit_breaker_state(
                    database=database_name,
                    state="open",
                    failure_count=self._failure_counts[database_name],
                )
            except Exception as prom_err:
                logger.debug(
                    f"Failed to record Prometheus circuit breaker metrics: {prom_err}"
                )

    def _record_success(self, database_name: str, response_time_ms: float):
        """Record a successful operation."""
        if database_name in self._failure_counts:
            self._failure_counts[database_name] = 0

        if database_name not in self._metrics:
            self._metrics[database_name] = ConnectionMetrics()

        metrics = self._metrics[database_name]
        metrics.total_requests += 1
        metrics.last_success_time = time.time()
        metrics.circuit_breaker_state = "closed"

        # Track response times
        if database_name not in self._request_times:
            self._request_times[database_name] = []

        self._request_times[database_name].append(response_time_ms)

        # Keep only last N response times
        if len(self._request_times[database_name]) > self._max_response_times:
            self._request_times[database_name].pop(0)

        # Update average response time
        if self._request_times[database_name]:
            metrics.avg_response_time_ms = sum(
                self._request_times[database_name]
            ) / len(self._request_times[database_name])

    def _create_sync_pool(self, database_name: str) -> ConnectionPool:
        """
        Create synchronous Redis connection pool (SINGLETON - Issue #743).

        This pool is created ONCE per database and stored in self._sync_pools.
        All subsequent get_sync_client() calls for this database reuse this pool.

        Pool Configuration:
        - max_connections: 20 (from REDIS_CONFIG.MAX_CONNECTIONS_POOL)
        - socket_timeout: 5.0 seconds
        - TCP keepalive enabled
        - Exponential backoff retry
        """
        if database_name in self._configs:
            config = self._configs[database_name]
        else:
            db_number = self._get_database_number(database_name)
            config = RedisConfig(
                name=database_name,
                db=db_number,
                host=self._config["host"],
                port=self._config["port"],
                password=self._config.get("password"),
                max_connections=self._pool_config.max_connections,
                socket_timeout=self._pool_config.socket_timeout,
                socket_connect_timeout=self._pool_config.socket_connect_timeout,
                retry_on_timeout=self._pool_config.retry_on_timeout,
                max_retries=self._pool_config.max_retries,
            )

        return self._create_sync_pool_with_keepalive(database_name, config)

    async def _create_async_pool(
        self, database_name: str
    ) -> async_redis.ConnectionPool:
        """
        Create asynchronous Redis connection pool (SINGLETON - Issue #743).

        This pool is created ONCE per database and stored in self._async_pools.
        All subsequent get_async_client() calls for this database reuse this pool.

        Pool Configuration:
        - max_connections: 20 (from REDIS_CONFIG.MAX_CONNECTIONS_POOL)
        - socket_timeout: 5.0 seconds
        - TCP keepalive enabled
        - Manual retry with exponential backoff
        - Loading dataset handling
        """
        if database_name in self._configs:
            config = self._configs[database_name]
        else:
            db_number = self._get_database_number(database_name)
            config = RedisConfig(
                name=database_name,
                db=db_number,
                host=self._config["host"],
                port=self._config["port"],
                password=self._config.get("password"),
                max_connections=self._pool_config.max_connections,
                socket_timeout=self._pool_config.socket_timeout,
                socket_connect_timeout=self._pool_config.socket_connect_timeout,
                retry_on_timeout=self._pool_config.retry_on_timeout,
                max_retries=self._pool_config.max_retries,
                health_check_interval=self._pool_config.health_check_interval,
            )

        return await self._create_async_pool_with_retry(database_name, config)

    def _check_sync_client_preconditions(self, database_name: str) -> Optional[bool]:
        """
        Check preconditions before getting sync client.

        Returns None if preconditions pass, False if client should not be returned.
        Issue #620.
        """
        if not self._config.get("enabled", True):
            logger.warning("Redis is disabled in configuration")
            return False

        if self._check_circuit_breaker(database_name):
            logger.warning(
                f"Circuit breaker is open for database '{database_name}', rejecting request"
            )
            return False

        return None

    def _ensure_sync_pool_exists(self, database_name: str) -> None:
        """
        Ensure sync connection pool exists for database, creating if needed.

        Uses double-checked locking pattern for thread safety.
        Issue #620.
        """
        if database_name not in self._sync_pools:
            with self._init_lock:
                if database_name not in self._sync_pools:
                    self._sync_pools[database_name] = self._create_sync_pool(
                        database_name
                    )

    def _handle_sync_client_success(
        self, database_name: str, client: redis.Redis, start_time: float
    ) -> redis.Redis:
        """
        Handle successful sync client creation and connection verification.

        Records metrics and updates connection state.
        Issue #620.
        """
        self._active_sync_connections.add(client)
        response_time_ms = (time.time() - start_time) * 1000
        self._record_success(database_name, response_time_ms)
        self._update_stats(database_name, success=True)
        self._states[database_name] = ConnectionState.HEALTHY
        return client

    def _handle_sync_client_failure(self, database_name: str, error: Exception) -> None:
        """
        Handle sync client creation failure.

        Records failure metrics and updates connection state.
        Issue #620.
        """
        logger.error(
            f"Failed to get sync Redis client for database '{database_name}': {error}"
        )
        self._record_failure(database_name, error)
        self._update_stats(database_name, success=False, error=str(error))
        self._states[database_name] = ConnectionState.FAILED

    def get_sync_client(self, database_name: str = "main") -> Optional[redis.Redis]:
        """
        Get synchronous Redis client with circuit breaker.

        POOLING BEHAVIOR (Issue #743):
        ===============================
        Returns a client backed by a SINGLETON connection pool.
        Pool is created ONCE on first call and reused for subsequent calls.

        Features: Circuit breaker, TCP keepalive, WeakSet tracking, statistics.
        """
        precondition_result = self._check_sync_client_preconditions(database_name)
        if precondition_result is False:
            return None

        try:
            start_time = time.time()
            self._ensure_sync_pool_exists(database_name)

            client = redis.Redis(connection_pool=self._sync_pools[database_name])
            client.ping()

            return self._handle_sync_client_success(database_name, client, start_time)

        except Exception as e:
            self._handle_sync_client_failure(database_name, e)
            return None

    async def _ensure_async_pool_exists(self, database_name: str) -> None:
        """
        Ensure async connection pool exists for database, creating if needed.

        Uses double-checked locking pattern for thread safety.
        Issue #620.
        """
        if database_name not in self._async_pools:
            async with self._async_lock:
                if database_name not in self._async_pools:
                    self._async_pools[database_name] = await self._create_async_pool(
                        database_name
                    )

    async def _create_and_verify_async_client(
        self, database_name: str
    ) -> async_redis.Redis:
        """
        Create async Redis client from pool and verify connection.

        Issue #620.
        """
        client = async_redis.Redis(connection_pool=self._async_pools[database_name])
        await client.ping()
        self._active_async_connections.add(client)
        return client

    async def get_async_client(
        self, database_name: str = "main"
    ) -> Optional[async_redis.Redis]:
        """
        Get asynchronous Redis client with circuit breaker.

        POOLING BEHAVIOR (Issue #743):
        ===============================
        Returns a client backed by a SINGLETON async connection pool.
        The pool is created ONCE on first call and reused for subsequent calls.

        Features: Circuit breaker, loading dataset handling, TCP keepalive,
        WeakSet tracking, enhanced statistics.
        """
        if not self._config.get("enabled", True):
            logger.warning("Redis is disabled in configuration")
            return None

        if self._check_circuit_breaker(database_name):
            logger.warning(
                f"Circuit breaker is open for database '{database_name}', rejecting request"
            )
            return None

        try:
            start_time = time.time()
            await self._ensure_async_pool_exists(database_name)
            client = await self._create_and_verify_async_client(database_name)

            response_time_ms = (time.time() - start_time) * 1000
            self._record_success(database_name, response_time_ms)
            self._update_stats(database_name, success=True)
            self._states[database_name] = ConnectionState.HEALTHY

            return client

        except Exception as e:
            logger.error(
                f"Failed to get async Redis client for database '{database_name}': {e}"
            )
            self._record_failure(database_name, e)
            self._update_stats(database_name, success=False, error=str(e))
            self._states[database_name] = ConnectionState.FAILED
            return None

    def get_metrics(self, database_name: Optional[str] = None) -> Dict[str, Any]:
        """Get connection metrics."""

        def _metrics_to_dict(metrics: ConnectionMetrics) -> Dict[str, Any]:
            data = metrics.__dict__.copy()
            data["success_rate"] = metrics.success_rate
            return data

        if database_name:
            return {
                database_name: _metrics_to_dict(
                    self._metrics.get(database_name, ConnectionMetrics())
                )
            }
        else:
            return {
                db: _metrics_to_dict(metrics) for db, metrics in self._metrics.items()
            }

    def get_health_status(self) -> Dict[str, Any]:
        """Get overall health status."""
        total_dbs = len(self._states)
        healthy_dbs = sum(
            1 for state in self._states.values() if state == ConnectionState.HEALTHY
        )

        total_requests = sum(m.total_requests for m in self._metrics.values())
        total_failures = sum(m.failed_requests for m in self._metrics.values())

        return {
            "overall_healthy": healthy_dbs == total_dbs if total_dbs > 0 else False,
            "total_databases": total_dbs,
            "healthy_databases": healthy_dbs,
            "total_requests": total_requests,
            "total_failures": total_failures,
            "success_rate": (
                ((total_requests - total_failures) / total_requests * 100)
                if total_requests > 0
                else 100.0
            ),
            "databases": {
                db: {
                    "state": state.value,
                    "metrics": self._metrics.get(db, ConnectionMetrics()).__dict__,
                }
                for db, state in self._states.items()
            },
        }

    # =========================================================================
    # Named Database Methods
    # =========================================================================

    async def main(self) -> Optional[async_redis.Redis]:
        """Get async client for main database."""
        return await self.get_async_client("main")

    async def knowledge(self) -> Optional[async_redis.Redis]:
        """Get async client for knowledge database."""
        return await self.get_async_client("knowledge")

    async def prompts(self) -> Optional[async_redis.Redis]:
        """Get async client for prompts database."""
        return await self.get_async_client("prompts")

    async def agents(self) -> Optional[async_redis.Redis]:
        """Get async client for agents database."""
        return await self.get_async_client("agents")

    async def metrics(self) -> Optional[async_redis.Redis]:
        """Get async client for metrics database."""
        return await self.get_async_client("metrics")

    async def sessions(self) -> Optional[async_redis.Redis]:
        """Get async client for sessions database."""
        return await self.get_async_client("sessions")

    async def workflows(self) -> Optional[async_redis.Redis]:
        """Get async client for workflows database."""
        return await self.get_async_client("workflows")

    async def vectors(self) -> Optional[async_redis.Redis]:
        """Get async client for vectors database."""
        return await self.get_async_client("vectors")

    async def models(self) -> Optional[async_redis.Redis]:
        """Get async client for models database."""
        return await self.get_async_client("models")

    async def memory(self) -> Optional[async_redis.Redis]:
        """Get async client for memory database."""
        return await self.get_async_client("memory")

    async def analytics(self) -> Optional[async_redis.Redis]:
        """Get async client for analytics database."""
        return await self.get_async_client("analytics")

    @asynccontextmanager
    async def pipeline(self, database: str = "main"):
        """
        Context manager for Redis pipeline operations.

        Usage:
            async with manager.pipeline("main") as pipe:
                pipe.set("key1", "value1")
                pipe.set("key2", "value2")
                # Auto-executes on context exit
        """
        client = await self.get_async_client(database)
        if client is None:
            raise ConnectionError(
                f"Could not get Redis client for database '{database}'"
            )

        pipe = client.pipeline()
        try:
            yield pipe
            await pipe.execute()
        except Exception as e:
            logger.error("Pipeline error for '%s': %s", database, e)
            raise
        finally:
            await pipe.reset()

    def get_pool_statistics(self, database: str) -> PoolStatistics:
        """
        Get detailed connection pool statistics (thread-safe).

        Args:
            database: Database name to get statistics for

        Returns:
            PoolStatistics with pool metrics

        Raises:
            ValueError: If no pool exists for the database
        """
        pool = self._sync_pools.get(database)
        if not pool:
            raise ValueError(f"No sync pool found for database '{database}'")

        try:
            with pool._lock:
                created = getattr(pool, "_created_connections", 0)
                available_conns = getattr(pool, "_available_connections", [])
                in_use_conns = getattr(pool, "_in_use_connections", [])
                available = len(available_conns)
                in_use = len(in_use_conns)
                max_conn = pool.max_connections
                idle_count = self._count_idle_connections(available_conns)

            return PoolStatistics(
                database_name=database,
                created_connections=created,
                available_connections=available,
                in_use_connections=in_use,
                max_connections=max_conn,
                idle_connections=idle_count,
            )
        except Exception as e:
            logger.error("Error getting pool statistics for '%s': %s", database, e)
            return PoolStatistics(
                database_name=database,
                created_connections=0,
                available_connections=0,
                in_use_connections=0,
                max_connections=pool.max_connections,
                idle_connections=0,
            )

    def _count_idle_connections(
        self, available_conns: list, threshold: int = 60
    ) -> int:
        """Count connections idle longer than threshold."""
        idle_count = 0
        for conn in available_conns:
            if hasattr(conn, "_last_use"):
                idle_time = (datetime.now() - conn._last_use).total_seconds()
                if idle_time > threshold:
                    idle_count += 1
        return idle_count

    def _identify_idle_connections(self, available_conns: list) -> list:
        """Identify connections idle longer than max_idle_time."""
        connections_to_remove = []
        for conn in available_conns:
            if not hasattr(conn, "_last_use"):
                continue
            idle_time = (datetime.now() - conn._last_use).total_seconds()
            if idle_time > self._max_idle_time_seconds:
                connections_to_remove.append(conn)
        return connections_to_remove

    def _remove_idle_connection(self, pool: Any, conn: Any) -> bool:
        """Remove a single idle connection from pool."""
        try:
            pool._available_connections.remove(conn)
            conn.disconnect()
            return True
        except ValueError:
            return False
        except Exception as e:
            logger.debug("Could not remove idle connection: %s", e)
            return False

    async def cleanup_idle_connections(self):
        """Clean up idle connections older than max_idle_time."""
        cleaned_total = 0

        for database_name, pool in list(self._sync_pools.items()):
            cleaned_count = self._cleanup_pool_idle_connections(database_name, pool)
            cleaned_total += cleaned_count

        if cleaned_total > 0:
            logger.info("Total idle connections cleaned: %s", cleaned_total)

    def _cleanup_pool_idle_connections(self, database_name: str, pool: Any) -> int:
        """Clean idle connections from a single pool."""
        try:
            cleaned_count = 0

            with pool._lock:
                available_conns = getattr(pool, "_available_connections", [])
                connections_to_remove = self._identify_idle_connections(available_conns)

                for conn in connections_to_remove:
                    if self._remove_idle_connection(pool, conn):
                        cleaned_count += 1

            if cleaned_count > 0:
                logger.info(
                    f"Cleaned up {cleaned_count} idle connections for '{database_name}'"
                )
            return cleaned_count

        except Exception as e:
            logger.error(
                "Error cleaning idle connections for '%s': %s", database_name, e
            )
            return 0

    async def _cleanup_idle_connections_task(self):
        """Background task to clean up idle connections periodically."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval_seconds)
                await self.cleanup_idle_connections()
            except asyncio.CancelledError:
                logger.info("Idle connection cleanup task cancelled")
                break
            except Exception as e:
                logger.error("Error in idle connection cleanup task: %s", e)

    def get_statistics(self) -> ManagerStats:
        """Get comprehensive manager statistics."""
        self._manager_stats.total_databases = len(self._configs)
        self._manager_stats.healthy_databases = sum(
            1 for state in self._states.values() if state == ConnectionState.HEALTHY
        )
        self._manager_stats.degraded_databases = sum(
            1 for state in self._states.values() if state == ConnectionState.DEGRADED
        )
        self._manager_stats.failed_databases = sum(
            1 for state in self._states.values() if state == ConnectionState.FAILED
        )

        self._manager_stats.uptime_seconds = (
            datetime.now() - self._start_time
        ).total_seconds()

        self._manager_stats.database_stats = self._database_stats.copy()

        return self._manager_stats

    async def close_all(self):
        """Close all connections and cleanup background tasks."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                logger.debug("Redis cleanup task cancelled during shutdown")

        for pool in self._async_pools.values():
            try:
                await pool.aclose()
            except Exception as e:
                logger.warning("Error closing async pool: %s", e)

        for pool in self._sync_pools.values():
            try:
                pool.disconnect()
            except Exception as e:
                logger.warning("Error closing sync pool: %s", e)

        self._sync_pools.clear()
        self._async_pools.clear()
        self._clients.clear()

        logger.info("All Redis connections closed")
