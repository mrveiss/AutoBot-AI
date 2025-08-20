"""
Centralized Redis client utility
Eliminates code duplication across modules by providing a singleton Redis
client factory
"""

import logging
from typing import Optional, Union

import redis
import redis.asyncio as async_redis

from src.config import config as global_config_manager
from src.utils.config_manager import config_manager

logger = logging.getLogger(__name__)

# Global Redis client instances
_redis_client: Optional[redis.Redis] = None
_async_redis_client: Optional[async_redis.Redis] = None


def get_redis_client(
    async_client: bool = False,
) -> Union[redis.Redis, async_redis.Redis, None]:
    """
    Returns a singleton instance of the Redis client, configured from the
    global application config.

    Args:
        async_client (bool): If True, returns async Redis client. If False,
            returns sync client.

    Returns:
        Union[redis.Redis, async_redis.Redis, None]: Redis client instance or
            None if Redis is disabled
    """
    global _redis_client, _async_redis_client

    try:
        # Get Redis configuration from global config manager
        # First try memory.redis config (current structure)
        memory_config = global_config_manager.get("memory", {})
        redis_config = memory_config.get("redis", {})

        # Fall back to task_transport.redis config if memory config not
        # available
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
        host = config_manager.get("redis.host", "localhost")
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
                    f"Async Redis client initialized for {host}:{port} " f"(DB: {db})"
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
                logger.info(f"Redis client initialized for {host}:{port} (DB: {db})")
            return _redis_client

    except Exception as e:
        logger.error(f"Failed to initialize Redis client: {str(e)}")
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
