"""
Centralized Redis Client Utility - CANONICAL REDIS PATTERN

This module provides the ONLY approved method for Redis client initialization
across the AutoBot codebase. Direct redis.Redis() instantiation is FORBIDDEN.

MANDATORY USAGE PATTERN:
=======================
from src.utils.redis_client import get_redis_client

# Get synchronous client for 'main' database
redis_client = get_redis_client(async_client=False, database="main")

# Get async client for 'knowledge' database
async_redis = await get_redis_client(async_client=True, database="knowledge")

DATABASE SEPARATION:
===================
AutoBot uses named Redis databases for logical separation:
- 'main': General application cache, queues, session data
- 'knowledge': Knowledge base vectors and embeddings
- 'prompts': LLM prompt templates and agent configurations
- 'agents': Agent communication and orchestration state
- 'metrics': Performance metrics and analytics data
- 'analytics': Codebase analytics and indexing state

MIGRATION FROM DIRECT INSTANTIATION:
====================================
❌ OLD PATTERN (67 files still use this - MUST MIGRATE):
    import redis
    client = redis.Redis(host="172.16.168.23", port=6379, db=0)
    client.set("key", "value")

✅ NEW PATTERN (Canonical):
    from src.utils.redis_client import get_redis_client
    client = get_redis_client(database="main")
    client.set("key", "value")

BENEFITS:
- Centralized configuration (NetworkConstants, unified_config_manager)
- Connection pooling via redis_database_manager
- Database separation with clear naming
- Fallback logic for backward compatibility
- Consistent timeout and keepalive settings

ASYNC/SYNC PATTERNS:
===================
Synchronous (for non-async functions):
    from src.utils.redis_client import get_redis_client

    def process_data():
        redis_client = get_redis_client(database="main")
        data = redis_client.get("key")
        return data

Async (for async functions):
    from src.utils.redis_client import get_redis_client

    async def async_process():
        # get_redis_client returns a coroutine for async clients
        redis_client = await get_redis_client(async_client=True, database="main")
        data = await redis_client.get("key")
        return data

CONVENIENCE FUNCTIONS:
=====================
Use named functions for common databases:
    from src.utils.redis_client import get_knowledge_base_redis
    kb_redis = get_knowledge_base_redis()  # Automatically uses 'knowledge' DB

Available convenience functions:
- get_main_redis()          -> database="main"
- get_knowledge_base_redis() -> database="knowledge"
- get_prompts_redis()        -> database="prompts"
- get_agents_redis()         -> database="agents"
- get_metrics_redis()        -> database="metrics"

TROUBLESHOOTING:
===============
Problem: "Redis connection failed"
Solution: Check Redis VM is running: redis-cli -h 172.16.168.23 ping

Problem: "Database not found"
Solution: Use named databases from list above, not DB numbers

Problem: "Can't use await with get_redis_client"
Solution: Set async_client=True: await get_redis_client(async_client=True, ...)

Problem: "Connection pool exhausted"
Solution: redis_database_manager handles pooling - check for leaked connections

ARCHITECTURE:
============
redis_client.py (THIS FILE)
    └─> Calls redis_database_manager.get_connection()
            └─> Uses redis.ConnectionPool for efficient connection reuse
                    └─> Connects to NetworkConstants.REDIS_VM_IP:REDIS_PORT

MIGRATION CHECKLIST:
===================
When migrating a file from direct instantiation:
1. ✓ Replace `import redis` with `from src.utils.redis_client import get_redis_client`
2. ✓ Replace `redis.Redis(host=..., port=..., db=N)` with `get_redis_client(database="name")`
3. ✓ Remove hardcoded IPs/ports - NetworkConstants handles this
4. ✓ Use named databases instead of DB numbers
5. ✓ Test connection works with existing code
6. ✓ Run code review to verify migration correctness

See CLAUDE.md "🔴 REDIS CLIENT USAGE" section for policy details.
"""

import logging
from typing import Optional, Union

import redis
import redis.asyncio as async_redis

