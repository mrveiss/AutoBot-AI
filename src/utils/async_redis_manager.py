#!/usr/bin/env python3
"""
Async Redis Manager using aioredis
Replaces the blocking redis_database_manager.py with proper async operations
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Optional, Any, AsyncGenerator
from dataclasses import dataclass

import aioredis
from aioredis import Redis
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


@dataclass
class RedisConfig:
    """Redis connection configuration"""

    host: str = "localhost"
    port: int = NetworkConstants.REDIS_PORT
    db: int = 0
    password: Optional[str] = None
    socket_timeout: float = 2.0
    socket_connect_timeout: float = 2.0
    retry_on_timeout: bool = True
    health_check_interval: int = 30


class AsyncRedisManager:
    """
    Async Redis connection manager using aioredis
    Provides connection pooling, health checks, and automatic reconnection
    """

    def __init__(self):
        self._pools: Dict[str, aioredis.ConnectionPool] = {}
        self._clients: Dict[str, Redis] = {}
        self._config: Dict[str, RedisConfig] = {}
        self._health_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def add_database(self, name: str, config: RedisConfig) -> None:
        """Add a Redis database configuration"""
        async with self._lock:
            self._config[name] = config
            await self._create_connection(name, config)

    async def _wait_for_redis_ready(
        self, client: Redis, name: str, max_wait: int = 60
    ) -> bool:
        """Wait for Redis to finish loading dataset and be ready"""
        logger.info(f"⏳ Waiting for Redis '{name}' to finish loading dataset...")

        for attempt in range(max_wait):
            try:
                # Try to ping - this will raise exception if still loading
                await asyncio.wait_for(client.ping(), timeout=2.0)
                logger.info(f"✅ Redis '{name}' is ready after {attempt} seconds")
                return True
            except Exception as e:
                error_msg = str(e).lower()

                # Check if Redis is still loading
                if "loading" in error_msg or "busy" in error_msg:
                    if attempt % 10 == 0:  # Log every 10 seconds
                        logger.info(
                            f"⏳ Redis '{name}' still loading dataset, waiting... ({attempt}s/{max_wait}s)"
                        )
                    await asyncio.sleep(1)
                    continue
                else:
                    # Different error, re-raise
                    logger.error(f"❌ Redis connection error for '{name}': {e}")
                    raise

        logger.error(
            f"❌ Redis '{name}' did not become ready within {max_wait} seconds"
        )
        return False

    @retry(
        stop=stop_after_attempt(5),  # Increased attempts for loading scenarios
        wait=wait_exponential(multiplier=2, min=2, max=30),  # Longer waits
        retry=retry_if_exception_type((aioredis.ConnectionError, asyncio.TimeoutError)),
    )
    async def _create_connection(self, name: str, config: RedisConfig) -> None:
        """Create async Redis connection with retry logic and loading state handling"""
        try:
            # Create connection pool
            pool = aioredis.ConnectionPool.from_url(
                f"redis://{':' + config.password + '@' if config.password else ''}"
                f"{config.host}:{config.port}/{config.db}",
                socket_timeout=config.socket_timeout,
                socket_connect_timeout=config.socket_connect_timeout,
                retry_on_timeout=config.retry_on_timeout,
                max_connections=20,  # Connection pooling
                health_check_interval=config.health_check_interval,
            )

            # Create Redis client
            client = Redis(connection_pool=pool)

            # Wait for Redis to be ready (handles loading state)
            if not await self._wait_for_redis_ready(client, name):
                raise aioredis.ConnectionError(
                    f"Redis '{name}' did not become ready in time"
                )

            # Store connections
            self._pools[name] = pool
            self._clients[name] = client

            # Start health check task
            self._health_tasks[name] = asyncio.create_task(
                self._health_check_task(name, client, config)
            )

            logger.info(f"✅ Async Redis connection established: {name}")

        except Exception as e:
            logger.error(f"❌ Failed to create async Redis connection {name}: {e}")
            raise

    async def _health_check_task(
        self, name: str, client: Redis, config: RedisConfig
    ) -> None:
        """Background health check task"""
        while True:
            try:
                await asyncio.sleep(config.health_check_interval)
                await asyncio.wait_for(client.ping(), timeout=1.0)
                logger.debug(f"Redis health check passed: {name}")

            except Exception as e:
                logger.warning(f"Redis health check failed for {name}: {e}")
                # Attempt reconnection
                try:
                    await self._create_connection(name, config)
                except Exception as reconnect_error:
                    logger.error(
                        f"Redis reconnection failed for {name}: {reconnect_error}"
                    )

    @asynccontextmanager
    async def get_client(
        self, database_name: str = "default"
    ) -> AsyncGenerator[Redis, None]:
        """Get Redis client with context manager for proper cleanup"""
        if database_name not in self._clients:
            raise ValueError(f"Redis database '{database_name}' not configured")

        client = self._clients[database_name]
        try:
            # Test connection before yielding
            await asyncio.wait_for(client.ping(), timeout=1.0)
            yield client
        except Exception as e:
            logger.error(f"Redis client error for {database_name}: {e}")
            raise

    async def execute(self, database_name: str, command: str, *args, **kwargs) -> Any:
        """Execute Redis command with automatic retry"""
        async with self.get_client(database_name) as client:
            command_method = getattr(client, command.lower())
            return await command_method(*args, **kwargs)

    async def get(self, database_name: str, key: str) -> Optional[bytes]:
        """Get value by key"""
        return await self.execute(database_name, "get", key)

    async def set(
        self,
        database_name: str,
        key: str,
        value: Any,
        ex: Optional[int] = None,
        px: Optional[int] = None,
    ) -> bool:
        """Set key-value pair with optional expiration"""
        return await self.execute(database_name, "set", key, value, ex=ex, px=px)

    async def delete(self, database_name: str, *keys: str) -> int:
        """Delete keys"""
        return await self.execute(database_name, "delete", *keys)

    async def exists(self, database_name: str, *keys: str) -> int:
        """Check if keys exist"""
        return await self.execute(database_name, "exists", *keys)

    async def hget(self, database_name: str, name: str, key: str) -> Optional[bytes]:
        """Get hash field value"""
        return await self.execute(database_name, "hget", name, key)

    async def hset(
        self,
        database_name: str,
        name: str,
        mapping: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> int:
        """Set hash fields"""
        if mapping:
            return await self.execute(database_name, "hset", name, mapping=mapping)
        return await self.execute(database_name, "hset", name, **kwargs)

    async def hgetall(self, database_name: str, name: str) -> Dict[bytes, bytes]:
        """Get all hash fields"""
        return await self.execute(database_name, "hgetall", name)

    async def close(self) -> None:
        """Close all Redis connections and cleanup"""
        # Cancel health check tasks
        for task in self._health_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Close clients and pools
        for client in self._clients.values():
            await client.close()

        for pool in self._pools.values():
            await pool.disconnect()

        self._clients.clear()
        self._pools.clear()
        self._health_tasks.clear()

        logger.info("All Redis connections closed")

    async def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        stats = {}
        for name, client in self._clients.items():
            try:
                info = await client.info()
                stats[name] = {
                    "connected": True,
                    "used_memory": info.get("used_memory_human", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                }
            except Exception as e:
                stats[name] = {"connected": False, "error": str(e)}

        return stats


# Global async Redis manager instance
async_redis_manager = AsyncRedisManager()


async def initialize_default_redis() -> None:
    """Initialize default Redis connection"""
    try:
        # Check if Redis is in Docker - use localhost since backend runs on host
        import os

        redis_host = os.getenv("REDIS_HOST", "172.16.168.23")  # Remote Redis host

        config = RedisConfig(
            host=redis_host,
            port=NetworkConstants.REDIS_PORT,
            db=0,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )

        await async_redis_manager.add_database("default", config)
        logger.info("Default async Redis initialized")

    except Exception as e:
        logger.warning(f"Failed to initialize default Redis: {e}")
        logger.info("Continuing without Redis - some features may be limited")
        # Don't raise - allow app to continue without Redis


# Convenience functions
async def get_redis() -> AsyncRedisManager:
    """Get the global Redis manager"""
    return async_redis_manager


async def redis_get(key: str, database: str = "default") -> Optional[bytes]:
    """Convenience function for Redis GET"""
    return await async_redis_manager.get(database, key)


async def redis_set(
    key: str, value: Any, database: str = "default", ex: Optional[int] = None
) -> bool:
    """Convenience function for Redis SET"""
    return await async_redis_manager.set(database, key, value, ex=ex)


async def redis_delete(key: str, database: str = "default") -> int:
    """Convenience function for Redis DELETE"""
    return await async_redis_manager.delete(database, key)
