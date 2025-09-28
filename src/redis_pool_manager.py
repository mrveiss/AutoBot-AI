"""
Redis Connection Pool Manager - Standardized Redis Connections

This module provides a centralized, standardized way to manage Redis connections
across the entire AutoBot system. It eliminates connection pattern inconsistencies
and provides proper pooling, error handling, and monitoring.

Key Features:
- Centralized connection management
- Proper connection pooling with configurable limits
- Automatic retry logic with exponential backoff
- Health monitoring and automatic recovery
- Database-specific connection pools
- Async and sync client support
- Connection metrics and monitoring
- Graceful degradation on failures

Usage:
    from src.redis_pool_manager import get_redis_pool, get_async_redis_pool

    # Get connection for specific database
    redis_client = await get_redis_pool('sessions')
    async_client = await get_async_redis_pool('knowledge')

    # Use in context manager
    async with get_redis_context('main') as redis:
        await redis.set('key', 'value')
"""

import asyncio
import logging
import time
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, AsyncGenerator, Union
from threading import Lock

import redis
import aioredis
from redis.connection import ConnectionPool
from redis.retry import Retry
from redis.backoff import ExponentialBackoff

from src.unified_config import config

logger = logging.getLogger(__name__)


@dataclass
class ConnectionMetrics:
    """Connection pool metrics"""
    created_connections: int = 0
    active_connections: int = 0
    failed_connections: int = 0
    reconnections: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None


@dataclass
class PoolConfig:
    """Redis pool configuration"""
    max_connections: int = 20
    min_connections: int = 2
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    retry_on_timeout: bool = True
    max_retries: int = 3
    backoff_factor: float = 2.0
    health_check_interval: float = 30.0


