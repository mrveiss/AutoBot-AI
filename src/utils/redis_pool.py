"""
Consolidated Redis Management System - UNIFIED VERSION

This module consolidates all Redis functionality from:
- redis_client.py: Centralized client factory with database separation
- async_redis_manager.py: Async operations with connection pooling
- redis_database_manager.py: Database enumeration and management

FEATURES CONSOLIDATED:
✅ Async and sync Redis operations
✅ Connection pooling and health monitoring
✅ Database separation with enum safety
✅ Automatic reconnection and retry logic
✅ Configuration integration
✅ Legacy backward compatibility
✅ Connection factory patterns
✅ Performance optimizations
✅ Error handling and logging

USAGE:
    from src.utils.redis_pool import get_redis_client, AsyncRedisManager

    # Sync usage (legacy compatible)
    client = get_redis_client(database="main")

    # Async usage (advanced features)
    async_manager = AsyncRedisManager()
    await async_manager.initialize()
    async with async_manager.get_connection("knowledge") as conn:
        await conn.set("key", "value")
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncGenerator, Dict, Optional, Union

import aioredis
import redis
import redis.asyncio as async_redis
from aioredis import Redis as AsyncRedis
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Configuration imports with fallbacks
try:
    from src.infrastructure_config import cfg, config
except ImportError:
    try:
        from src.config_helper import cfg

        config = None
    except ImportError:
        try:
            from src.config import config as global_config_manager

            config = global_config_manager
            cfg = None
        except ImportError:
            config = None
            cfg = None

logger = logging.getLogger(__name__)


# ==============================================
# DATABASE ENUMERATION (from redis_database_manager)
# ==============================================


class RedisDatabase(Enum):
    """
    Enumeration of Redis databases for type safety and organization
    Consolidates database definitions across all Redis managers
    """

    MAIN = 0  # Main application data
    KNOWLEDGE = 1  # Knowledge base and documents
    PROMPTS = 2  # Prompt templates and cache
    AGENTS = 3  # Agent states and communication
    METRICS = 4  # System metrics and monitoring
    LOGS = 5  # Application logs and events
    SESSIONS = 6  # User sessions and temporary data
    WORKFLOWS = 7  # Workflow states and history
    VECTORS = 8  # Vector embeddings and indexes
    MODELS = 9  # Model configurations and cache
    CACHE = 10  # General application cache
    FACTS = 11  # Knowledge facts and rules
    TESTING = 15  # Testing and development data


@dataclass
class RedisConfig:
    """
    Redis connection configuration with all options
    Consolidates config patterns from all Redis managers
    """

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    socket_timeout: float = 2.0
    socket_connect_timeout: float = 2.0
    retry_on_timeout: bool = True
    health_check_interval: int = 30
    max_connections: int = 10
    decode_responses: bool = True
    encoding: str = "utf-8"


# ==============================================
# ASYNC REDIS MANAGER (from async_redis_manager)
# ==============================================


class ConsolidatedAsyncRedisManager:
    """
    Async Redis connection manager with all advanced features:
    - Connection pooling and health monitoring
    - Automatic reconnection and retry logic
    - Database separation and enum safety
    - Configuration integration
    """

    def __init__(self):
        self._pools: Dict[str, aioredis.ConnectionPool] = {}
        self._clients: Dict[str, AsyncRedis] = {}
        self._config: Dict[str, RedisConfig] = {}
        self._health_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self, config_path: Optional[str] = None):
        """Initialize the Redis manager with configuration"""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            # Load configuration
            await self._load_configuration(config_path)

            # Create default database connections
            for db_enum in RedisDatabase:
                await self._add_database_connection(db_enum.name.lower(), db_enum.value)

            self._initialized = True
            logger.info("Consolidated async Redis manager initialized")

    async def _load_configuration(self, config_path: Optional[str] = None):
        """Load Redis configuration from various sources"""
        base_config = RedisConfig()

        # Try to get configuration from consolidated config system
        if config and hasattr(config, "get_host"):
            base_config.host = config.get_host("redis")
            base_config.port = config.get_port("redis")
        elif cfg and hasattr(cfg, "get"):
            base_config.host = cfg.get("infrastructure.hosts.redis", base_config.host)
            base_config.port = cfg.get("infrastructure.ports.redis", base_config.port)
        else:
            # Fallback to environment variables
            base_config.host = os.getenv("REDIS_HOST", base_config.host)
            base_config.port = int(os.getenv("REDIS_PORT", base_config.port))

        # Store base configuration
        self._base_config = base_config
        logger.info(
            f"Redis configuration loaded: {base_config.host}:{base_config.port}"
        )

    async def _add_database_connection(self, name: str, db_number: int):
        """Add a database connection with the specified database number"""
        config = RedisConfig(
            host=self._base_config.host,
            port=self._base_config.port,
            db=db_number,
            password=self._base_config.password,
            socket_timeout=self._base_config.socket_timeout,
            socket_connect_timeout=self._base_config.socket_connect_timeout,
        )

        self._config[name] = config

        # Create connection pool
        pool = aioredis.ConnectionPool(
            host=config.host,
            port=config.port,
            db=config.db,
            password=config.password,
            socket_timeout=config.socket_timeout,
            socket_connect_timeout=config.socket_connect_timeout,
            max_connections=config.max_connections,
            retry_on_timeout=config.retry_on_timeout,
            decode_responses=config.decode_responses,
            encoding=config.encoding,
        )

        self._pools[name] = pool
        self._clients[name] = AsyncRedis(connection_pool=pool)

        # Start health monitoring
        self._health_tasks[name] = asyncio.create_task(
            self._monitor_connection_health(name)
        )

        logger.debug(f"Added Redis database connection: {name} (DB {db_number})")

    @asynccontextmanager
    async def get_connection(
        self, database: Union[str, RedisDatabase] = "main"
    ) -> AsyncGenerator[AsyncRedis, None]:
        """
        Get Redis connection with context manager for proper cleanup
        """
        if not self._initialized:
            await self.initialize()

        # Handle enum input
        if isinstance(database, RedisDatabase):
            database = database.name.lower()

        if database not in self._clients:
            raise ValueError(f"Redis database '{database}' not configured")

        client = self._clients[database]
        try:
            yield client
        except Exception as e:
            logger.error(f"Redis connection error for database '{database}': {e}")
            raise

    async def get_client(
        self, database: Union[str, RedisDatabase] = "main"
    ) -> AsyncRedis:
        """Get Redis client directly (for legacy compatibility)"""
        if not self._initialized:
            await self.initialize()

        if isinstance(database, RedisDatabase):
            database = database.name.lower()

        if database not in self._clients:
            raise ValueError(f"Redis database '{database}' not configured")

        return self._clients[database]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(
            (aioredis.ConnectionError, aioredis.TimeoutError)
        ),
    )
    async def _monitor_connection_health(self, database: str):
        """Monitor connection health and reconnect if needed"""
        config = self._config[database]

        while True:
            try:
                await asyncio.sleep(config.health_check_interval)

                # Ping the database
                client = self._clients[database]
                await client.ping()

                logger.debug(f"Redis health check passed for database: {database}")

            except Exception as e:
                logger.warning(f"Redis health check failed for {database}: {e}")

                # Attempt to reconnect
                try:
                    await self._reconnect_database(database)
                    logger.info(
                        f"Redis reconnected successfully for database: {database}"
                    )
                except Exception as reconnect_error:
                    logger.error(
                        f"Redis reconnection failed for {database}: {reconnect_error}"
                    )
                    # Wait longer before next attempt
                    await asyncio.sleep(60)

    async def _reconnect_database(self, database: str):
        """Reconnect to a specific database"""
        config = self._config[database]

        # Close existing pool
        if database in self._pools:
            await self._pools[database].disconnect()

        # Create new pool and client
        await self._add_database_connection(database, config.db)

    async def close(self):
        """Close all connections and cleanup resources"""
        # Cancel health monitoring tasks
        for task in self._health_tasks.values():
            task.cancel()

        # Close all connection pools
        for pool in self._pools.values():
            await pool.disconnect()

        self._pools.clear()
        self._clients.clear()
        self._health_tasks.clear()
        self._initialized = False

        logger.info("Consolidated async Redis manager closed")


# ==============================================
# SYNC REDIS CLIENT FACTORY (from redis_client)
# ==============================================

# Global instances for backward compatibility
_redis_client: Optional[redis.Redis] = None
_async_redis_client: Optional[AsyncRedis] = None
_async_manager: Optional[ConsolidatedAsyncRedisManager] = None


def get_redis_client(
    async_client: bool = False,
    database: Union[str, RedisDatabase] = "main",
) -> Union[redis.Redis, AsyncRedis, None]:
    """
    Returns a Redis client instance with database separation support.
    Legacy compatible function that consolidates all Redis client patterns.

    Args:
        async_client (bool): If True, returns async Redis client
        database (Union[str, RedisDatabase]): Database name or enum

    Returns:
        Union[redis.Redis, AsyncRedis, None]: Redis client instance
    """
    try:
        # Handle enum input
        if isinstance(database, RedisDatabase):
            db_number = database.value
            database_name = database.name.lower()
        else:
            # Map string names to database numbers
            database_name = database.lower()
            db_mapping = {
                "main": RedisDatabase.MAIN.value,
                "knowledge": RedisDatabase.KNOWLEDGE.value,
                "prompts": RedisDatabase.PROMPTS.value,
                "agents": RedisDatabase.AGENTS.value,
                "metrics": RedisDatabase.METRICS.value,
                "logs": RedisDatabase.LOGS.value,
                "sessions": RedisDatabase.SESSIONS.value,
                "workflows": RedisDatabase.WORKFLOWS.value,
                "vectors": RedisDatabase.VECTORS.value,
                "models": RedisDatabase.MODELS.value,
                "cache": RedisDatabase.CACHE.value,
                "facts": RedisDatabase.FACTS.value,
                "testing": RedisDatabase.TESTING.value,
            }
            db_number = db_mapping.get(database_name, RedisDatabase.MAIN.value)

        # Get Redis connection parameters
        redis_host = "localhost"
        redis_port = 6379

        if config and hasattr(config, "get_host"):
            redis_host = config.get_host("redis")
            redis_port = config.get_port("redis")
        elif cfg and hasattr(cfg, "get"):
            redis_host = cfg.get("infrastructure.hosts.redis", redis_host)
            redis_port = cfg.get("infrastructure.ports.redis", redis_port)
        else:
            redis_host = os.getenv("REDIS_HOST", redis_host)
            redis_port = int(os.getenv("REDIS_PORT", redis_port))

        if async_client:
            # Return async client
            return async_redis.Redis(
                host=redis_host,
                port=redis_port,
                db=db_number,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
                retry_on_timeout=True,
            )
        else:
            # Return sync client
            return redis.Redis(
                host=redis_host,
                port=redis_port,
                db=db_number,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
                retry_on_timeout=True,
            )

    except Exception as e:
        logger.error(f"Failed to create Redis client for database '{database}': {e}")
        return None


# ==============================================
# ASYNC CONVENIENCE FUNCTIONS
# ==============================================


async def redis_get(
    key: str, database: Union[str, RedisDatabase] = "main"
) -> Optional[Any]:
    """Async Redis GET operation with consolidated backend"""
    global _async_manager

    if not _async_manager:
        _async_manager = ConsolidatedAsyncRedisManager()
        await _async_manager.initialize()

    async with _async_manager.get_connection(database) as conn:
        return await conn.get(key)


async def redis_set(
    key: str,
    value: Any,
    expire: Optional[int] = None,
    database: Union[str, RedisDatabase] = "main",
) -> bool:
    """Async Redis SET operation with consolidated backend"""
    global _async_manager

    if not _async_manager:
        _async_manager = ConsolidatedAsyncRedisManager()
        await _async_manager.initialize()

    try:
        async with _async_manager.get_connection(database) as conn:
            result = await conn.set(key, value)
            if expire:
                await conn.expire(key, expire)
            return result
    except Exception as e:
        logger.error(f"Redis SET failed for key '{key}': {e}")
        return False


async def redis_delete(key: str, database: Union[str, RedisDatabase] = "main") -> int:
    """Async Redis DELETE operation"""
    global _async_manager

    if not _async_manager:
        _async_manager = ConsolidatedAsyncRedisManager()
        await _async_manager.initialize()

    async with _async_manager.get_connection(database) as conn:
        return await conn.delete(key)


# ==============================================
# LEGACY COMPATIBILITY EXPORTS
# ==============================================

# Export the consolidated async manager as the main interface
AsyncRedisManager = ConsolidatedAsyncRedisManager

# Create global instance for legacy imports
redis_db_manager = None  # Will be initialized on first use


class LegacyRedisDatabaseManager:
    """Legacy compatibility class for redis_database_manager imports"""

    def __init__(self):
        self._async_manager = ConsolidatedAsyncRedisManager()
        self._initialized = False

    async def get_async_connection(self, database: str):
        """Legacy method for getting async connections"""
        if not self._initialized:
            await self._async_manager.initialize()
            self._initialized = True

        return await self._async_manager.get_client(database)

    def get_connection(self, database: str):
        """Legacy method for getting sync connections"""
        return get_redis_client(async_client=False, database=database)


# Create legacy instance
redis_db_manager = LegacyRedisDatabaseManager()

# Export database enum and config for compatibility
__all__ = [
    "RedisDatabase",
    "RedisConfig",
    "ConsolidatedAsyncRedisManager",
    "AsyncRedisManager",
    "get_redis_client",
    "redis_get",
    "redis_set",
    "redis_delete",
    "redis_db_manager",
]

logger.info("Consolidated Redis management system initialized with all features")
