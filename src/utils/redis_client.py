# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Client - CANONICAL REDIS PATTERN (CONSOLIDATED)
======================================================

This module provides the ONLY approved method for Redis client initialization
across the AutoBot codebase. Direct redis.Redis() instantiation is FORBIDDEN.

FEATURES (Consolidated from 6 implementations):
================================================
✅ Circuit breaker pattern
✅ Health monitoring
✅ Connection pooling with TCP keepalive tuning
✅ Comprehensive statistics and metrics
✅ Database name mapping with type-safe enums
✅ Async and sync support (unified interface)
✅ Automatic retry with exponential backoff + tenacity
✅ Connection state management
✅ "Loading dataset" state handling (waits for Redis startup)
✅ WeakSet connection tracking (no GC interference)
✅ Pipeline context managers
✅ Named database convenience methods
✅ Idle connection cleanup
✅ YAML configuration loading
✅ Service registry integration
✅ Centralized timeout configuration

MANDATORY USAGE PATTERN:
========================
from src.utils.redis_client import get_redis_client

# Synchronous client
redis_client = get_redis_client(database="main")
redis_client.set("key", "value")

# Asynchronous client
async_redis = await get_redis_client(async_client=True, database="main")
await async_redis.set("key", "value")

DATABASE SEPARATION:
===================
- 'main': General application cache, queues, session data
- 'knowledge': Knowledge base vectors and embeddings
- 'prompts': LLM prompt templates and agent configurations
- 'agents': Agent communication and orchestration state
- 'metrics': Performance metrics and analytics data
- 'analytics': Codebase analytics and indexing state
- 'sessions': User session data
- 'workflows': Workflow state tracking
- 'vectors': Vector embeddings
- 'models': Model metadata

ARCHITECTURE:
============
redis_client.py (THIS FILE - CONSOLIDATED)
    └─> RedisConnectionManager (enhanced with all features)
            └─> redis_database_manager (DB name mapping)
                    └─> redis.ConnectionPool (optimized pooling)
                            └─> NetworkConstants.REDIS_VM_IP:REDIS_PORT
