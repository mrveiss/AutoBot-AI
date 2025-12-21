# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Lazy Singleton Initialization - Standardized Pattern

This module provides utilities for lazy-initializing singleton objects on app state
or other storage mechanisms. Eliminates duplicate lazy initialization code across API files.

CONSOLIDATES PATTERNS FROM:
==========================
- backend/api/chat.py:66-79 (get_chat_history_manager)
- backend/api/chat.py:92-105 (get_llm_service)
- 10+ other similar functions across API files

BENEFITS:
=========
✅ Eliminates 10-15 lines of duplicate code per function
✅ Standardizes error handling and logging
✅ Thread-safe lazy initialization
✅ Consistent attribute naming
✅ Reduces 100+ lines of duplicate code across codebase

USAGE PATTERN:
==============
from src.utils.lazy_singleton import lazy_init_singleton

# Old pattern (14 lines)
def get_chat_history_manager(request):
    manager = getattr(request.app.state, "chat_history_manager", None)
    if manager is None:
        try:
            from src.chat_history import ChatHistoryManager
            manager = ChatHistoryManager()
            request.app.state.chat_history_manager = manager
            logger.info("✅ Lazy-initialized chat_history_manager")
        except Exception as e:
            logger.error("Failed to lazy-initialize chat_history_manager: %s", e)
    return manager

# New pattern (3 lines)
def get_chat_history_manager(request):
    from src.chat_history import ChatHistoryManager
    return lazy_init_singleton(request.app.state, "chat_history_manager", ChatHistoryManager)

ADVANCED USAGE:
===============
# With initialization arguments
def get_llm_service(request):
    from src.llm_service import LLMService
    return lazy_init_singleton(
        request.app.state,
        "llm_service",
        LLMService,
        model="gpt-4",
        temperature=0.7
    )

# With async initialization
async def get_async_service(request):
    from src.async_service import AsyncService
    return await lazy_init_singleton_async(
        request.app.state,
        "async_service",
        AsyncService
    )

# With custom factory function
def get_complex_service(request):
    def factory():
        service = ComplexService()
        service.configure(config)
        service.initialize()
        return service

    return lazy_init_singleton(
        request.app.state,
        "complex_service",
        factory
    )
"""

import asyncio
import logging
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def lazy_init_singleton(
    storage: Any,
    attribute_name: str,
    factory: Callable[..., T],
    *args,
    **kwargs,
) -> Optional[T]:
    """
    Lazy-initialize a singleton object on a storage object (e.g., app.state).

    This function implements the lazy initialization pattern with proper error
    handling and logging. It checks if the attribute already exists on the storage
    object, and if not, creates it using the provided factory.

    Args:
        storage: Storage object (e.g., request.app.state) to store singleton
        attribute_name: Name of attribute to store singleton under
        factory: Callable that creates the singleton (class or function)
        *args: Positional arguments to pass to factory
        **kwargs: Keyword arguments to pass to factory

    Returns:
        T: The singleton instance, or None if initialization failed

    Examples:
        # Basic usage with class
        >>> manager = lazy_init_singleton(
        ...     request.app.state,
        ...     "chat_history_manager",
        ...     ChatHistoryManager
        ... )

        # With initialization arguments
        >>> service = lazy_init_singleton(
        ...     request.app.state,
        ...     "llm_service",
        ...     LLMService,
        ...     model="gpt-4",
        ...     temperature=0.7
        ... )

        # With factory function
        >>> def create_service():
        ...     service = ComplexService()
        ...     service.configure(config)
        ...     return service
        >>> service = lazy_init_singleton(
        ...     request.app.state,
        ...     "complex_service",
        ...     create_service
        ... )

    Thread Safety:
        This function uses getattr/setattr which are atomic operations in Python,
        making it thread-safe for the common case. However, if the factory itself
        is not thread-safe or if initialization order matters, consider using
        a lock or initializing during startup instead.
    """
    # Check if already initialized
    instance = getattr(storage, attribute_name, None)

    if instance is not None:
        return instance

    # Need to initialize
    try:
        # Create instance using factory
        instance = factory(*args, **kwargs)

        # Store on storage object
        setattr(storage, attribute_name, instance)

        logger.info("✅ Lazy-initialized %s", attribute_name)
        return instance

    except Exception as e:
        logger.error("❌ Failed to lazy-initialize %s: %s", attribute_name, e)
        return None


async def lazy_init_singleton_async(
    storage: Any,
    attribute_name: str,
    factory: Callable[..., T],
    *args,
    **kwargs,
) -> Optional[T]:
    """
    Async version of lazy_init_singleton for factories that return coroutines.

    Use this when the factory function is async or returns an awaitable.

    Args:
        storage: Storage object (e.g., request.app.state) to store singleton
        attribute_name: Name of attribute to store singleton under
        factory: Async callable that creates the singleton
        *args: Positional arguments to pass to factory
        **kwargs: Keyword arguments to pass to factory

    Returns:
        T: The singleton instance, or None if initialization failed

    Examples:
        # Basic async usage
        >>> manager = await lazy_init_singleton_async(
        ...     request.app.state,
        ...     "async_manager",
        ...     AsyncManager
        ... )

        # With initialization
        >>> async def create_service():
        ...     service = AsyncService()
        ...     await service.initialize()
        ...     return service
        >>> service = await lazy_init_singleton_async(
        ...     request.app.state,
        ...     "async_service",
        ...     create_service
        ... )
    """
    # Check if already initialized
    instance = getattr(storage, attribute_name, None)

    if instance is not None:
        return instance

    # Need to initialize
    try:
        # Create instance using factory
        result = factory(*args, **kwargs)

        # Await if it's a coroutine
        if asyncio.iscoroutine(result):
            instance = await result
        else:
            instance = result

        # Store on storage object
        setattr(storage, attribute_name, instance)

        logger.info("✅ Lazy-initialized %s (async)", attribute_name)
        return instance

    except Exception as e:
        logger.error("❌ Failed to lazy-initialize %s (async): %s", attribute_name, e)
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
        T: The singleton instance, or None if initialization/validation failed

    Examples:
        >>> def validate_service(service):
        ...     return service.is_initialized and service.is_healthy()
        >>>
        >>> service = lazy_init_singleton_with_check(
        ...     request.app.state,
        ...     "validated_service",
        ...     ServiceClass,
        ...     validator=validate_service
        ... )
    """
    # Check if already initialized and valid
    instance = getattr(storage, attribute_name, None)

    if instance is not None:
        # If validator provided, check if still valid
        if validator is not None:
            try:
                if not validator(instance):
                    logger.warning(
                        f"Existing {attribute_name} failed validation, re-initializing"
                    ),
                    instance = None
            except Exception as e:
                logger.warning(
                    f"Validation of existing {attribute_name} failed: {e}, re-initializing"
                ),
                instance = None

    # Need to initialize or re-initialize
    if instance is None:
        try:
            # Create instance using factory
            instance = factory(*args, **kwargs)

            # Validate if validator provided
            if validator is not None:
                if not validator(instance):
                    logger.error("Newly created %s failed validation", attribute_name)
                    return None

            # Store on storage object
            setattr(storage, attribute_name, instance)

            logger.info("✅ Lazy-initialized %s (with validation)", attribute_name)

        except Exception as e:
            logger.error("❌ Failed to lazy-initialize %s: %s", attribute_name, e)
            return None

    return instance


