# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
FastAPI Dependency Injection Module

This module provides dependency injection functions for FastAPI endpoints,
removing the need for components to directly import and use global_config_manager.
"""

import threading

from fastapi import Depends, Request

from config.manager import ConfigManager, get_config_manager


def provide_config_manager() -> ConfigManager:
    """
    Dependency injection provider for configuration.

    Returns the application-wide singleton ConfigManager so that route
    handlers can receive it via ``Depends(provide_config_manager)`` instead of
    importing ``global_config_manager`` directly.  Tests can override
    this dependency with ``app.dependency_overrides[provide_config_manager]``.

    Returns:
        ConfigManager: The global configuration manager singleton
    """
    return get_config_manager()


def get_diagnostics(config: ConfigManager = Depends(provide_config_manager)):
    """
    Dependency injection provider for diagnostics.

    Args:
        config: Configuration manager instance

    Returns:
        Diagnostics: Diagnostics instance configured with the provided config
    """
    from diagnostics import Diagnostics

    return Diagnostics(config_manager=config)


async def get_knowledge_base(request: Request):
    """Dependency injection provider for the knowledge base.

    Returns the app-wide *initialized* instance — the same object every
    ``api/knowledge*.py`` route reaches through
    ``knowledge_factory.get_or_create_knowledge_base`` — rather than constructing one
    per request.

    #18121: this provider used to be synchronous and return
    ``KnowledgeBase(config_manager=config)``. ``KnowledgeBaseCore.initialize()`` is what
    creates the vector store and must be awaited after construction, which a sync
    dependency can never do, so every injected instance had ``initialized is False`` and
    the first search raised ``RuntimeError`` out of ``ensure_initialized()``. All eight
    call sites catch ``Exception`` into a warning and substitute an empty result, so the
    knowledge base silently contributed nothing instead of failing visibly.

    The dropped ``config`` parameter does not regress #13162: that fix stopped a resolved
    config being accepted and discarded, and the app-state instance is built once at
    lifespan from the real config rather than per request.

    Returns:
        The initialized ``KnowledgeBase``, or ``None`` when it is unavailable — every
        caller already treats ``None`` as "no knowledge base".
    """
    from knowledge_factory import get_or_create_knowledge_base

    return await get_or_create_knowledge_base(request.app)


def get_llm_interface(config: ConfigManager = Depends(provide_config_manager)):
    """
    Dependency injection provider for the LLM service.

    The function name is retained for back-compat with any FastAPI route that
    references ``LLMInterfaceDep`` below; the returned instance is now an
    ``LLMService`` (the canonical post-#3185 successor to LLMInterface).

    Args:
        config: Configuration manager instance

    Returns:
        LLMService: shared singleton instance.
    """
    # #6983: migrated from LLMInterface() to LLMService singleton (#3185 missed this caller)
    from services.llm_service import get_llm_service

    return get_llm_service()


def get_orchestrator(
    config: ConfigManager = Depends(provide_config_manager),
):
    """
    Lazy loading dependency injection provider for orchestrator.

    Args:
        config: Configuration manager instance

    Returns:
        Orchestrator: instance configured with the provided config manager.
    """
    # Lazy import to reduce startup time
    from orchestrator import Orchestrator

    # #13162: the constructor parameter is now named for the attribute it sets
    # (``config_manager``), so this provider and get_cached_orchestrator below
    # finally agree with it. Orchestrator self-instantiates the collaborators
    # this provider does not supply.
    return Orchestrator(config_manager=config)


def get_security_layer(config: ConfigManager = Depends(provide_config_manager)):
    """
    Dependency injection provider for security layer.

    Args:
        config: Configuration manager instance

    Returns:
        SecurityLayer | None: Security layer instance if enabled, None otherwise
    """
    try:
        from security_layer import SecurityLayer

        return SecurityLayer()
    except Exception:
        return None


# Utility functions for dependency injection patterns
class DependencyCache:
    """
    Simple cache for expensive-to-create dependencies.

    This can be used to ensure that expensive objects like
    knowledge bases or orchestrators are created only once
    per request context.
    """

    def __init__(self):
        """Initialize dependency cache with empty storage and thread lock."""
        self._cache = {}
        self._lock = threading.Lock()  # CRITICAL: Protect concurrent cache access

    def get_or_create(self, key: str, factory_fn):
        """Get cached instance or create new one using factory function."""
        # CRITICAL: Atomic check-and-create with lock to prevent race conditions
        with self._lock:
            if key not in self._cache:
                self._cache[key] = factory_fn()
            return self._cache[key]

    def clear(self):
        """Clear the cache."""
        with self._lock:
            self._cache.clear()


# Global cache instance (could be request-scoped in the future)
dependency_cache = DependencyCache()


async def get_cached_knowledge_base(request: Request):
    """Cached knowledge base dependency.

    #18121: delegates to :func:`get_knowledge_base`. ``app.state.knowledge_base`` already
    is the cache — ``get_or_create_knowledge_base`` returns the existing instance when one
    is initialized — so a second ``dependency_cache`` entry only created a second
    uninitialized instance to go stale. Kept as a wired name so
    ``CachedKnowledgeBaseDep`` cannot reintroduce the defect.
    """
    return await get_knowledge_base(request)


def get_cached_orchestrator(config: ConfigManager = Depends(provide_config_manager)):
    """
    Cached version of orchestrator dependency with lazy loading.

    This version caches the orchestrator instance to avoid
    repeated initialization costs and uses lazy import.

    Args:
        config: Configuration manager instance

    Returns:
        Orchestrator: Cached orchestrator instance
    """

    # Lazy import inside cache function to defer loading
    def _create_orchestrator():
        """Create orchestrator instance with configuration manager."""
        from orchestrator import Orchestrator

        return Orchestrator(config_manager=config)

    return dependency_cache.get_or_create("orchestrator", _create_orchestrator)


async def get_async_redis_client(database: str = "main"):
    """
    Dependency injection provider for async Redis client.

    Issue #666: Added async version to avoid blocking I/O in async contexts.

    Args:
        database: Named database for logical separation. Default: "main"

    Returns:
        Async Redis client instance
    """
    from autobot_shared.redis_client import get_async_redis_client as _get_async_redis_client

    return await _get_async_redis_client(database=database)


# Type aliases for cleaner dependency annotations
ConfigDep = Depends(provide_config_manager)
DiagnosticsDep = Depends(get_diagnostics)
KnowledgeBaseDep = Depends(get_knowledge_base)
LLMInterfaceDep = Depends(get_llm_interface)
OrchestratorDep = Depends(get_orchestrator)
SecurityLayerDep = Depends(get_security_layer)

# Cached versions
CachedKnowledgeBaseDep = Depends(get_cached_knowledge_base)
CachedOrchestratorDep = Depends(get_cached_orchestrator)