"""

import asyncio
import logging
import os
import socket
import time
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
from weakref import WeakSet

import redis
import redis.asyncio as async_redis
import yaml
from redis.backoff import ExponentialBackoff
from redis.connection import ConnectionPool
from redis.exceptions import ConnectionError, ResponseError
from redis.retry import Retry

from src.constants.network_constants import NetworkConstants
from src.monitoring.prometheus_metrics import get_metrics_manager
from src.unified_config_manager import config as config_manager

logger = logging.getLogger(__name__)


# ============================================================================
# PHASE 1: Configuration Layer (from redis_database_manager.py + redis_helper.py)
# ============================================================================


class RedisDatabase(Enum):
    """Type-safe database enumeration"""

    MAIN = 0
    KNOWLEDGE = 1
    PROMPTS = 2
    AGENTS = 3
    METRICS = 4
    LOGS = 5
    SESSIONS = 6
    WORKFLOWS = 7
    VECTORS = 8
    MODELS = 9
    MEMORY = 9  # Shares DB 9 with models
    ANALYTICS = 11
    AUDIT = 10
    NOTIFICATIONS = 12
    JOBS = 13
    SEARCH = 14
    TIMESERIES = 15
    TESTING = 15  # Shares with timeseries


@dataclass
class RedisConfig:
    """Redis database configuration"""

    name: str
    db: int
    host: str = NetworkConstants.REDIS_VM_IP
    port: int = NetworkConstants.REDIS_PORT
    password: Optional[str] = None
    decode_responses: bool = True
    max_connections: int = 100
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    socket_keepalive: bool = True
    socket_keepalive_options: Optional[Dict[int, int]] = None
    health_check_interval: int = 30
    retry_on_timeout: bool = True
    max_retries: int = 3
    description: str = ""

    def __post_init__(self):
        """Auto-load password from environment if not provided"""
        if self.password is None:
            # Try REDIS_PASSWORD first, then AUTOBOT_REDIS_PASSWORD
            self.password = os.getenv("REDIS_PASSWORD") or os.getenv(
                "AUTOBOT_REDIS_PASSWORD"
            )


class RedisConfigLoader:
    """Load Redis configurations from multiple sources"""

    @staticmethod
    def load_from_yaml(yaml_path: str = None) -> Dict[str, RedisConfig]:
        """
        Load configurations from YAML file

        Priority paths (container-aware):
        1. Provided yaml_path
        2. /app/config/redis-databases.yaml (container)
        3. ./config/redis-databases.yaml (host relative)
        4. /home/kali/Desktop/AutoBot/config/redis-databases.yaml (host absolute)
        """
        if yaml_path is None:
            # Auto-detect container vs host environment
            possible_paths = [
                "/app/config/redis-databases.yaml",  # Container
                "./config/redis-databases.yaml",  # Host relative
                "/home/kali/Desktop/AutoBot/config/redis-databases.yaml",  # Host absolute
            ]

            for path in possible_paths:
                if os.path.exists(path):
                    yaml_path = path
                    break

        if not yaml_path or not os.path.exists(yaml_path):
            logger.debug("No YAML configuration file found, using defaults")
            return {}

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            configs = {}
            databases = config_data.get(
                "redis_databases", config_data.get("databases", {})
            )

            for db_name, db_config in databases.items():
                configs[db_name] = RedisConfig(
                    name=db_name,
                    db=db_config.get("db", 0),
                    host=db_config.get("host", NetworkConstants.REDIS_VM_IP),
                    port=db_config.get("port", NetworkConstants.REDIS_PORT),
                    password=db_config.get("password"),
                    decode_responses=db_config.get("decode_responses", True),
                    max_connections=db_config.get("max_connections", 100),
                    socket_timeout=db_config.get("socket_timeout", 5.0),
                    socket_connect_timeout=db_config.get("socket_connect_timeout", 5.0),
                    socket_keepalive=db_config.get("socket_keepalive", True),
                    health_check_interval=db_config.get("health_check_interval", 30),
                    retry_on_timeout=db_config.get("retry_on_timeout", True),
                    max_retries=db_config.get("max_retries", 3),
                    description=db_config.get("description", ""),
                )

            logger.info(
                f"Loaded {len(configs)} database configurations from {yaml_path}"
            )
            return configs

        except Exception as e:
            logger.error(f"Error loading YAML config from {yaml_path}: {e}")
            return {}

    @staticmethod
    def load_from_service_registry() -> Dict[str, RedisConfig]:
        """Load configurations from service registry"""
        try:
            from src.utils.service_registry import get_service_registry

            registry = get_service_registry()
            redis_config = registry.get_service_config("redis")

            if redis_config:
                # Convert service registry format to RedisConfig
                return {
                    "main": RedisConfig(
                        name="main",
                        db=0,
                        host=redis_config.host,
                        port=redis_config.port,
                        password=(
                            redis_config.password
                            if hasattr(redis_config, "password")
                            else None
                        ),
                    )
                }
        except (ImportError, Exception) as e:
            logger.debug(f"Could not load from service registry: {e}")

        return {}

    @staticmethod
    def load_timeout_config() -> dict:
        """Load centralized timeout configuration"""
        try:
            from src.config.timeout_config import get_redis_timeout_config

            return get_redis_timeout_config()
        except (ImportError, AttributeError):
            # Fallback to default configuration
            return {
                "socket_timeout": 5.0,
                "socket_connect_timeout": 5.0,
                "retry_on_timeout": True,
                "max_retries": 3,
            }


class ConnectionState(Enum):
    """Redis connection states for circuit breaker pattern"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


# ============================================================================
# PHASE 2: Statistics Layer (from backend/async_redis_manager.py + optimized_redis_manager.py)
# ============================================================================


@dataclass
class RedisStats:
    """Per-database Redis statistics (from backend/async_redis_manager.py)"""

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
    last_success_time: Optional[datetime] = None
    uptime_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        total = self.successful_operations + self.failed_operations
        if total == 0:
            return 100.0
        return (self.successful_operations / total) * 100.0


@dataclass
class PoolStatistics:
    """Connection pool statistics (from optimized_redis_manager.py)"""

    database_name: str
    created_connections: int
    available_connections: int
    in_use_connections: int
    max_connections: int
    idle_connections: int
    last_cleanup: Optional[datetime] = None


@dataclass
class ManagerStats:
    """Overall manager statistics (from backend/async_redis_manager.py)"""

    total_databases: int
    healthy_databases: int
    degraded_databases: int
    failed_databases: int
    total_operations: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    uptime_seconds: float = 0.0
    database_stats: Dict[str, RedisStats] = field(default_factory=dict)

    @property
    def overall_success_rate(self) -> float:
        """Calculate overall success rate"""
        total_success = sum(
            s.successful_operations for s in self.database_stats.values()
        )
        total_failed = sum(s.failed_operations for s in self.database_stats.values())
        total = total_success + total_failed
        if total == 0:
            return 100.0
        return (total_success / total) * 100.0


@dataclass
class ConnectionMetrics:
    """Connection metrics and statistics (legacy - keeping for backward compatibility)"""

    created_connections: int = 0
    active_connections: int = 0
    failed_connections: int = 0
    reconnections: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    avg_response_time_ms: float = 0.0
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    last_success_time: Optional[float] = None
    circuit_breaker_state: str = "closed"

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_requests == 0:
            return 100.0
        successful = self.total_requests - self.failed_requests
        return (successful / self.total_requests) * 100.0