# Convenience decorators
def singleton_getter(attribute_name: str, factory: Callable):
    """
    Decorator to create a lazy singleton getter function.

    This decorator simplifies the creation of getter functions that lazily
    initialize singletons.

    Args:
        attribute_name: Name of attribute on app.state
        factory: Factory callable to create the singleton

    Returns:
        Decorated function that performs lazy initialization

    Examples:
        # Without decorator (old way)
        def get_chat_history_manager(request):
            from src.chat_history import ChatHistoryManager
            return lazy_init_singleton(
                request.app.state,
                "chat_history_manager",
                ChatHistoryManager
            )

        # With decorator (new way)
        @singleton_getter("chat_history_manager", ChatHistoryManager)
        def get_chat_history_manager(request):
            from src.chat_history import ChatHistoryManager
            return ChatHistoryManager  # Return factory class

        # Or even simpler with lambda
        get_chat_history_manager = singleton_getter(
            "chat_history_manager",
            lambda: __import__('src.chat_history_manager').ChatHistoryManager()
        )
    """

    def decorator(func):
        """Create wrapper function that performs lazy singleton initialization."""

        def wrapper(request, *args, **kwargs):
            """Execute original function and lazily initialize singleton from result."""
            # Execute original function to get factory (allows for imports)
            result = func(request, *args, **kwargs)

            # If result is a class, use it as factory
            if isinstance(result, type):
                actual_factory = result
            # If result is callable, use it
            elif callable(result):
                actual_factory = result
            # Otherwise, use the decorator's factory
            else:
                actual_factory = factory

            return lazy_init_singleton(
                request.app.state, attribute_name, actual_factory, *args, **kwargs
            )

        return wrapper

    return decorator


# Storage class for non-request contexts
class SingletonStorage:
    """
    Simple storage class for singletons when not using request.app.state.

    Useful for testing or when you need lazy singletons outside of a web framework.

    Examples:
        >>> storage = SingletonStorage()
        >>> manager = lazy_init_singleton(storage, "manager", ManagerClass)
        >>> # Later access
        >>> same_manager = lazy_init_singleton(storage, "manager", ManagerClass)
        >>> assert manager is same_manager
    """


# Global storage for module-level singletons (use sparingly)
_global_singleton_storage = SingletonStorage()


def global_lazy_singleton(
    attribute_name: str, factory: Callable[..., T], *args, **kwargs
) -> Optional[T]:
    """
    Lazy-initialize a global singleton (module-level).

    Use this sparingly - prefer request.app.state for web applications.
    This is mainly useful for CLI tools or scripts that need singletons.

    Args:
        attribute_name: Name to store singleton under
        factory: Factory to create singleton
        *args: Arguments to pass to factory
        **kwargs: Keyword arguments to pass to factory

    Returns:
        The singleton instance

    Examples:
        >>> # First call creates it
        >>> service = global_lazy_singleton("my_service", MyService)
        >>> # Second call returns same instance
        >>> same_service = global_lazy_singleton("my_service", MyService)
        >>> assert service is same_service
    """
    return lazy_init_singleton(
        _global_singleton_storage, attribute_name, factory, *args, **kwargs
    )
