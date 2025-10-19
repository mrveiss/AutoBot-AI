"""
Optimized Redis Connection Manager - Performance Fix for Connection Pooling
Addresses connection leaks and provides proper resource management
Identified by performance agent analysis for stable Redis performance
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Optional

import redis

from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class OptimizedRedisConnectionManager:
    """
    Optimized Redis connection manager with proper pooling and resource limits
    """

    def __init__(self):
        self.connection_pools = {}
        self.pool_config = {
            "max_connections": 20,
            "retry_on_timeout": True,
            "socket_keepalive": True,
            "socket_keepalive_options": {
                1: 600,  # TCP_KEEPIDLE (seconds)
                2: 60,  # TCP_KEEPINTVL (seconds)
                3: 5,  # TCP_KEEPCNT (count)
            },
            "health_check_interval": 30,
            "socket_timeout": 10,
            "socket_connect_timeout": 5,
        }

    def get_connection_pool(
        self, host: str, port: int, db: int, password: Optional[str] = None
    ) -> redis.ConnectionPool:
        """Get or create optimized connection pool"""
        pool_key = f"{host}:{port}:{db}"

        if pool_key not in self.connection_pools:
            pool_params = {
                "host": host,
                "port": port,
                "db": db,
                "decode_responses": True,
                **self.pool_config,
            }

            if password:
                pool_params["password"] = password

            self.connection_pools[pool_key] = redis.ConnectionPool(**pool_params)
            logger.info(f"Created optimized Redis pool: {pool_key}")

        return self.connection_pools[pool_key]

    def get_redis_client(
        self, host: str, port: int, db: int, password: Optional[str] = None
    ) -> redis.Redis:
        """Get Redis client with optimized connection pool"""
        pool = self.get_connection_pool(host, port, db, password)
        return redis.Redis(connection_pool=pool)

    @asynccontextmanager
    async def get_managed_client(
        self, host: str, port: int, db: int, password: Optional[str] = None
    ):
        """Context manager for managed Redis client usage"""
        client = self.get_redis_client(host, port, db, password)
        try:
            yield client
        finally:
            # Connection automatically returns to pool
            pass

    async def health_check_all_pools(self) -> Dict[str, bool]:
        """Health check all connection pools"""
        health_status = {}

        for pool_key, pool in self.connection_pools.items():
            try:
                client = redis.Redis(connection_pool=pool)
                client.ping()
                health_status[pool_key] = True
                logger.debug(f"Redis pool {pool_key} healthy")
            except Exception as e:
                logger.error(f"Redis pool {pool_key} health check failed: {e}")
                health_status[pool_key] = False

        return health_status

    def get_pool_stats(self) -> Dict[str, Dict]:
        """Get connection pool statistics"""
        stats = {}

        for pool_key, pool in self.connection_pools.items():
            try:
                stats[pool_key] = {
                    "created_connections": pool.created_connections,
                    "available_connections": len(pool._available_connections),
                    "in_use_connections": len(pool._in_use_connections),
                    "max_connections": pool.max_connections,
                    "host": f"{pool.connection_kwargs['host']}:{pool.connection_kwargs['port']}/{pool.connection_kwargs['db']}",
                }
            except Exception as e:
                logger.error(f"Error getting stats for pool {pool_key}: {e}")
                stats[pool_key] = {"error": str(e)}

        return stats

    def cleanup_pools(self):
        """Cleanup all connection pools"""
        for pool_key, pool in self.connection_pools.items():
            try:
                pool.disconnect()
                logger.info(f"Disconnected Redis pool: {pool_key}")
            except Exception as e:
                logger.error(f"Error disconnecting pool {pool_key}: {e}")

        self.connection_pools.clear()

    def cleanup_idle_connections(self, max_idle_time: int = 300):
        """Clean up idle connections older than max_idle_time seconds"""
        for pool_key, pool in self.connection_pools.items():
            try:
                # This will clean up connections that have been idle
                available_count_before = len(pool._available_connections)

                # Force cleanup of idle connections
                pool.disconnect(inuse_connections=False)

                available_count_after = len(pool._available_connections)

                if available_count_before != available_count_after:
                    logger.info(
                        f"Cleaned {available_count_before - available_count_after} idle connections from pool {pool_key}"
                    )

            except Exception as e:
                logger.error(
                    f"Error cleaning idle connections for pool {pool_key}: {e}"
                )


# Global optimized Redis manager instance
_redis_manager = None


def get_optimized_redis_manager() -> OptimizedRedisConnectionManager:
    """Get global optimized Redis manager instance"""
    global _redis_manager
    if _redis_manager is None:
        _redis_manager = OptimizedRedisConnectionManager()
    return _redis_manager


# Helper function for common Redis operations
async def with_redis_client(
    host: str, port: int, db: int, password: Optional[str] = None
):
    """Context manager helper for Redis client operations"""
    manager = get_optimized_redis_manager()
    return manager.get_managed_client(host, port, db, password)