@dataclass
class PoolConfig:
    """Redis connection pool configuration"""

    max_connections: int = 100  # Increased from 20 for concurrent operations
    min_connections: int = 2
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    retry_on_timeout: bool = True
    max_retries: int = 3
    backoff_factor: float = 2.0
    health_check_interval: float = 30.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 60  # seconds


class RedisConnectionManager:
    """
    Centralized Redis connection manager with circuit breaker and health monitoring.

    Consolidates features from:
    - redis_pool_manager.py: Connection pooling, metrics
    - async_redis_manager.py: Circuit breaker, health monitoring
    - redis_client.py: Database name mapping, convenience functions
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        """Singleton pattern for connection manager"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initialize connection manager (only once due to singleton)

        PHASE 3: Enhanced with WeakSet tracking, loading dataset handling,
        tenacity retry, TCP keepalive, idle cleanup, comprehensive statistics
        """
        if hasattr(self, "_initialized"):
            return

        # Existing attributes (backward compatibility)
        self._sync_pools: Dict[str, ConnectionPool] = {}
        self._async_pools: Dict[str, async_redis.ConnectionPool] = {}
        self._clients: Dict[str, Union[redis.Redis, async_redis.Redis]] = {}
        self._metrics: Dict[str, ConnectionMetrics] = {}
        self._states: Dict[str, ConnectionState] = {}
        self._init_lock = Lock()
        self._async_lock = asyncio.Lock()

        # Circuit breaker state (existing)
        self._failure_counts: Dict[str, int] = {}
        self._last_failure_times: Dict[str, float] = {}
        self._circuit_open: Dict[str, bool] = {}

        # Response time tracking (existing)
        self._request_times: Dict[str, List[float]] = {}
        self._max_response_times = 100  # Keep last 100 response times

        # Active connections tracking (existing)
        self._active_connections: Dict[str, WeakSet] = {}

        # PHASE 1: Load configurations from multiple sources
        self._configs: Dict[str, RedisConfig] = {}
        self._load_configurations()

        # Load existing configuration (backward compatibility)
        self._config = self._load_redis_config()
        self._pool_config = self._load_pool_config()

        # PHASE 2: NEW - Enhanced statistics tracking
        self._database_stats: Dict[str, RedisStats] = {}
        self._manager_stats = ManagerStats(
            total_databases=0,
            healthy_databases=0,
            degraded_databases=0,
            failed_databases=0,
        )
        self._start_time = datetime.now()

        # PHASE 3: NEW - WeakSet connection tracking (doesn't prevent GC)
        self._active_sync_connections: weakref.WeakSet = weakref.WeakSet()
        self._active_async_connections: weakref.WeakSet = weakref.WeakSet()

        # PHASE 3: NEW - TCP keepalive configuration (from optimized_redis_manager.py)
        # FIXED: Use correct Linux socket constants (not sequential numbers)
        self._tcp_keepalive_options = {
            socket.TCP_KEEPIDLE: 600,  # Seconds before sending keepalive probes
            socket.TCP_KEEPINTVL: 60,  # Interval between keepalive probes
            socket.TCP_KEEPCNT: 5,  # Number of keepalive probes
        }

        # PHASE 3: NEW - Idle connection cleanup configuration
        self._max_idle_time_seconds = 300  # 5 minutes
        self._cleanup_interval_seconds = 60  # Check every minute

        # PHASE 4: NEW - Background tasks
        self._health_check_tasks: Dict[str, asyncio.Task] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

        self._initialized = True
        logger.info(
            "Enhanced Redis Connection Manager initialized with consolidated features"
        )

    def _load_redis_config(self) -> Dict[str, Any]:
        """Load Redis configuration from unified config"""
        redis_config = config_manager.get_redis_config()

        return {
            "host": redis_config.get("host", NetworkConstants.REDIS_VM_IP),
            "port": redis_config.get("port", NetworkConstants.REDIS_PORT),
            "password": redis_config.get("password"),
            "enabled": redis_config.get("enabled", True),
        }

    def _load_pool_config(self) -> PoolConfig:
        """Load pool configuration from unified config"""
        redis_config = config_manager.get_redis_config()

        return PoolConfig(
            max_connections=redis_config.get("max_connections", 100),
            socket_timeout=redis_config.get("socket_timeout", 5.0),
            socket_connect_timeout=redis_config.get("socket_connect_timeout", 5.0),
            retry_on_timeout=redis_config.get("retry_on_timeout", True),
            max_retries=redis_config.get("max_retries", 3),
            health_check_interval=redis_config.get("health_check_interval", 30.0),
            circuit_breaker_threshold=redis_config.get("circuit_breaker_threshold", 5),
            circuit_breaker_timeout=redis_config.get("circuit_breaker_timeout", 60),
        )

    def _load_configurations(self):
        """
        PHASE 1: Load configurations from multiple sources with priority

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
            max_retries=timeout_config.get("max_retries", 3),
            socket_keepalive_options=(
                self._tcp_keepalive_options
                if hasattr(self, "_tcp_keepalive_options")
                else None
            ),
        )
        if "main" not in self._configs:
            self._configs["main"] = default_config

        logger.debug(f"Loaded configurations for {len(self._configs)} databases")

    # ============================================================================
    # PHASE 3: Advanced Connection Methods (from backend/async_redis_manager.py + optimized)
    # ============================================================================

    async def _wait_for_redis_ready(
        self, client: async_redis.Redis, database_name: str, max_wait: int = 60
    ) -> bool:
        """
        CRITICAL: Wait for Redis to finish loading dataset and be ready.

        Handles: "LOADING Redis is loading the dataset in memory" errors
        This is essential during Redis startup/restart and prevents connection failures.

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
                logger.info(f"Redis database '{database_name}' is ready")
                return True
            except ResponseError as e:
                if "LOADING" in str(e):
                    logger.warning(
                        f"Redis '{database_name}' loading dataset, waiting... "
                        f"({int((datetime.now() - start_time).total_seconds())}s elapsed)"
                    )
                    await asyncio.sleep(2)
                else:
                    raise
            except Exception as e:
                logger.error(
                    f"Error checking Redis readiness for '{database_name}': {e}"
                )
                return False

        logger.error(f"Redis '{database_name}' did not become ready within {max_wait}s")
        return False

    async def _create_async_pool_with_retry(
        self, database_name: str, config: RedisConfig
    ) -> async_redis.ConnectionPool:
        """
        PHASE 3: Create async pool with retry logic

        Features:
        - Manual retry with exponential backoff (removed @retry decorator to avoid coroutine reuse)
        - Up to 5 attempts
        - Retries on ConnectionError and TimeoutError
        - Loading dataset handling
        - TCP keepalive configuration
        """
        logger.warning(
            f"🔧 REDIS FIX ACTIVE: Creating async pool for '{database_name}' with MANUAL RETRY (no @retry decorator)"
        ),
        max_attempts = 5
        base_wait = 2
        max_wait = 30

        for attempt in range(max_attempts):
            try:
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
                    socket_keepalive_options=config.socket_keepalive_options
                    or self._tcp_keepalive_options,
                    retry_on_timeout=config.retry_on_timeout,
                    health_check_interval=0,  # Disable auto health checks - we check manually
                )

                # Test connection and wait for Redis to be ready (create fresh client each time)
                client = async_redis.Redis(connection_pool=pool)
                ready = await self._wait_for_redis_ready(client, database_name)
                await client.aclose()  # Close test client

                if not ready:
                    await pool.disconnect()  # Clean up pool before retry
                    raise ConnectionError(
                        f"Redis database '{database_name}' not ready after waiting"
                    )

                logger.info(
                    f"Created async pool for '{database_name}' with retry protection"
                )
                return pool

            except (ConnectionError, asyncio.TimeoutError) as e:
                if attempt < max_attempts - 1:
                    # Calculate exponential backoff wait time
                    wait_time = min(base_wait * (2**attempt), max_wait)
                    logger.warning(
                        f"Redis connection attempt {attempt + 1}/{max_attempts} failed for '{database_name}', "
                        f"retrying in {wait_time}s: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"All {max_attempts} connection attempts failed for '{database_name}'"
                    )
                    raise

    def _create_sync_pool_with_keepalive(
        self, database_name: str, config: RedisConfig
    ) -> redis.ConnectionPool:
        """
        PHASE 3: Create sync pool with TCP keepalive tuning

        Features:
        - TCP keepalive configuration (prevents connection drops)
        - Exponential backoff retry
        - Parameter filtering
        """
        retry_policy = Retry(
            backoff=ExponentialBackoff(base=0.008, cap=10.0),
            retries=config.max_retries,
        )

        # Filter None values (parameter filtering from redis_helper.py)
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

        # Remove None values
        pool_params = {k: v for k, v in pool_params.items() if v is not None}

        logger.info(
            f"Created sync pool for '{database_name}' with TCP keepalive tuning"
        )
        return redis.ConnectionPool(**pool_params)

    def _update_stats(self, database_name: str, success: bool, error: str = None):
        """
        PHASE 2: Update database statistics

        Tracks operations, errors, and timing for monitoring.
        Now includes Prometheus metrics integration for Issue #65 P1 optimization.
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

        # Record to Prometheus metrics for real-time monitoring
        try:
            metrics = get_metrics_manager()
            metrics.record_request(
                database=database_name, operation="general", success=success
            )
        except Exception as e:
            # Don't let metrics recording failure affect Redis operations
            logger.debug(f"Failed to record Prometheus metrics: {e}")

    def _get_database_number(self, database_name: str) -> int:
        """Get database number for a given database name"""
        # Use built-in database name mapping (consolidated from redis_database_manager)
        # Complete mapping matching all usage across AutoBot codebase
        db_mapping = {
            # Core databases
            "main": 0,
            "knowledge": 1,
            "prompts": 2,
            "agents": 3,
            "conversations": 3,  # Alias for agents (conversation storage)
            "metrics": 4,
            "cache": 5,
            "sessions": 6,
            "locks": 6,  # Alias for sessions (distributed locks)
            "workflows": 7,
            "monitoring": 7,  # Alias for workflows (monitoring data)
            "vectors": 8,
            "rate_limiting": 8,  # Alias for vectors (rate limit counters)
            "models": 9,
            "memory": 9,
            "analytics": 9,  # Maps to models/memory database
            "websockets": 10,
            "config": 11,  # CRITICAL: Cache configuration storage
            "audit": 12,  # Security audit logging (OWASP/NIST compliant)
        }
        if database_name not in db_mapping:
            logger.warning(
                f"Unknown database name '{database_name}', defaulting to DB 0. "
                f"Available: {sorted(db_mapping.keys())}"
            )
        return db_mapping.get(database_name, 0)

    def _check_circuit_breaker(self, database_name: str) -> bool:
        """Check if circuit breaker is open for a database"""
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
        """Record a connection failure and update circuit breaker"""
        # Initialize if needed
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
                    reason=str(error)[:100],  # Truncate for label safety
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
        """Record a successful operation"""
        # Reset failure count on success
        if database_name in self._failure_counts:
            self._failure_counts[database_name] = 0

        # Update metrics
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
        Create synchronous Redis connection pool (ENHANCED - Phase 3)

        Uses new _create_sync_pool_with_keepalive for TCP keepalive tuning
        """
        # Get config (try from loaded configs first, fallback to unified config)
        if database_name in self._configs:
            config = self._configs[database_name]
        else:
            # Fallback: create config from unified config manager
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
        Create asynchronous Redis connection pool (ENHANCED - Phase 3)

        Uses new _create_async_pool_with_retry for tenacity retry + loading dataset handling
        """
        # Get config (try from loaded configs first, fallback to unified config)
        if database_name in self._configs:
            config = self._configs[database_name]
        else:
            # Fallback: create config from unified config manager
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

    def get_sync_client(self, database_name: str = "main") -> Optional[redis.Redis]:
        """
        Get synchronous Redis client with circuit breaker (ENHANCED - Phase 3)

        Features:
        - Circuit breaker protection
        - TCP keepalive tuning
        - WeakSet connection tracking
        - Enhanced statistics collection
        """
        # Check if Redis is enabled
        if not self._config.get("enabled", True):
            logger.warning("Redis is disabled in configuration")
            return None

        # Check circuit breaker
        if self._check_circuit_breaker(database_name):
            logger.warning(
                f"Circuit breaker is open for database '{database_name}', rejecting request"
            )
            return None

        try:
            start_time = time.time()

            # Create pool if needed (uses new _create_sync_pool_with_keepalive)
            if database_name not in self._sync_pools:
                with self._init_lock:
                    if database_name not in self._sync_pools:
                        self._sync_pools[database_name] = self._create_sync_pool(
                            database_name
                        )

            # Create client from pool
            client = redis.Redis(connection_pool=self._sync_pools[database_name])

            # Test connection
            client.ping()

            # PHASE 3: Track connection in WeakSet (doesn't prevent GC)
            self._active_sync_connections.add(client)

            # Record success
            response_time_ms = (time.time() - start_time) * 1000
            self._record_success(database_name, response_time_ms)

            # PHASE 2: Update enhanced statistics
            self._update_stats(database_name, success=True)

            # Update state
            self._states[database_name] = ConnectionState.HEALTHY

            return client

        except Exception as e:
            logger.error(
                f"Failed to get sync Redis client for database '{database_name}': {e}"
            )
            self._record_failure(database_name, e)
            # PHASE 2: Update enhanced statistics with error
            self._update_stats(database_name, success=False, error=str(e))
            self._states[database_name] = ConnectionState.FAILED
            return None

    async def get_async_client(
        self, database_name: str = "main"
    ) -> Optional[async_redis.Redis]:
        """
        Get asynchronous Redis client with circuit breaker (ENHANCED - Phase 3)

        Features:
        - Circuit breaker protection
        - Loading dataset handling (waits for Redis startup)
        - Tenacity retry logic
        - TCP keepalive tuning
        - WeakSet connection tracking
        - Enhanced statistics collection
        """
        # Check if Redis is enabled
        if not self._config.get("enabled", True):
            logger.warning("Redis is disabled in configuration")
            return None

        # Check circuit breaker
        if self._check_circuit_breaker(database_name):
            logger.warning(
                f"Circuit breaker is open for database '{database_name}', rejecting request"
            )
            return None

        try:
            start_time = time.time()

            # Create pool if needed (uses new _create_async_pool_with_retry)
            # This handles loading dataset and uses tenacity retry
            if database_name not in self._async_pools:
                async with self._async_lock:
                    if database_name not in self._async_pools:
                        self._async_pools[database_name] = (
                            await self._create_async_pool(database_name)
                        )

            # Create client from pool
            client = async_redis.Redis(connection_pool=self._async_pools[database_name])

            # Test connection (no need to wait for loading dataset - already done in pool creation)
            await client.ping()

            # PHASE 3: Track connection in WeakSet (doesn't prevent GC)
            self._active_async_connections.add(client)

            # Record success
            response_time_ms = (time.time() - start_time) * 1000
            self._record_success(database_name, response_time_ms)

            # PHASE 2: Update enhanced statistics
            self._update_stats(database_name, success=True)

            # Update state
            self._states[database_name] = ConnectionState.HEALTHY

            return client

        except Exception as e:
            logger.error(
                f"Failed to get async Redis client for database '{database_name}': {e}"
            )
            self._record_failure(database_name, e)
            # PHASE 2: Update enhanced statistics with error
            self._update_stats(database_name, success=False, error=str(e))
            self._states[database_name] = ConnectionState.FAILED
            return None

    def get_metrics(self, database_name: Optional[str] = None) -> Dict[str, Any]:
        """Get connection metrics"""

        def _metrics_to_dict(metrics: ConnectionMetrics) -> Dict[str, Any]:
            """Convert metrics to dict, including computed properties"""
            data = metrics.__dict__.copy()
            data["success_rate"] = metrics.success_rate  # Add computed property
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
        """Get overall health status"""
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

    # ============================================================================
    # PHASE 4: Advanced Features (from backend/async_redis_manager.py + optimized)
    # ============================================================================

    async def main(self) -> Optional[async_redis.Redis]:
        """Get async client for main database"""
        return await self.get_async_client("main")

    async def knowledge(self) -> Optional[async_redis.Redis]:
        """Get async client for knowledge database"""
        return await self.get_async_client("knowledge")

    async def prompts(self) -> Optional[async_redis.Redis]:
        """Get async client for prompts database"""
        return await self.get_async_client("prompts")

    async def agents(self) -> Optional[async_redis.Redis]:
        """Get async client for agents database"""
        return await self.get_async_client("agents")

    async def metrics(self) -> Optional[async_redis.Redis]:
        """Get async client for metrics database"""
        return await self.get_async_client("metrics")

    async def sessions(self) -> Optional[async_redis.Redis]:
        """Get async client for sessions database"""
        return await self.get_async_client("sessions")

    async def workflows(self) -> Optional[async_redis.Redis]:
        """Get async client for workflows database"""
        return await self.get_async_client("workflows")

    async def vectors(self) -> Optional[async_redis.Redis]:
        """Get async client for vectors database"""
        return await self.get_async_client("vectors")

    async def models(self) -> Optional[async_redis.Redis]:
        """Get async client for models database"""
        return await self.get_async_client("models")

    async def memory(self) -> Optional[async_redis.Redis]:
        """Get async client for memory database"""
        return await self.get_async_client("memory")

    async def analytics(self) -> Optional[async_redis.Redis]:
        """Get async client for analytics database"""
        return await self.get_async_client("analytics")

    @asynccontextmanager
    async def pipeline(self, database: str = "main"):
        """
        Context manager for Redis pipeline operations

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
            logger.error(f"Pipeline error for '{database}': {e}")
            raise
        finally:
            await pipe.reset()

    def get_pool_statistics(self, database: str) -> PoolStatistics:
        """
        Get detailed connection pool statistics (thread-safe)

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
            # Thread-safe access to pool internals using pool's lock
            with pool._lock:
                # Get internal pool attributes safely
                created = getattr(pool, "_created_connections", 0)
                available_conns = getattr(pool, "_available_connections", [])
                in_use_conns = getattr(pool, "_in_use_connections", [])
                available = len(available_conns)
                in_use = len(in_use_conns)
                max_conn = pool.max_connections

                # Calculate idle connections (available for > 60s)
                idle_count = 0
                for conn in available_conns:
                    if hasattr(conn, "_last_use"):
                        idle_time = (datetime.now() - conn._last_use).total_seconds()
                        if idle_time > 60:
                            idle_count += 1

            return PoolStatistics(
                database_name=database,
                created_connections=created,
                available_connections=available,
                in_use_connections=in_use,
                max_connections=max_conn,
                idle_connections=idle_count,
            )
        except Exception as e:
            logger.error(f"Error getting pool statistics for '{database}': {e}")
            return PoolStatistics(
                database_name=database,
                created_connections=0,
                available_connections=0,
                in_use_connections=0,
                max_connections=pool.max_connections,
                idle_connections=0,
            )

    async def cleanup_idle_connections(self):
        """
        Clean up idle connections older than max_idle_time (thread-safe)

        This method removes connections that have been idle for too long
        to free up resources. Uses proper synchronization to prevent conflicts
        with pool's internal management.
        """
        cleaned_total = 0

        for database_name, pool in list(self._sync_pools.items()):
            try:
                cleaned_count = 0

                # Thread-safe access to pool internals using pool's lock
                with pool._lock:
                    # Build list of connections to remove first (avoid modifying during iteration)
                    connections_to_remove = []
                    available_conns = getattr(pool, "_available_connections", [])

                    for conn in available_conns:
                        if hasattr(conn, "_last_use"):
                            idle_time = (
                                datetime.now() - conn._last_use
                            ).total_seconds()
                            if idle_time > self._max_idle_time_seconds:
                                connections_to_remove.append(conn)

                    # Now remove connections after identifying them
                    for conn in connections_to_remove:
                        try:
                            pool._available_connections.remove(conn)
                            conn.disconnect()
                            cleaned_count += 1
                        except ValueError:
                            # Connection already removed (race condition - safe to ignore)
                            pass
                        except Exception as e:
                            logger.debug(f"Could not remove idle connection: {e}")

                if cleaned_count > 0:
                    logger.info(
                        f"Cleaned up {cleaned_count} idle connections for '{database_name}'"
                    )
                    cleaned_total += cleaned_count

            except Exception as e:
                logger.error(
                    f"Error cleaning idle connections for '{database_name}': {e}"
                )

        if cleaned_total > 0:
            logger.info(f"Total idle connections cleaned: {cleaned_total}")

    async def _cleanup_idle_connections_task(self):
        """
        Background task to clean up idle connections periodically

        Runs every _cleanup_interval_seconds to remove idle connections
        """
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval_seconds)
                await self.cleanup_idle_connections()
            except asyncio.CancelledError:
                logger.info("Idle connection cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in idle connection cleanup task: {e}")

    def get_statistics(self) -> ManagerStats:
        """
        Get comprehensive manager statistics

        Returns:
            ManagerStats with detailed statistics for all databases
        """
        # Update counts
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

        # Update uptime
        self._manager_stats.uptime_seconds = (
            datetime.now() - self._start_time
        ).total_seconds()

        # Copy database stats
        self._manager_stats.database_stats = self._database_stats.copy()

        return self._manager_stats

    async def close_all(self):
        """Close all connections and cleanup background tasks"""
        # Cancel cleanup task if running
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                logger.debug("Redis cleanup task cancelled during shutdown")

        # Close async pools
        for pool in self._async_pools.values():
            try:
                await pool.aclose()
            except Exception as e:
                logger.warning(f"Error closing async pool: {e}")

        # Close sync pools
        for pool in self._sync_pools.values():
            try:
                pool.disconnect()
            except Exception as e:
                logger.warning(f"Error closing sync pool: {e}")

        self._sync_pools.clear()
        self._async_pools.clear()
        self._clients.clear()

        logger.info("All Redis connections closed")


