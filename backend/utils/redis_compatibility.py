# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Compatibility Layer for AutoBot
Provides backward compatibility for existing code while transitioning to async Redis manager
"""

import asyncio
import threading
import warnings
from typing import Optional, Union

from src.utils.logging_manager import get_logger

from .async_redis_manager import get_redis_manager

logger = get_logger(__name__, "backend")


class RedisCompatibilityWrapper:
    """
    Wrapper that provides both sync and async Redis operations
    for backward compatibility while transitioning to async Redis manager
    """

    def __init__(self, database_name: str = "main"):
        self.database_name = database_name
        self._async_db = None
        self._sync_client = None
        self._deprecation_warnings_shown = set()

    def _show_deprecation_warning(self, method_name: str):
        """Show deprecation warning once per method"""
        if method_name not in self._deprecation_warnings_shown:
            warnings.warn(
                f"Synchronous Redis method '{method_name}' is deprecated. "
                f"Please use async Redis operations with AsyncRedisManager.",
                DeprecationWarning,
                stacklevel=3,
            )
            self._deprecation_warnings_shown.add(method_name)

    async def _get_async_db(self):
        """Get async database connection"""
        if self._async_db is None:
            manager = await get_redis_manager()
            self._async_db = await manager.get_or_create_database(self.database_name)
        return self._async_db

    def _get_sync_client(self):
        """Get sync Redis client (deprecated path)"""
        if self._sync_client is None:
            # Import the old database manager for fallback
            try:
                from src.utils.redis_client import redis_db_manager

                self._sync_client = redis_db_manager.get_connection(self.database_name)
                logger.warning(
                    f"Using deprecated sync Redis client for database '{self.database_name}'. "
                    "Consider migrating to async operations."
                )
            except Exception as e:
                logger.error(f"Failed to create sync Redis client: {e}")
                raise ConnectionError(
                    f"Unable to create Redis client for {self.database_name}"
                )

        return self._sync_client

    # Async methods (preferred)

    async def aget(self, key: str) -> Optional[str]:
        """Async get value by key"""
        db = await self._get_async_db()
        return await db.get(key)

    async def aset(
        self,
        key: str,
        value: Union[str, bytes, int, float],
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """Async set key-value pair"""
        db = await self._get_async_db()
        return await db.set(key, value, ex=ex, px=px, nx=nx, xx=xx)

    async def adelete(self, *keys: str) -> int:
        """Async delete keys"""
        db = await self._get_async_db()
        return await db.delete(*keys)

    async def aexists(self, *keys: str) -> int:
        """Async check if keys exist"""
        db = await self._get_async_db()
        return await db.exists(*keys)

    async def aexpire(self, key: str, seconds: int) -> bool:
        """Async set key expiration"""
        db = await self._get_async_db()
        return await db.expire(key, seconds)

    async def attl(self, key: str) -> int:
        """Async get key time to live"""
        db = await self._get_async_db()
        return await db.ttl(key)

    async def ahget(self, name: str, key: str) -> Optional[str]:
        """Async get hash field value"""
        db = await self._get_async_db()
        return await db.hget(name, key)

    async def ahset(
        self, name: str, key: str, value: Union[str, bytes, int, float]
    ) -> int:
        """Async set hash field value"""
        db = await self._get_async_db()
        return await db.hset(name, key, value)

    async def ahgetall(self, name: str) -> dict:
        """Async get all hash fields and values"""
        db = await self._get_async_db()
        return await db.hgetall(name)

    async def alrange(self, name: str, start: int, end: int) -> list:
        """Async get list range"""
        async_db = await self._get_async_db()
        # Use the underlying Redis client for operations not wrapped
        return await async_db._redis.lrange(name, start, end)

    async def aping(self) -> bool:
        """Async ping Redis server"""
        db = await self._get_async_db()
        return await db.ping()

    # Sync methods (deprecated but supported for compatibility)

    def get(self, key: str) -> Optional[str]:
        """Sync get value by key (DEPRECATED - use aget)"""
        self._show_deprecation_warning("get")
        client = self._get_sync_client()
        return client.get(key)

    def set(
        self,
        key: str,
        value: Union[str, bytes, int, float],
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """Sync set key-value pair (DEPRECATED - use aset)"""
        self._show_deprecation_warning("set")
        client = self._get_sync_client()
        return client.set(key, value, ex=ex, px=px, nx=nx, xx=xx)

    def delete(self, *keys: str) -> int:
        """Sync delete keys (DEPRECATED - use adelete)"""
        self._show_deprecation_warning("delete")
        client = self._get_sync_client()
        return client.delete(*keys)

    def exists(self, *keys: str) -> int:
        """Sync check if keys exist (DEPRECATED - use aexists)"""
        self._show_deprecation_warning("exists")
        client = self._get_sync_client()
        return client.exists(*keys)

    def expire(self, key: str, seconds: int) -> bool:
        """Sync set key expiration (DEPRECATED - use aexpire)"""
        self._show_deprecation_warning("expire")
        client = self._get_sync_client()
        return client.expire(key, seconds)

    def ttl(self, key: str) -> int:
        """Sync get key time to live (DEPRECATED - use attl)"""
        self._show_deprecation_warning("ttl")
        client = self._get_sync_client()
        return client.ttl(key)

    def hget(self, name: str, key: str) -> Optional[str]:
        """Sync get hash field value (DEPRECATED - use ahget)"""
        self._show_deprecation_warning("hget")
        client = self._get_sync_client()
        return client.hget(name, key)

    def hset(self, name: str, key: str, value: Union[str, bytes, int, float]) -> int:
        """Sync set hash field value (DEPRECATED - use ahset)"""
        self._show_deprecation_warning("hset")
        client = self._get_sync_client()
        return client.hset(name, key, value)

    def hgetall(self, name: str) -> dict:
        """Sync get all hash fields and values (DEPRECATED - use ahgetall)"""
        self._show_deprecation_warning("hgetall")
        client = self._get_sync_client()
        return client.hgetall(name)

    def ping(self) -> bool:
        """Sync ping Redis server (DEPRECATED - use aping)"""
        self._show_deprecation_warning("ping")
        client = self._get_sync_client()
        try:
            return client.ping()
        except Exception:
            return False

    # Async context manager support

    async def __aenter__(self):
        """Async context manager entry"""
        await self._get_async_db()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        # Connections are managed by the async Redis manager


# Global compatibility instances for each database
_compatibility_instances = {}

# Lock for thread-safe access to _compatibility_instances (synchronous function needs threading.Lock)
_instances_lock = threading.Lock()


def get_redis_client_compat(database: str = "main") -> RedisCompatibilityWrapper:
    """
    Get Redis compatibility wrapper for a specific database

    This provides both sync and async methods for backward compatibility
    while transitioning to the async Redis manager.

    Args:
        database: Database name (main, knowledge, prompts, etc.)

    Returns:
        RedisCompatibilityWrapper instance
    """
    with _instances_lock:
        if database not in _compatibility_instances:
            _compatibility_instances[database] = RedisCompatibilityWrapper(database)

        return _compatibility_instances[database]


# Convenience functions for specific databases
def get_main_redis_compat() -> RedisCompatibilityWrapper:
    """Get main database compatibility wrapper"""
    return get_redis_client_compat("main")


def get_knowledge_redis_compat() -> RedisCompatibilityWrapper:
    """Get knowledge database compatibility wrapper"""
    return get_redis_client_compat("knowledge")


def get_cache_redis_compat() -> RedisCompatibilityWrapper:
    """Get cache database compatibility wrapper"""
    return get_redis_client_compat("cache")


def get_sessions_redis_compat() -> RedisCompatibilityWrapper:
    """Get sessions database compatibility wrapper"""
    return get_redis_client_compat("sessions")


# Migration helper functions
async def test_async_migration(database: str = "main") -> dict:
    """
    Test async Redis operations for migration validation

    Returns:
        dict: Test results and performance metrics
    """
    import time

    results = {
        "database": database,
        "tests": {},
        "overall_success": False,
        "migration_ready": False,
    }

    try:
        compat = get_redis_client_compat(database)

        # Test basic operations
        test_key = f"migration_test_{int(time.time())}"
        test_value = "async_migration_test_value"

        # Test async set
        start_time = time.time()
        set_result = await compat.aset(test_key, test_value, ex=60)
        set_time = (time.time() - start_time) * 1000

        # Test async get
        start_time = time.time()
        get_result = await compat.aget(test_key)
        get_time = (time.time() - start_time) * 1000

        # Test async delete
        start_time = time.time()
        del_result = await compat.adelete(test_key)
        del_time = (time.time() - start_time) * 1000

        # Test async ping
        start_time = time.time()
        ping_result = await compat.aping()
        ping_time = (time.time() - start_time) * 1000

        results["tests"] = {
            "async_set": {
                "success": set_result is True,
                "response_time_ms": round(set_time, 2),
            },
            "async_get": {
                "success": get_result == test_value,
                "response_time_ms": round(get_time, 2),
                "value_match": get_result == test_value,
            },
            "async_delete": {
                "success": del_result == 1,
                "response_time_ms": round(del_time, 2),
            },
            "async_ping": {
                "success": ping_result is True,
                "response_time_ms": round(ping_time, 2),
            },
        }

        # Check overall success
        all_tests_passed = all(
            test_data.get("success", False) for test_data in results["tests"].values()
        )

        results["overall_success"] = all_tests_passed
        results["migration_ready"] = all_tests_passed
        results["average_response_time"] = round(
            sum(
                test_data.get("response_time_ms", 0)
                for test_data in results["tests"].values()
            )
            / len(results["tests"]),
            2,
        )

    except Exception as e:
        results["error"] = str(e)
        results["migration_ready"] = False
        logger.error(f"Async migration test failed for database '{database}': {e}")

    return results


async def migrate_sync_to_async_example():
    """
    Example showing how to migrate from sync to async Redis operations
    """
    logger.info("=== Redis Migration Example ===")

    # Old sync way (deprecated)
    logger.info("OLD SYNC WAY (deprecated):")
    try:
        compat = get_redis_client_compat("main")

        # These will show deprecation warnings
        compat.set("example_key", "example_value", ex=60)
        value = compat.get("example_key")
        logger.info(f"Sync result: {value}")

    except Exception as e:
        logger.error(f"Sync operations failed: {e}")

    # New async way (preferred)
    logger.info("NEW ASYNC WAY (preferred):")
    try:
        compat = get_redis_client_compat("main")

        # Use async methods - no deprecation warnings
        await compat.aset("example_key_async", "example_value_async", ex=60)
        value = await compat.aget("example_key_async")
        logger.info(f"Async result: {value}")

        # Cleanup
        await compat.adelete("example_key", "example_key_async")

    except Exception as e:
        logger.error(f"Async operations failed: {e}")

    # Test migration readiness
    test_results = await test_async_migration("main")
    logger.info(f"Migration test results: {test_results}")


if __name__ == "__main__":
    # Run migration example (logging configured via centralized logging_manager)
    asyncio.run(migrate_sync_to_async_example())
