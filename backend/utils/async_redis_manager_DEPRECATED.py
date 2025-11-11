"""
DEPRECATED: Use src.utils.redis_client instead

This module has been DEPRECATED and replaced by src.utils.redis_client.py

Migration Guide:
===============
OLD (async_redis_manager.py):
    from backend.utils.async_redis_manager import get_async_redis, AsyncRedisManager
    redis = await get_async_redis()
    manager = AsyncRedisManager()
    await manager.initialize()

NEW (redis_client.py):
    from src.utils.redis_client import get_redis_client
    redis = await get_redis_client(async_client=True, database='main')
    # No manager initialization needed - handled automatically

This wrapper exists for backward compatibility only. All new code should use
the Redis client utility.

Consolidation completed as part of: "Redis Connection Patterns Consolidation"
Date: 2025-01-09
"""

import logging
import warnings

# Import from Redis client utility
from src.utils.redis_client import (
    close_all_redis_connections,
    get_redis_client,
    get_redis_health,
    get_redis_metrics,
    redis_context,
)

logger = logging.getLogger(__name__)

# Issue deprecation warning
warnings.warn(
    "backend.utils.async_redis_manager is DEPRECATED. Use src.utils.redis_client instead. "
    "See migration guide in this file's docstring.",
    DeprecationWarning,
    stacklevel=2,
)

logger.warning(
    "DEPRECATION: backend.utils.async_redis_manager is deprecated. "
    "Migrate to src.utils.redis_client"
)


# Backward compatibility wrappers
async def get_async_redis(database: str = "main"):
    """
    DEPRECATED: Use get_redis_client(async_client=True) instead

    Wrapper for backward compatibility.
    """
    warnings.warn(
        "get_async_redis() is deprecated. Use get_redis_client(async_client=True, database=...) instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return await get_redis_client(async_client=True, database=database)


class AsyncRedisManager:
    """
    DEPRECATED: Use get_redis_client() instead

    This class wrapper exists for backward compatibility only.
    The consolidated implementation handles all connection management automatically.
    """

    def __init__(self):
        warnings.warn(
            "AsyncRedisManager is deprecated. Use get_redis_client() directly instead",
            DeprecationWarning,
            stacklevel=2,
        )
        self._initialized = False

    async def initialize(self):
        """Compatibility method - no-op in consolidated implementation"""
        self._initialized = True
        return True

    async def get_connection(self, database: str = "main"):
        """Get Redis connection - delegates to consolidated implementation"""
        return await get_redis_client(async_client=True, database=database)

    async def close(self):
        """Close connections - delegates to consolidated implementation"""
        await close_all_redis_connections()


# Re-export useful functions
__all__ = [
    "get_async_redis",
    "AsyncRedisManager",
    "get_redis_health",
    "get_redis_metrics",
    "redis_context",
    "close_all_redis_connections",
]