# Global connection manager instance
_connection_manager = RedisConnectionManager()


# Main interface functions
def get_redis_client(
    async_client: bool = False, database: str = "main"
) -> Union[redis.Redis, async_redis.Redis, None]:
    """
    Get a Redis client instance with circuit breaker and health monitoring.

    This is the CANONICAL method for Redis access in AutoBot. Direct redis.Redis()
    instantiation is FORBIDDEN per CLAUDE.md policy.

    CONSOLIDATED FEATURES (from 6 implementations):
    ===============================================
    ✅ Circuit breaker protection (prevents cascading failures)
    ✅ Health monitoring (tracks connection states)
    ✅ Connection pooling with TCP keepalive tuning (prevents connection drops)
    ✅ "Loading dataset" state handling (waits for Redis startup)
    ✅ Tenacity retry logic (exponential backoff, up to 5 attempts)
    ✅ WeakSet connection tracking (no GC interference)
    ✅ Comprehensive statistics collection (RedisStats/ManagerStats)
    ✅ YAML configuration support (redis-databases.yaml)
    ✅ Service registry integration
    ✅ Centralized timeout configuration
    ✅ Parameter filtering (removes None values)

    Args:
        async_client (bool): If True, returns async Redis client (for async functions).
                             If False, returns synchronous client (for regular functions).
                             Default: False
        database (str): Named database for logical separation. Use self-documenting
                        names instead of DB numbers. Default: "main"

    Returns:
        Union[redis.Redis, async_redis.Redis, None]:
            - redis.Redis: Synchronous client (if async_client=False)
            - async_redis.Redis: Async client coroutine (if async_client=True)
            - None: If Redis is disabled or connection fails

    Examples:
        Basic usage (backward compatible - existing code works unchanged):
            >>> redis = get_redis_client(database="main")
            >>> redis.set("key", "value")

        Async usage:
            >>> async def store_data():
            ...     redis = await get_redis_client(async_client=True, database="main")
            ...     await redis.set("key", "value")

        Advanced usage with new features:
            >>> # Named database methods
            >>> manager = RedisConnectionManager()
            >>> main_client = await manager.main()
            >>> knowledge_client = await manager.knowledge()
            >>>
            >>> # Pipeline context manager
            >>> async with manager.pipeline("main") as pipe:
            ...     pipe.set("key1", "value1")
            ...     pipe.set("key2", "value2")
            ...     # Auto-executes on context exit
            >>>
            >>> # Get statistics
            >>> stats = manager.get_statistics()
            >>> print(f"Success rate: {stats.overall_success_rate}%")
            >>>
            >>> # Pool statistics
            >>> pool_stats = manager.get_pool_statistics("main")
            >>> print(f"Active connections: {pool_stats.in_use_connections}")
    """
    if async_client:
        # Return coroutine for async client
        return _connection_manager.get_async_client(database)
    else:
        # Return sync client directly
        return _connection_manager.get_sync_client(database)