from src.constants.network_constants import NetworkConstants
from src.unified_config_manager import config as config_manager
from src.unified_config_manager import config as global_config_manager
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
    Get a Redis client instance with database separation and connection pooling.

    This is the CANONICAL method for Redis access in AutoBot. Direct redis.Redis()
    instantiation is FORBIDDEN per CLAUDE.md policy.

    Args:
        async_client (bool): If True, returns async Redis client (for async functions).
                             If False, returns synchronous client (for regular functions).
                             Default: False
        database (str): Named database for logical separation. Use self-documenting
                        names instead of DB numbers. Default: "main"

                        Available databases:
                        - 'main': General cache, queues, session data
                        - 'knowledge': Knowledge base vectors/embeddings
                        - 'prompts': LLM prompt templates
                        - 'agents': Agent communication state
                        - 'metrics': Performance metrics
                        - 'analytics': Codebase analytics

    Returns:
        Union[redis.Redis, async_redis.Redis, None]:
            - redis.Redis: Synchronous client (if async_client=False)
            - async_redis.Redis: Async client coroutine (if async_client=True)
            - None: If Redis is disabled in configuration

    Examples:
        Basic synchronous usage:
            >>> from src.utils.redis_client import get_redis_client
            >>> redis = get_redis_client(database="main")
            >>> redis.set("key", "value")
            >>> redis.get("key")
            'value'

        Async usage in async functions:
            >>> async def store_data():
            ...     redis = await get_redis_client(async_client=True, database="main")
            ...     await redis.set("key", "value")
            ...     return await redis.get("key")

        Using named databases:
            >>> # Knowledge base vectors
            >>> kb_redis = get_redis_client(database="knowledge")
            >>>
            >>> # Agent orchestration
            >>> agent_redis = get_redis_client(database="agents")

        Migration from direct instantiation:
            >>> # OLD (FORBIDDEN):
            >>> # import redis
            >>> # client = redis.Redis(host="172.16.168.23", port=6379, db=0)
            >>>
            >>> # NEW (CANONICAL):
            >>> from src.utils.redis_client import get_redis_client
            >>> client = get_redis_client(database="main")

    Raises:
        None: Function handles all errors internally and logs them.
              Returns None if connection fails instead of raising exceptions.

    Notes:
        - Uses redis_database_manager for connection pooling and efficient reuse
        - Configuration sourced from NetworkConstants and unified_config_manager
        - Falls back to legacy singleton method for backward compatibility
        - Async clients return coroutines that must be awaited
        - Database names map to Redis DB numbers internally (see redis_database_manager)

    See Also:
        - get_knowledge_base_redis(): Convenience function for 'knowledge' database
        - get_prompts_redis(): Convenience function for 'prompts' database
        - get_agents_redis(): Convenience function for 'agents' database
        - reset_redis_clients(): Reset all connections (useful for testing)
        - test_redis_connection(): Test connectivity without creating client
    """
    try:
        # PREFERRED PATH: Use redis_database_manager for connection pooling
        # This provides:
        # - Efficient connection reuse via redis.ConnectionPool
        # - Database name -> DB number mapping
        # - Centralized timeout/keepalive configuration
        # - NetworkConstants for IP/port configuration

        if async_client:
            # ASYNC CLIENT PATH: For use in async functions with await
            # Example: redis = await get_redis_client(async_client=True, database="main")
            import asyncio

            if asyncio.iscoroutinefunction(redis_db_manager.get_async_connection):
                # Return a coroutine that must be awaited by caller
                # The coroutine wraps the async connection request
                async def get_async_client():
                    return await redis_db_manager.get_async_connection(database)

                return get_async_client()
            else:
                # Async not available - fall back to sync client
                # This can happen if async Redis dependencies not installed
                logger.warning(
                    "Async Redis not properly configured, falling back to sync"
                )
                return redis_db_manager.get_connection(database)
        else:
            # SYNC CLIENT PATH: For use in regular (non-async) functions
            # Example: redis = get_redis_client(database="main")
            # Database manager handles connection pooling and DB number mapping
            return redis_db_manager.get_connection(database)

    except Exception as e:
        logger.error(f"Failed to get Redis client for database '{database}': {str(e)}")

        # FALLBACK PATH: Legacy singleton method for backward compatibility
        # This fallback exists to ensure existing code continues working during migration
        # New code should NOT rely on this - it uses the old DB number approach
        # Migration goal: Eventually remove this fallback once all 67 files migrated
        global _redis_client, _async_redis_client

        try:
            # STEP 1: Try to load Redis config from unified_config_manager
            # Config can come from multiple sources (config.yaml, .env, defaults)
            memory_config = global_config_manager.get("memory", {})
            redis_config = memory_config.get("redis", {})

            # STEP 2: If memory.redis not configured, check task_transport.redis
            # Some legacy configurations use task_transport for Redis settings
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

            # STEP 3: Extract connection parameters using centralized config
            # Uses NetworkConstants for defaults (REDIS_VM_IP, REDIS_PORT)
            host = config_manager.get("redis.host", NetworkConstants.REDIS_VM_IP)
            port = config_manager.get("redis.port", NetworkConstants.REDIS_PORT)
            password = config_manager.get("redis.password", None)
            db = config_manager.get("redis.db", 0)  # DB number (legacy approach)

            # STEP 4: Create singleton client instance (cached for reuse)
            # WARNING: This uses DB numbers instead of named databases
            # This fallback should ONLY activate if redis_database_manager fails
            if async_client:
                if _async_redis_client is None:
                    # Create async Redis client (for use with await)
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
                    # Create sync Redis client (for regular functions)
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
