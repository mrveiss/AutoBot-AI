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
- Circuit breaker pattern
- Health monitoring
- Connection pooling with TCP keepalive tuning
- Comprehensive statistics and metrics
- Database name mapping with type-safe enums
- Async and sync support (unified interface)
- Automatic retry with exponential backoff + tenacity
- Connection state management
- "Loading dataset" state handling (waits for Redis startup)
- WeakSet connection tracking (no GC interference)
- Pipeline context managers
- Named database convenience methods
- Idle connection cleanup
- YAML configuration loading
- Service registry integration
- Centralized timeout configuration

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

Note: This module has been refactored as part of Issue #381 god class refactoring.
All classes are now in the redis_management/ package. This module provides
backward compatibility by re-exporting all classes.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, Optional, Union

import redis
import redis.asyncio as async_redis

# Import all types, data models, and classes from the package (Issue #381 refactoring)
from src.utils.redis_management.types import (
    ConnectionState,
    DATABASE_MAPPING,
    RedisDatabase,
)
from src.utils.redis_management.config import (
    PoolConfig,
    RedisConfig,
    RedisConfigLoader,
)
from src.utils.redis_management.statistics import (
    ConnectionMetrics,
    ManagerStats,
    PoolStatistics,
    RedisStats,
)
from src.utils.redis_management.connection_manager import (
    RedisConnectionManager,
)

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    # Enums
    "RedisDatabase",
    "ConnectionState",
    # Constants
    "DATABASE_MAPPING",
    # Configuration
    "RedisConfig",
    "RedisConfigLoader",
    "PoolConfig",
    # Statistics
    "RedisStats",
    "PoolStatistics",
    "ManagerStats",
    "ConnectionMetrics",
    # Manager
    "RedisConnectionManager",
    # Convenience functions
    "get_redis_client",
    "get_knowledge_base_redis",
    "get_prompts_redis",
    "get_agents_redis",
    "get_metrics_redis",
    "get_main_redis",
    "get_redis_health",
    "get_redis_metrics",
    "close_all_redis_connections",
    "redis_context",
    # Backward compatibility
    "RedisDatabaseManager",
    "redis_db_manager",
]


# =============================================================================
# Global Connection Manager Instance
# =============================================================================

_connection_manager = RedisConnectionManager()


# =============================================================================
# Main Interface Functions
# =============================================================================


def get_redis_client(
    async_client: bool = False, database: str = "main"
) -> Union[redis.Redis, async_redis.Redis, None]:
    """
    Get a Redis client instance with circuit breaker and health monitoring.

    This is the CANONICAL method for Redis access in AutoBot. Direct redis.Redis()
    instantiation is FORBIDDEN per CLAUDE.md policy.

    CONSOLIDATED FEATURES (from 6 implementations):
    ===============================================
    - Circuit breaker protection (prevents cascading failures)
    - Health monitoring (tracks connection states)
    - Connection pooling with TCP keepalive tuning (prevents connection drops)
    - "Loading dataset" state handling (waits for Redis startup)
    - Tenacity retry logic (exponential backoff, up to 5 attempts)
    - WeakSet connection tracking (no GC interference)
    - Comprehensive statistics collection (RedisStats/ManagerStats)
    - YAML configuration support (redis-databases.yaml)
    - Service registry integration
    - Centralized timeout configuration
    - Parameter filtering (removes None values)

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


# =============================================================================
# Convenience Functions for Specific Database Access
# =============================================================================


def get_knowledge_base_redis(**kwargs) -> Optional[redis.Redis]:
    """Get Redis client for knowledge base data."""
    return get_redis_client(database="knowledge", **kwargs)


def get_prompts_redis(**kwargs) -> Optional[redis.Redis]:
    """Get Redis client for prompt templates."""
    return get_redis_client(database="prompts", **kwargs)


def get_agents_redis(**kwargs) -> Optional[redis.Redis]:
    """Get Redis client for agent communication."""
    return get_redis_client(database="agents", **kwargs)


def get_metrics_redis(**kwargs) -> Optional[redis.Redis]:
    """Get Redis client for performance metrics."""
    return get_redis_client(database="metrics", **kwargs)


def get_main_redis(**kwargs) -> Optional[redis.Redis]:
    """Get Redis client for main application data."""
    return get_redis_client(database="main", **kwargs)


# =============================================================================
# Health and Metrics Functions
# =============================================================================


def get_redis_health() -> Dict[str, Any]:
    """Get Redis health status."""
    return _connection_manager.get_health_status()


def get_redis_metrics(database: Optional[str] = None) -> Dict[str, Any]:
    """Get Redis connection metrics."""
    return _connection_manager.get_metrics(database)


# =============================================================================
# Cleanup Function
# =============================================================================


async def close_all_redis_connections():
    """Close all Redis connections."""
    await _connection_manager.close_all()


# =============================================================================
# Context Manager for Redis Operations
# =============================================================================


@asynccontextmanager
async def redis_context(
    database: str = "main",
) -> AsyncGenerator[async_redis.Redis, None]:
    """
    Async context manager for Redis operations.

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


# =============================================================================
# BACKWARD COMPATIBILITY LAYER
# =============================================================================
# Support for old redis_database_manager imports (archived in P1)


class RedisDatabaseManager:
    """
    DEPRECATED: Backward compatibility wrapper for archived redis_database_manager.

    This class provides compatibility for code still using the old
    RedisDatabaseManager interface. All new code should use get_redis_client() directly.

    Migration:
        OLD: manager = RedisDatabaseManager()
             client = await manager.get_async_connection(RedisDatabase.MAIN)

        NEW: client = await get_redis_client(async_client=True, database="main")
    """

    def __init__(self):
        """Initialize deprecated manager with deprecation warning."""
        logger.warning(
            "DEPRECATED: RedisDatabaseManager is deprecated. "
            "Use get_redis_client() from src.utils.redis_client instead."
        )

    def get_connection(
        self, database: Union[RedisDatabase, str]
    ) -> Optional[redis.Redis]:
        """Get synchronous Redis connection (DEPRECATED)."""
        db_name = (
            database.name.lower() if isinstance(database, RedisDatabase) else database
        )
        return get_redis_client(async_client=False, database=db_name)

    async def get_async_connection(
        self, database: Union[RedisDatabase, str]
    ) -> Optional[async_redis.Redis]:
        """Get asynchronous Redis connection (DEPRECATED)."""
        db_name = (
            database.name.lower() if isinstance(database, RedisDatabase) else database
        )
        return await get_redis_client(async_client=True, database=db_name)


# Global instance for backward compatibility (lazy-loaded)
# Issue #665: Use lazy initialization to avoid deprecation warning at import time
_redis_db_manager_instance: Optional[RedisDatabaseManager] = None


def _get_redis_db_manager() -> RedisDatabaseManager:
    """
    Get the deprecated RedisDatabaseManager instance (lazy-loaded).

    Issue #665: Lazy initialization prevents deprecation warning at module import.
    Warning only shows when deprecated functionality is actually used.
    """
    global _redis_db_manager_instance
    if _redis_db_manager_instance is None:
        _redis_db_manager_instance = RedisDatabaseManager()
    return _redis_db_manager_instance


class _LazyRedisDatabaseManager:
    """
    Lazy proxy for RedisDatabaseManager to defer deprecation warning.

    Issue #665: This proxy delays instantiation until first access,
    preventing the deprecation warning from appearing at import time.
    """

    def __getattr__(self, name: str):
        """Proxy attribute access to the real manager."""
        return getattr(_get_redis_db_manager(), name)


# Export as the original name for backward compatibility
redis_db_manager = _LazyRedisDatabaseManager()
