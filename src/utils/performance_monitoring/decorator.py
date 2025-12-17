# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Monitoring Decorator Module

Contains the monitor_performance decorator for tracking function execution.

Extracted from performance_monitor.py as part of Issue #381 refactoring.
"""

import asyncio
import json
import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)

# Module-level redis client reference (set by monitor)
_redis_client = None


def set_redis_client(client):
    """Set the Redis client for metrics storage."""
    global _redis_client
    _redis_client = client


def _store_performance_in_redis(
    category: str, func_name: str, execution_time: float, args_count: int, kwargs_count: int
) -> None:
    """Store performance metrics in Redis."""
    if not _redis_client:
        return
    try:
        key = f"function_performance:{category}:{func_name}"
        _redis_client.zadd(
            key,
            {
                json.dumps(
                    {
                        "execution_time_ms": execution_time * 1000,
                        "timestamp": time.time(),
                        "args_count": args_count,
                        "kwargs_count": kwargs_count,
                    }
                ): time.time()
            },
        )
        _redis_client.expire(key, 3600)  # 1 hour retention
    except Exception:
        pass  # Non-critical: Redis metrics storage failure


def monitor_performance(category: str = "general"):
    """Decorator to monitor function performance."""

    def decorator(func):
        """Wrap function with performance monitoring and Redis metric storage."""

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            """Execute async function with timing and logging."""
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time

                logger.info(
                    f"PERFORMANCE [{category}]: {func.__name__} executed in {execution_time:.3f}s"
                )
                _store_performance_in_redis(
                    category, func.__name__, execution_time, len(args), len(kwargs)
                )

                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(
                    f"PERFORMANCE [{category}]: {func.__name__} failed "
                    f"after {execution_time:.3f}s: {e}"
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            """Execute sync function with timing and logging."""
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time

                logger.info(
                    f"PERFORMANCE [{category}]: {func.__name__} "
                    f"executed in {execution_time:.3f}s"
                )

                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(
                    f"PERFORMANCE [{category}]: {func.__name__} failed "
                    f"after {execution_time:.3f}s: {e}"
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
