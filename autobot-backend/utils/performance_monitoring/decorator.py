# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Performance Monitoring Decorator Module

Contains the monitor_performance decorator for tracking function execution.

Extracted from performance_monitor.py as part of Issue #381 refactoring.
"""

import asyncio
import json
import time
from functools import wraps
from typing import Any, Callable

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import TTL_1_HOUR

logger = get_logger(__name__)

# Resolves the Redis client at call time; each monitor passes its own, so two
# monitors on different dbs never write into each other's (#18458).
ClientProvider = Callable[[], Any]


def _store_performance_in_redis(
    client_provider: ClientProvider | None,
    category: str,
    func_name: str,
    execution_time: float,
    args_count: int,
    kwargs_count: int,
) -> None:
    """Store performance metrics in Redis."""
    client = client_provider() if client_provider is not None else None
    if not client:
        return
    try:
        key = f"function_performance:{category}:{func_name}"
        client.zadd(
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
        client.expire(key, TTL_1_HOUR)  # 1 hour retention
    except Exception:
        logger.debug("Suppressed exception in try block", exc_info=True)


def _create_async_wrapper(func, category: str, client_provider: ClientProvider | None):
    """
    Create async wrapper for performance monitoring.

    Issue #620.
    """

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        """Execute async function with timing and logging."""
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.info(f"PERFORMANCE [{category}]: {func.__name__} executed in {execution_time:.3f}s")
            _store_performance_in_redis(
                client_provider, category, func.__name__, execution_time, len(args), len(kwargs)
            )
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"PERFORMANCE [{category}]: {func.__name__} failed " f"after {execution_time:.3f}s: {e}")
            raise

    return async_wrapper


def _create_sync_wrapper(func, category: str, client_provider: ClientProvider | None):
    """
    Create sync wrapper for performance monitoring.

    Issue #620.
    """

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        """Execute sync function with timing and logging."""
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.info(f"PERFORMANCE [{category}]: {func.__name__} executed in {execution_time:.3f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"PERFORMANCE [{category}]: {func.__name__} failed " f"after {execution_time:.3f}s: {e}")
            raise

    return sync_wrapper


def monitor_performance(category: str = "general", client_provider: ClientProvider | None = None):
    """Decorator to monitor function performance.

    ``client_provider`` is a zero-arg callable returning the owning monitor's
    Redis client (or None); without it nothing is stored in Redis.
    """

    def decorator(func):
        """Wrap function with performance monitoring and Redis metric storage. Issue #620."""
        if asyncio.iscoroutinefunction(func):
            return _create_async_wrapper(func, category, client_provider)
        else:
            return _create_sync_wrapper(func, category, client_provider)

    return decorator
