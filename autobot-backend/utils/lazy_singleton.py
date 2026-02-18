# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Lazy Singleton Initialization - Standardized Pattern

This module provides utilities for lazy-initializing singleton objects on app state
or other storage mechanisms. Eliminates duplicate lazy initialization code across API files.

Usage:
    from utils.lazy_singleton import lazy_init_singleton

    def get_chat_history_manager(request):
        from chat_history import ChatHistoryManager
        return lazy_init_singleton(request.app.state, "chat_history_manager", ChatHistoryManager)
"""

import asyncio
import logging
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _create_and_store_instance(
    storage: Any,
    attribute_name: str,
    factory: Callable[..., T],
    *args,
    **kwargs,
) -> Optional[T]:
    """
    Create instance using factory and store on storage object.

    Helper function that handles the actual instance creation and storage.
    Extracted from lazy_init_singleton for Issue #620.

    Args:
        storage: Storage object to store singleton
        attribute_name: Name of attribute to store singleton under
        factory: Callable that creates the singleton
        *args: Positional arguments to pass to factory
        **kwargs: Keyword arguments to pass to factory

    Returns:
        The created instance, or None if creation failed
    """
    try:
        instance = factory(*args, **kwargs)
        setattr(storage, attribute_name, instance)
        logger.info("Lazy-initialized %s", attribute_name)
        return instance
    except Exception as e:
        logger.error("Failed to lazy-initialize %s: %s", attribute_name, e)
        return None


def _validate_existing_instance(
    instance: T,
    attribute_name: str,
    validator: Callable[[T], bool],
) -> bool:
    """
    Validate an existing singleton instance.

    Helper function that checks if an existing instance passes validation.
    Extracted from lazy_init_singleton_with_check for Issue #620.

    Args:
        instance: The instance to validate
        attribute_name: Name of the attribute (for logging)
        validator: Function that returns True if instance is valid

    Returns:
        True if instance is valid, False if invalid or validation failed
    """
    try:
        if not validator(instance):
            logger.warning(
                "Existing %s failed validation, re-initializing", attribute_name
            )
            return False
        return True
    except Exception as e:
        logger.warning(
            "Validation of existing %s failed: %s, re-initializing", attribute_name, e
        )
        return False


def _create_and_validate_instance(
    storage: Any,
    attribute_name: str,
    factory: Callable[..., T],
    validator: Optional[Callable[[T], bool]],
    *args,
    **kwargs,
) -> Optional[T]:
    """
    Create a new instance and optionally validate it before storing.

    Helper function that handles instance creation with validation.
    Extracted from lazy_init_singleton_with_check for Issue #620.

    Args:
        storage: Storage object to store singleton
        attribute_name: Name of attribute to store singleton under
        factory: Callable that creates the singleton
        validator: Optional function to validate the instance
        *args: Positional arguments to pass to factory
        **kwargs: Keyword arguments to pass to factory

    Returns:
        The validated instance, or None if creation/validation failed
    """
    try:
        instance = factory(*args, **kwargs)

        if validator is not None and not validator(instance):
            logger.error("Newly created %s failed validation", attribute_name)
            return None

        setattr(storage, attribute_name, instance)
        logger.info("Lazy-initialized %s (with validation)", attribute_name)
        return instance

    except Exception as e:
        logger.error("Failed to lazy-initialize %s: %s", attribute_name, e)
        return None


def lazy_init_singleton(
    storage: Any,
    attribute_name: str,
    factory: Callable[..., T],
    *args,
    **kwargs,
) -> Optional[T]:
    """
    Lazy-initialize a singleton object on a storage object (e.g., app.state).

    Args:
        storage: Storage object (e.g., request.app.state) to store singleton
        attribute_name: Name of attribute to store singleton under
        factory: Callable that creates the singleton (class or function)
        *args: Positional arguments to pass to factory
        **kwargs: Keyword arguments to pass to factory

    Returns:
        The singleton instance, or None if initialization failed

    Example:
        >>> manager = lazy_init_singleton(
        ...     request.app.state, "chat_history_manager", ChatHistoryManager
        ... )
    """
    instance = getattr(storage, attribute_name, None)
    if instance is not None:
        return instance

    return _create_and_store_instance(storage, attribute_name, factory, *args, **kwargs)


async def lazy_init_singleton_async(
    storage: Any,
    attribute_name: str,
    factory: Callable[..., T],
    *args,
    **kwargs,
) -> Optional[T]:
    """
    Async version of lazy_init_singleton for factories that return coroutines.

    Args:
        storage: Storage object (e.g., request.app.state) to store singleton
        attribute_name: Name of attribute to store singleton under
        factory: Async callable that creates the singleton
        *args: Positional arguments to pass to factory
        **kwargs: Keyword arguments to pass to factory

    Returns:
        The singleton instance, or None if initialization failed

    Example:
        >>> manager = await lazy_init_singleton_async(
        ...     request.app.state, "async_manager", AsyncManager
        ... )
    """
    instance = getattr(storage, attribute_name, None)
    if instance is not None:
        return instance

    try:
        result = factory(*args, **kwargs)
        instance = await result if asyncio.iscoroutine(result) else result
        setattr(storage, attribute_name, instance)
        logger.info("Lazy-initialized %s (async)", attribute_name)
        return instance
    except Exception as e:
        logger.error("Failed to lazy-initialize %s (async): %s", attribute_name, e)
        return None


def lazy_init_singleton_with_check(
    storage: Any,
    attribute_name: str,
    factory: Callable[..., T],
    validator: Optional[Callable[[T], bool]] = None,
    *args,
    **kwargs,
) -> Optional[T]:
    """
    Lazy-initialize singleton with optional validation check.

    This variant allows you to validate the instance before accepting it.
    Useful when the factory might return an invalid or uninitialized object.

    Args:
        storage: Storage object to store singleton
        attribute_name: Name of attribute to store singleton under
        factory: Callable that creates the singleton
        validator: Optional function to validate the instance (returns True if valid)
        *args: Positional arguments to pass to factory
        **kwargs: Keyword arguments to pass to factory

    Returns:
        The singleton instance, or None if initialization/validation failed

    Example:
        >>> def validate_service(svc):
        ...     return svc.is_initialized and svc.is_healthy()
        >>> service = lazy_init_singleton_with_check(
        ...     request.app.state, "validated_service", ServiceClass,
        ...     validator=validate_service
        ... )
    """
    instance = getattr(storage, attribute_name, None)

    # Check if existing instance is valid
    if instance is not None:
        if validator is None or _validate_existing_instance(
            instance, attribute_name, validator
        ):
            return instance
        instance = None  # Force re-initialization

    return _create_and_validate_instance(
        storage, attribute_name, factory, validator, *args, **kwargs
    )


def singleton_getter(attribute_name: str, factory: Callable):
    """
    Decorator to create a lazy singleton getter function.

    Args:
        attribute_name: Name of attribute on app.state
        factory: Factory callable to create the singleton

    Returns:
        Decorated function that performs lazy initialization

    Example:
        >>> @singleton_getter("chat_history_manager", ChatHistoryManager)
        ... def get_chat_history_manager(request):
        ...     from chat_history import ChatHistoryManager
        ...     return ChatHistoryManager
    """

    def decorator(func):
        """Create wrapper for lazy singleton initialization. Issue #620."""

        def wrapper(request, *args, **kwargs):
            """Execute function and lazily initialize singleton. Issue #620."""
            result = func(request, *args, **kwargs)
            actual_factory = (
                result if isinstance(result, type) or callable(result) else factory
            )
            return lazy_init_singleton(
                request.app.state, attribute_name, actual_factory, *args, **kwargs
            )

        return wrapper

    return decorator


class SingletonStorage:
    """
    Simple storage class for singletons when not using request.app.state.

    Useful for testing or when you need lazy singletons outside of a web framework.

    Example:
        >>> storage = SingletonStorage()
        >>> manager = lazy_init_singleton(storage, "manager", ManagerClass)
    """


_global_singleton_storage = SingletonStorage()


def global_lazy_singleton(
    attribute_name: str, factory: Callable[..., T], *args, **kwargs
) -> Optional[T]:
    """
    Lazy-initialize a global singleton (module-level).

    Use sparingly - prefer request.app.state for web applications.

    Args:
        attribute_name: Name to store singleton under
        factory: Factory to create singleton
        *args: Arguments to pass to factory
        **kwargs: Keyword arguments to pass to factory

    Returns:
        The singleton instance

    Example:
        >>> service = global_lazy_singleton("my_service", MyService)
    """
    return lazy_init_singleton(
        _global_singleton_storage, attribute_name, factory, *args, **kwargs
    )