class RedisPoolManager:
    """Centralized Redis connection pool manager"""

    def __init__(self):
        self._sync_pools: Dict[str, ConnectionPool] = {}
        self._async_pools: Dict[str, aioredis.ConnectionPool] = {}
        self._clients: Dict[str, Union[redis.Redis, aioredis.Redis]] = {}
        self._metrics: Dict[str, ConnectionMetrics] = {}
        self._lock = Lock()
        self._config = config.get_redis_config()
        self._pool_config = self._load_pool_config()
        self._health_check_task: Optional[asyncio.Task] = None

        logger.info("Redis Pool Manager initialized")

    def _load_pool_config(self) -> PoolConfig:
        """Load pool configuration from unified config"""
        redis_config = self._config.get('connection', {})

        return PoolConfig(
            max_connections=redis_config.get('max_connections', 20),
            min_connections=redis_config.get('min_connections', 2),
            socket_timeout=redis_config.get('socket_timeout', 5.0),
            socket_connect_timeout=redis_config.get('socket_connect_timeout', 5.0),
            retry_on_timeout=redis_config.get('retry_on_timeout', True),
            max_retries=config.get('retry.redis.attempts', 3),
            backoff_factor=config.get('retry.backoff_factor', 2.0),
            health_check_interval=config.get('health.interval', 30.0)
        )

    def _get_database_number(self, database_name: str) -> int:
        """Get database number for a given database name"""
        databases = config.get('redis.databases', {})
        return databases.get(database_name, 0)

    def _create_sync_pool(self, database_name: str) -> ConnectionPool:
        """Create synchronous Redis connection pool"""
        db_number = self._get_database_number(database_name)

        retry_policy = Retry(
            backoff=ExponentialBackoff(
                base=0.008,  # Base backoff time in seconds
                cap=10.0     # Maximum backoff time in seconds
            ),
            retries=self._pool_config.max_retries
        )

        pool = ConnectionPool(
            host=self._config['host'],
            port=self._config['port'],
            db=db_number,
            password=self._config.get('password'),
            max_connections=self._pool_config.max_connections,
            socket_timeout=self._pool_config.socket_timeout,
            socket_connect_timeout=self._pool_config.socket_connect_timeout,
            retry_on_timeout=self._pool_config.retry_on_timeout,
            retry=retry_policy,
            decode_responses=True
        )

        logger.info(
            f"Created sync Redis pool for '{database_name}' (DB {db_number}) "
            f"with {self._pool_config.max_connections} max connections"
        )

        return pool

    async def _create_async_pool(self, database_name: str) -> aioredis.ConnectionPool:
        """Create asynchronous Redis connection pool"""
        db_number = self._get_database_number(database_name)

        pool = aioredis.ConnectionPool(
            host=self._config['host'],
            port=self._config['port'],
            db=db_number,
            password=self._config.get('password'),
            max_connections=self._pool_config.max_connections,
            socket_timeout=self._pool_config.socket_timeout,
            socket_connect_timeout=self._pool_config.socket_connect_timeout,
            retry_on_timeout=self._pool_config.retry_on_timeout,
            decode_responses=True
        )

        logger.info(
            f"Created async Redis pool for '{database_name}' (DB {db_number}) "
            f"with {self._pool_config.max_connections} max connections"
        )

        return pool

    def get_sync_client(self, database_name: str = 'main') -> redis.Redis:
        """Get synchronous Redis client for specified database"""
        with self._lock:
            client_key = f"sync_{database_name}"

            if client_key not in self._clients:
                # Create pool if it doesn't exist
                if database_name not in self._sync_pools:
                    self._sync_pools[database_name] = self._create_sync_pool(database_name)
                    self._metrics[database_name] = ConnectionMetrics()

                # Create client with pool
                pool = self._sync_pools[database_name]
                client = redis.Redis(connection_pool=pool)

                # Test connection
                try:
                    client.ping()
                    self._clients[client_key] = client
                    self._metrics[database_name].created_connections += 1
                    logger.debug(f"✅ Sync Redis client ready for '{database_name}'")
                except Exception as e:
                    self._metrics[database_name].failed_connections += 1
                    self._metrics[database_name].last_error = str(e)
                    self._metrics[database_name].last_error_time = time.time()
                    logger.error(f"❌ Failed to connect sync Redis client for '{database_name}': {e}")
                    raise

            return self._clients[client_key]

    async def get_async_client(self, database_name: str = 'main') -> aioredis.Redis:
        """Get asynchronous Redis client for specified database"""
        client_key = f"async_{database_name}"

        if client_key not in self._clients:
            # Create pool if it doesn't exist
            if database_name not in self._async_pools:
                self._async_pools[database_name] = await self._create_async_pool(database_name)
                if database_name not in self._metrics:
                    self._metrics[database_name] = ConnectionMetrics()

            # Create client with pool
            pool = self._async_pools[database_name]
            client = aioredis.Redis(connection_pool=pool)

            # Test connection
            try:
                await client.ping()
                self._clients[client_key] = client
                self._metrics[database_name].created_connections += 1
                logger.debug(f"✅ Async Redis client ready for '{database_name}'")
            except Exception as e:
                self._metrics[database_name].failed_connections += 1
                self._metrics[database_name].last_error = str(e)
                self._metrics[database_name].last_error_time = time.time()
                logger.error(f"❌ Failed to connect async Redis client for '{database_name}': {e}")
                raise

        return self._clients[client_key]

    @asynccontextmanager
    async def get_connection_context(self, database_name: str = 'main') -> AsyncGenerator[aioredis.Redis, None]:
        """Async context manager for Redis connections"""
        client = None
        try:
            client = await self.get_async_client(database_name)
            self._metrics[database_name].active_connections += 1
            yield client
        except Exception as e:
            logger.error(f"Redis connection context error for '{database_name}': {e}")
            raise
        finally:
            if client and database_name in self._metrics:
                self._metrics[database_name].active_connections -= 1

    async def health_check_all_pools(self) -> Dict[str, bool]:
        """Health check all active pools"""
        results = {}

        # Check async pools
        for db_name, pool in self._async_pools.items():
            try:
                client = aioredis.Redis(connection_pool=pool)
                await client.ping()
                await client.close()
                results[f"async_{db_name}"] = True
            except Exception as e:
                results[f"async_{db_name}"] = False
                self._metrics[db_name].failed_connections += 1
                self._metrics[db_name].last_error = str(e)
                self._metrics[db_name].last_error_time = time.time()
                logger.warning(f"Health check failed for async '{db_name}': {e}")

        # Check sync pools
        for db_name, pool in self._sync_pools.items():
            try:
                client = redis.Redis(connection_pool=pool)
                client.ping()
                client.close()
                results[f"sync_{db_name}"] = True
            except Exception as e:
                results[f"sync_{db_name}"] = False
                if db_name not in self._metrics:
                    self._metrics[db_name] = ConnectionMetrics()
                self._metrics[db_name].failed_connections += 1
                self._metrics[db_name].last_error = str(e)
                self._metrics[db_name].last_error_time = time.time()
                logger.warning(f"Health check failed for sync '{db_name}': {e}")

        return results

    def get_pool_metrics(self) -> Dict[str, Any]:
        """Get connection pool metrics"""
        metrics = {
            'pools': {
                'sync': list(self._sync_pools.keys()),
                'async': list(self._async_pools.keys())
            },
            'clients': list(self._clients.keys()),
            'database_metrics': {}
        }

        for db_name, db_metrics in self._metrics.items():
            metrics['database_metrics'][db_name] = {
                'created_connections': db_metrics.created_connections,
                'active_connections': db_metrics.active_connections,
                'failed_connections': db_metrics.failed_connections,
                'reconnections': db_metrics.reconnections,
                'last_error': db_metrics.last_error,
                'last_error_time': db_metrics.last_error_time,
                'error_age_seconds': time.time() - db_metrics.last_error_time if db_metrics.last_error_time else None
            }

        return metrics

    async def close_all_pools(self):
        """Close all connection pools gracefully"""
        logger.info("Closing all Redis connection pools...")

        # Close async pools
        for db_name, pool in self._async_pools.items():
            try:
                await pool.disconnect()
                logger.debug(f"Closed async pool for '{db_name}'")
            except Exception as e:
                logger.warning(f"Error closing async pool for '{db_name}': {e}")

        # Close sync pools (they handle cleanup automatically)
        for db_name, pool in self._sync_pools.items():
            try:
                pool.disconnect()
                logger.debug(f"Closed sync pool for '{db_name}'")
            except Exception as e:
                logger.warning(f"Error closing sync pool for '{db_name}': {e}")

        # Stop health check task
        if self._health_check_task:
            self._health_check_task.cancel()

        # Clear caches
        self._sync_pools.clear()
        self._async_pools.clear()
        self._clients.clear()

        logger.info("All Redis pools closed")

    def __del__(self):
        """Cleanup on destruction"""
        if self._sync_pools or self._async_pools:
            logger.warning("RedisPoolManager destroyed without proper cleanup")