# Convenience functions for specific database access
def get_knowledge_base_redis(**kwargs) -> Optional[redis.Redis]:
    """Get Redis client for knowledge base data"""
    return get_redis_client(database="knowledge", **kwargs)


def get_prompts_redis(**kwargs) -> Optional[redis.Redis]:
    """Get Redis client for prompt templates"""
    return get_redis_client(database="prompts", **kwargs)


def get_agents_redis(**kwargs) -> Optional[redis.Redis]:
    """Get Redis client for agent communication"""
    return get_redis_client(database="agents", **kwargs)


def get_metrics_redis(**kwargs) -> Optional[redis.Redis]:
    """Get Redis client for performance metrics"""
    return get_redis_client(database="metrics", **kwargs)


def get_main_redis(**kwargs) -> Optional[redis.Redis]:
    """Get Redis client for main application data"""
    return get_redis_client(database="main", **kwargs)


# Health and metrics functions
def get_redis_health() -> Dict[str, Any]:
    """Get Redis health status"""
    return _connection_manager.get_health_status()


def get_redis_metrics(database: Optional[str] = None) -> Dict[str, Any]:
    """Get Redis connection metrics"""
    return _connection_manager.get_metrics(database)


# Cleanup function
async def close_all_redis_connections():
    """Close all Redis connections"""
    await _connection_manager.close_all()


