"""
Redis Connection Helper with Standardized Timeouts
=================================================

Helper module for creating Redis connections with standardized timeout
configurations across AutoBot.

Usage:
    from src.utils.redis_helper import get_redis_connection, get_async_redis_connection

    # Synchronous Redis connection
    redis_client = get_redis_connection(db=0)

    # Asynchronous Redis connection
    async_client = await get_async_redis_connection(db=0)
"""

from typing import Optional

import redis
import redis.asyncio as aioredis

from src.constants.network_constants import NetworkConstants

try:
    from src.config.timeout_config import get_redis_timeout_config

    TIMEOUT_CONFIG = get_redis_timeout_config()
except ImportError:
    # Fallback configuration
    TIMEOUT_CONFIG = {
        "socket_timeout": 5.0,
        "socket_connect_timeout": 5.0,
        "retry_on_timeout": True,
        "max_retries": 3,
    }


def get_redis_connection(
    host: str = NetworkConstants.REDIS_VM_IP,
    port: int = NetworkConstants.REDIS_PORT,
    db: int = 0,
    password: Optional[str] = None,
    **kwargs
) -> redis.Redis:
    """
    Get a standardized synchronous Redis connection

    Args:
        host: Redis host (default: Redis VM IP)
        port: Redis port (default: Redis port)
        db: Database number (default: 0)
        password: Redis password if required
        **kwargs: Additional Redis connection parameters

    Returns:
        Configured Redis client
    """
    connection_params = {
        "host": host,
        "port": port,
        "db": db,
        "password": password,
        "socket_timeout": TIMEOUT_CONFIG["socket_timeout"],
        "socket_connect_timeout": TIMEOUT_CONFIG["socket_connect_timeout"],
        "retry_on_timeout": TIMEOUT_CONFIG["retry_on_timeout"],
        "decode_responses": True,
        **kwargs,
    }

    # Remove None values
    connection_params = {k: v for k, v in connection_params.items() if v is not None}

    return redis.Redis(**connection_params)


async def get_async_redis_connection(
    host: str = NetworkConstants.REDIS_VM_IP,
    port: int = NetworkConstants.REDIS_PORT,
    db: int = 0,
    password: Optional[str] = None,
    **kwargs
) -> aioredis.Redis:
    """
    Get a standardized asynchronous Redis connection

    Args:
        host: Redis host (default: Redis VM IP)
        port: Redis port (default: Redis port)
        db: Database number (default: 0)
        password: Redis password if required
        **kwargs: Additional Redis connection parameters

    Returns:
        Configured async Redis client
    """
    connection_params = {
        "host": host,
        "port": port,
        "db": db,
        "password": password,
        "socket_timeout": TIMEOUT_CONFIG["socket_timeout"],
        "socket_connect_timeout": TIMEOUT_CONFIG["socket_connect_timeout"],
        "retry_on_timeout": TIMEOUT_CONFIG["retry_on_timeout"],
        "decode_responses": True,
        **kwargs,
    }

    # Remove None values
    connection_params = {k: v for k, v in connection_params.items() if v is not None}

    return aioredis.Redis(**connection_params)


def get_redis_pool(
    host: str = NetworkConstants.REDIS_VM_IP,
    port: int = NetworkConstants.REDIS_PORT,
    db: int = 0,
    password: Optional[str] = None,
    max_connections: int = 20,
    **kwargs
) -> redis.ConnectionPool:
    """
    Get a standardized Redis connection pool

    Args:
        host: Redis host (default: Redis VM IP)
        port: Redis port (default: Redis port)
        db: Database number (default: 0)
        password: Redis password if required
        max_connections: Maximum connections in pool (default: 20)
        **kwargs: Additional pool parameters

    Returns:
        Configured Redis connection pool
    """
    pool_params = {
        "host": host,
        "port": port,
        "db": db,
        "password": password,
        "max_connections": max_connections,
        "socket_timeout": TIMEOUT_CONFIG["socket_timeout"],
        "socket_connect_timeout": TIMEOUT_CONFIG["socket_connect_timeout"],
        "retry_on_timeout": TIMEOUT_CONFIG["retry_on_timeout"],
        **kwargs,
    }

    # Remove None values
    pool_params = {k: v for k, v in pool_params.items() if v is not None}

    return redis.ConnectionPool(**pool_params)


class RedisConnectionManager:
    """Managed Redis connections with automatic cleanup"""

    def __init__(self):
        self._connections = {}
        self._pools = {}

    def get_connection(self, db: int = 0, **kwargs) -> redis.Redis:
        """Get or create a Redis connection for the specified database"""
        if db not in self._connections:
            self._connections[db] = get_redis_connection(db=db, **kwargs)
        return self._connections[db]

    async def get_async_connection(self, db: int = 0, **kwargs) -> aioredis.Redis:
        """Get or create an async Redis connection for the specified database"""
        if db not in self._connections:
            self._connections[db] = await get_async_redis_connection(db=db, **kwargs)
        return self._connections[db]

    def close_all(self):
        """Close all managed connections"""
        for conn in self._connections.values():
            if hasattr(conn, "close"):
                conn.close()
        self._connections.clear()

        for pool in self._pools.values():
            if hasattr(pool, "disconnect"):
                pool.disconnect()
        self._pools.clear()


# Global connection manager instance
redis_manager = RedisConnectionManager()