# Global singleton instance
_pool_manager: Optional[RedisPoolManager] = None
_manager_lock = Lock()


def get_pool_manager() -> RedisPoolManager:
    """Get the global Redis pool manager instance"""
    global _pool_manager

    if _pool_manager is None:
        with _manager_lock:
            if _pool_manager is None:
                _pool_manager = RedisPoolManager()

    return _pool_manager


# Convenience functions for easy access
def get_redis_sync(database_name: str = 'main') -> redis.Redis:
    """Get synchronous Redis client"""
    return get_pool_manager().get_sync_client(database_name)


async def get_redis_async(database_name: str = 'main') -> aioredis.Redis:
    """Get asynchronous Redis client"""
    return await get_pool_manager().get_async_client(database_name)


@asynccontextmanager
async def redis_context(database_name: str = 'main') -> AsyncGenerator[aioredis.Redis, None]:
    """Async context manager for Redis connections"""
    async with get_pool_manager().get_connection_context(database_name) as redis_client:
        yield redis_client


async def health_check_redis() -> Dict[str, Any]:
    """Comprehensive Redis health check"""
    manager = get_pool_manager()
    pool_health = await manager.health_check_all_pools()
    metrics = manager.get_pool_metrics()

    return {
        'pool_health': pool_health,
        'all_healthy': all(pool_health.values()),
        'metrics': metrics,
        'redis_config': {
            'host': config.get_host('redis'),
            'port': config.get_port('redis'),
            'enabled': config.get('redis.enabled', True)
        }
    }


# Cleanup function for app shutdown
async def cleanup_redis_pools():
    """Cleanup function for application shutdown"""
    global _pool_manager
    if _pool_manager:
        await _pool_manager.close_all_pools()
        _pool_manager = None


# Export main functions
__all__ = [
    'RedisPoolManager',
    'get_pool_manager',
    'get_redis_sync',
    'get_redis_async',
    'redis_context',
    'health_check_redis',
    'cleanup_redis_pools'
]