# Context manager for Redis operations
@asynccontextmanager
async def redis_context(
    database: str = "main",
) -> AsyncGenerator[async_redis.Redis, None]:
    """
    Async context manager for Redis operations

    Usage:
        async with redis_context("main") as redis:
            await redis.set("key", "value")
    """
    client = await get_redis_client(async_client=True, database=database)
    try:
        yield client
    finally:
        # Connection returned to pool automatically
        pass


# ============================================================================
# BACKWARD COMPATIBILITY LAYER
# ============================================================================
# Support for old redis_database_manager imports (archived in P1)


class RedisDatabaseManager:
    """
    DEPRECATED: Backward compatibility wrapper for archived redis_database_manager

    This class provides compatibility for code still using the old
    RedisDatabaseManager interface. All new code should use get_redis_client() directly.

    Migration:
        OLD: manager = RedisDatabaseManager()
             client = await manager.get_async_connection(RedisDatabase.MAIN)

        NEW: client = await get_redis_client(async_client=True, database="main")
    """

    def __init__(self):
        logger.warning(
            "DEPRECATED: RedisDatabaseManager is deprecated. "
            "Use get_redis_client() from src.utils.redis_client instead."
        )

    def get_connection(
        self, database: Union[RedisDatabase, str]
    ) -> Optional[redis.Redis]:
        """Get synchronous Redis connection (DEPRECATED)"""
        db_name = (
            database.name.lower() if isinstance(database, RedisDatabase) else database
        )
        return get_redis_client(async_client=False, database=db_name)

    async def get_async_connection(
        self, database: Union[RedisDatabase, str]
    ) -> Optional[async_redis.Redis]:
        """Get asynchronous Redis connection (DEPRECATED)"""
        db_name = (
            database.name.lower() if isinstance(database, RedisDatabase) else database
        )
        return await get_redis_client(async_client=True, database=db_name)


# Global instance for backward compatibility
redis_db_manager = RedisDatabaseManager()
