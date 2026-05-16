# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Error Isolation Module

Issue #4342: Component-level error isolation prevents cascading failures.
Skill failures do not halt agent execution. Peripheral services can fail
without affecting core functionality.
"""

import asyncio
import functools
from typing import Any, Callable, TypeVar

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class IsolatedError(Exception):
    """Error occurred in isolated component but was handled gracefully."""

    def __init__(self, component: str, original_error: Exception, fallback_value: Any = None) -> None:
        """Initialize isolated error with context."""
        self.component = component
        self.original_error = original_error
        self.fallback_value = fallback_value
        super().__init__(f"Isolated error in {component}: {type(original_error).__name__}")


def isolate_errors(
    component: str,
    fallback: Any = None,
    log_traceback: bool = True,
):
    """
    Decorator for component-level error isolation.

    Catches exceptions in decorated function and prevents them from cascading.
    If a fallback is provided, returns its result instead of raising.

    Usage:
        @isolate_errors(component="knowledge_service", fallback=lambda: [])
        async def fetch_knowledge(query: str):
            # May fail, but won't halt agent
            return await kb.search(query)

    Args:
        component: Component name for logging and tracking
        fallback: Optional value or callable to return if primary fails
        log_traceback: Whether to log full traceback (default: True)

    Returns:
        Decorated function with error isolation
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        """Wrap function with error isolation."""
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                """Async wrapper with error isolation."""
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    logger.error(
                        "Error in isolated component %s.%s: %s",
                        component,
                        func.__name__,
                        type(e).__name__,
                        exc_info=log_traceback,
                    )

                    if fallback is not None:
                        if callable(fallback):
                            fallback_result = fallback()
                            # If fallback returns a coroutine, await it
                            if asyncio.iscoroutine(fallback_result):
                                fallback_result = await fallback_result
                        else:
                            fallback_result = fallback
                        logger.info(
                            "Using fallback for %s.%s",
                            component,
                            func.__name__,
                        )
                        return fallback_result

                    raise IsolatedError(component, e)

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                """Sync wrapper with error isolation."""
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.error(
                        "Error in isolated component %s.%s: %s",
                        component,
                        func.__name__,
                        type(e).__name__,
                        exc_info=log_traceback,
                    )

                    if fallback is not None:
                        fallback_result = fallback() if callable(fallback) else fallback
                        logger.info(
                            "Using fallback for %s.%s",
                            component,
                            func.__name__,
                        )
                        return fallback_result

                    raise IsolatedError(component, e)

            return sync_wrapper

    return decorator
