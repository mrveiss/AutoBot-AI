# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Project State Tracking - Tracking Functions Module

Functions for tracking errors, API calls, and user interactions.

Part of Issue #381 - God Class Refactoring
"""

import asyncio
import functools
import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from .types import REDIS_METRIC_KEYS, SIGNIFICANT_INTERACTIONS

logger = logging.getLogger(__name__)


async def track_error_to_redis(
    redis_client: Any,
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Track an error occurrence to Redis for error rate calculation"""
    try:
        if not redis_client:
            return

        current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        error_key = f"{REDIS_METRIC_KEYS['error_count']}:{current_hour.timestamp()}"

        # Issue #379: Batch Redis operations using pipeline
        async with redis_client.pipeline() as pipe:
            await pipe.incr(error_key)
            await pipe.expire(error_key, 86400)  # Expire after 24 hours
            await pipe.execute()

    except Exception as e:
        logger.error("Failed to track error to Redis: %s", e)


async def track_api_call_to_redis(
    redis_client: Any,
    endpoint: str,
    method: str = "GET",
    response_status: Optional[int] = None,
) -> None:
    """Track an API call to Redis for metrics"""
    try:
        if not redis_client:
            return

        current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        api_key = f"{REDIS_METRIC_KEYS['api_calls']}:{current_hour.timestamp()}"
        endpoint_key = f"autobot:metrics:endpoints:{endpoint}:calls"

        # Issue #379: Batch all Redis operations using pipeline
        async with redis_client.pipeline() as pipe:
            # Increment API call count for this hour
            await pipe.incr(api_key)
            await pipe.expire(api_key, 86400)  # Expire after 24 hours
            # Track specific endpoint stats
            await pipe.incr(endpoint_key)
            await pipe.expire(endpoint_key, 86400)
            await pipe.execute()

        logger.debug("API call tracked: %s %s -> %s", method, endpoint, response_status)

    except Exception as e:
        logger.error("Failed to track API call to Redis: %s", e)


async def track_user_interaction_to_redis(
    redis_client: Any,
    interaction_type: str,
    user_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """Track a user interaction to Redis for metrics"""
    try:
        if not redis_client:
            return

        current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        interaction_key = (
            f"{REDIS_METRIC_KEYS['user_interactions']}:{current_hour.timestamp()}"
        )
        type_key = f"autobot:metrics:interaction_types:{interaction_type}:count"

        # Issue #379: Batch all Redis operations using pipeline
        async with redis_client.pipeline() as pipe:
            # Increment user interaction count for this hour
            await pipe.incr(interaction_key)
            await pipe.expire(interaction_key, 86400)  # Expire after 24 hours
            # Track interaction types
            await pipe.incr(type_key)
            await pipe.expire(type_key, 86400)
            await pipe.execute()

        logger.debug("User interaction tracked: %s by %s", interaction_type, user_id)

    except Exception as e:
        logger.error("Failed to track user interaction to Redis: %s", e)


def is_significant_interaction(interaction_type: str) -> bool:
    """Check if an interaction type is considered significant"""
    return interaction_type in SIGNIFICANT_INTERACTIONS


# ============================================================================
# Error Tracking Decorator and Helpers
# ============================================================================


def _handle_sync_error_tracking(
    error: Exception, func: Callable, args: tuple, kwargs: dict
) -> None:
    """Handle error tracking for sync functions"""
    error_context = {
        "function": func.__name__,
        "module": func.__module__,
        "args": str(args)[:200],
        "kwargs": str(kwargs)[:200],
    }

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            _schedule_error_tracking(error, error_context)
        else:
            _run_error_tracking(error, error_context)
    except Exception:
        logger.error("Error in %s: %s", func.__name__, error)


def _schedule_error_tracking(error: Exception, context: Dict[str, Any]) -> None:
    """Schedule error tracking in running event loop"""
    # Import here to avoid circular imports
    from . import track_system_error

    asyncio.create_task(track_system_error(error, context))


def _run_error_tracking(error: Exception, context: Dict[str, Any]) -> None:
    """Run error tracking in new event loop"""
    # Import here to avoid circular imports
    from . import track_system_error

    asyncio.run(track_system_error(error, context))


def error_tracking_decorator(func: Callable) -> Callable:
    """Decorator to automatically track errors in functions"""

    if asyncio.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            """Async wrapper that tracks errors before re-raising."""
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Import here to avoid circular imports
                from . import track_system_error

                await track_system_error(
                    e,
                    {
                        "function": func.__name__,
                        "module": func.__module__,
                        "args": str(args)[:200],
                        "kwargs": str(kwargs)[:200],
                    },
                )
                raise

        return async_wrapper
    else:

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            """Sync wrapper that tracks errors before re-raising."""
            try:
                return func(*args, **kwargs)
            except Exception as e:
                _handle_sync_error_tracking(e, func, args, kwargs)
                raise

        return sync_wrapper
