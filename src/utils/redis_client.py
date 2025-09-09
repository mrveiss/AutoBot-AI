"""
Centralized Redis client utility
Eliminates code duplication across modules by providing a singleton Redis
client factory with database separation support
"""

import logging
from typing import Optional, Union

import redis
import redis.asyncio as async_redis

from src.config import config as global_config_manager
from src.utils.config_manager import config_manager
from src.utils.redis_database_manager import redis_db_manager

logger = logging.getLogger(__name__)

# Global Redis client instances (for backward compatibility)
_redis_client: Optional[redis.Redis] = None
_async_redis_client: Optional[async_redis.Redis] = None


def get_redis_client(
    async_client: bool = False,
    database: str = "main",
) -> Union[redis.Redis, async_redis.Redis, None]:
    """
    Returns a Redis client instance with database separation support.

    Args:
        async_client (bool): If True, returns async Redis client. If False,
            returns sync client.
        database (str): Database name (e.g., 'main', 'knowledge', 'prompts')

    Returns:
        Union[redis.Redis, async_redis.Redis, None]: Redis client instance or
            None if Redis is disabled
    """
    try:
        # Use new database manager for proper database separation
        if async_client:
            # For async clients, we need to handle this properly
            import asyncio

            if asyncio.iscoroutinefunction(redis_db_manager.get_async_connection):
                # Return a coroutine that can be awaited
                async def get_async_client():
                    return await redis_db_manager.get_async_connection(database)

                return get_async_client()
            else:
                logger.warning(
                    "Async Redis not properly configured, falling back to sync"
                )
                return redis_db_manager.get_connection(database)
        else:
            return redis_db_manager.get_connection(database)

    except Exception as e:
        logger.error(f"Failed to get Redis client for database '{database}': {str(e)}")

        # Fallback to legacy method for backward compatibility
        global _redis_client, _async_redis_client

        try:
            # Get Redis configuration from global config manager
            memory_config = global_config_manager.get("memory", {})
            redis_config = memory_config.get("redis", {})

            # Fall back to task_transport.redis config if memory config not available
            if not redis_config or not redis_config.get("enabled", False):
                task_transport_config = global_config_manager.get("task_transport", {})
                if task_transport_config.get("type") == "redis":
                    redis_config = task_transport_config.get("redis", {})
                else:
                    logger.info("Redis is disabled in configuration")
                    return None

            if not redis_config:
                logger.warning("No Redis configuration found")
                return None

            # Extract connection parameters using centralized config
            host = config_manager.get("redis.host", "172.16.168.23")
            port = config_manager.get("redis.port", 6379)
            password = config_manager.get("redis.password", None)
            db = config_manager.get("redis.db", 0)

            if async_client:
                if _async_redis_client is None:
                    _async_redis_client = async_redis.Redis(
                        host=host,
                        port=port,
                        password=password,
                        db=db,
                        decode_responses=True,
                    )
                    logger.info(
                        f"Fallback async Redis client initialized for "
                        f"{host}:{port} (DB: {db})"
                    )
                return _async_redis_client
            else:
                if _redis_client is None:
                    _redis_client = redis.Redis(
                        host=host,
                        port=port,
                        password=password,
                        db=db,
                        decode_responses=True,
                    )
                    logger.info(
                        f"Fallback Redis client initialized for "
                        f"{host}:{port} (DB: {db})"
                    )
                return _redis_client

        except Exception as fallback_error:
            logger.error(
                f"Fallback Redis client initialization failed: {str(fallback_error)}"
            )
            return None


def get_redis_config() -> dict:
    """
    Get Redis configuration from global config manager.

    Returns:
        dict: Redis configuration dictionary
    """
    # Try memory.redis config first
    memory_config = global_config_manager.get("memory", {})
    redis_config = memory_config.get("redis", {})

    # Fall back to task_transport.redis config
    if not redis_config or not redis_config.get("enabled", False):
        task_transport_config = global_config_manager.get("task_transport", {})
        if task_transport_config.get("type") == "redis":
            redis_config = task_transport_config.get("redis", {})

    return redis_config


def reset_redis_clients():
    """
    Reset Redis client instances. Useful for testing or configuration changes.
    """
    global _redis_client, _async_redis_client

    # Reset new database manager connections
    try:
        redis_db_manager.close_all_connections()
        logger.info("Database manager connections closed")
    except Exception as e:
        logger.error(f"Error closing database manager connections: {e}")

    # Reset legacy singleton instances for backward compatibility
    if _redis_client:
        try:
            _redis_client.close()
        except Exception:  # noqa: S110
            pass
        _redis_client = None

    if _async_redis_client:
        try:
            # Async clients need different cleanup
            pass
        except Exception:  # noqa: S110
            pass
        _async_redis_client = None

    logger.info("Redis client instances reset")


def test_redis_connection() -> bool:
    """
    Test Redis connection without creating persistent client.

    Returns:
        bool: True if connection successful, False otherwise
    """
    try:
        redis_config = get_redis_config()
        if not redis_config:
            return False

        host = config_manager.get("redis.host", "localhost")
        port = config_manager.get("redis.port", 6379)
        password = config_manager.get("redis.password", None)

        test_client = redis.Redis(
            host=host, port=port, password=password, decode_responses=True
        )

        test_client.ping()
        test_client.close()
        return True

    except Exception as e:
        logger.error(f"Redis connection test failed: {str(e)}")
        return False


# Convenience functions for specific database access
def get_knowledge_base_redis(**kwargs) -> redis.Redis:
    """Get Redis client for knowledge base data"""
    return get_redis_client(database="knowledge", **kwargs)


def get_prompts_redis(**kwargs) -> redis.Redis:
    """Get Redis client for prompt templates"""
    return get_redis_client(database="prompts", **kwargs)


def get_agents_redis(**kwargs) -> redis.Redis:
    """Get Redis client for agent communication"""
    return get_redis_client(database="agents", **kwargs)


def get_metrics_redis(**kwargs) -> redis.Redis:
    """Get Redis client for performance metrics"""
    return get_redis_client(database="metrics", **kwargs)


def get_main_redis(**kwargs) -> redis.Redis:
    """Get Redis client for main application data"""
    return get_redis_client(database="main", **kwargs)
