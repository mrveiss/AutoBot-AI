# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
FastAPI Dependency Injection Module

This module provides dependency injection functions for FastAPI endpoints,
removing the need for components to directly import and use global_config_manager.
"""

import threading

from config import ConfigManager
from fastapi import Depends

global_config_manager = ConfigManager()


def get_config() -> ConfigManager:
    """
    Dependency injection provider for configuration.

    This function provides access to the configuration manager
    without requiring direct imports of global_config_manager.

    Returns:
        ConfigManager: The global configuration manager instance
    """
    return global_config_manager


def get_diagnostics(config: ConfigManager = Depends(get_config)):
    """
    Dependency injection provider for diagnostics.

    Args:
        config: Configuration manager instance

    Returns:
        Diagnostics: Diagnostics instance configured with the provided config
    """
    from diagnostics import Diagnostics

    return Diagnostics(config_manager=config)


def get_knowledge_base(config: ConfigManager = Depends(get_config)):
    """
    Dependency injection provider for knowledge base.

    Args:
        config: Configuration manager instance

    Returns:
        KnowledgeBase: Knowledge base instance configured with the provided config
    """
    from knowledge_base import KnowledgeBase as KnowledgeBase

    return KnowledgeBase()


def get_llm_interface(config: ConfigManager = Depends(get_config)):
    """
    Dependency injection provider for LLM interface.

    Args:
        config: Configuration manager instance

    Returns:
        LLMInterface: LLM interface instance configured with the provided config
    """
    from llm_interface import LLMInterface

    return LLMInterface()


def get_orchestrator(
    config: ConfigManager = Depends(get_config),
    llm_interface=Depends(get_llm_interface),
    knowledge_base=Depends(get_knowledge_base),
    diagnostics=Depends(get_diagnostics),
):
    """
    Lazy loading dependency injection provider for orchestrator.

    Args:
        config: Configuration manager instance
        llm_interface: LLM interface instance
        knowledge_base: Knowledge base instance
        diagnostics: Diagnostics instance

    Returns:
        Orchestrator: Orchestrator instance configured with all dependencies
    """
    # Lazy import to reduce startup time
    from orchestrator import Orchestrator

    return Orchestrator(
        config_manager=config,
        llm_interface=llm_interface,
        knowledge_base=knowledge_base,
        diagnostics=diagnostics,
    )


def get_security_layer(config: ConfigManager = Depends(get_config)):
    """
    Dependency injection provider for security layer.

    Args:
        config: Configuration manager instance

    Returns:
        Optional[SecurityLayer]: Security layer instance if enabled, None otherwise
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


def get_cached_knowledge_base(config: ConfigManager = Depends(get_config)):
    """
    Cached version of knowledge base dependency.

    This version caches the knowledge base instance to avoid
    repeated initialization costs.

    Args:
        config: Configuration manager instance

    Returns:
        KnowledgeBase: Cached knowledge base instance
    """
    from knowledge_base import KnowledgeBase as KnowledgeBase

    return dependency_cache.get_or_create("knowledge_base", lambda: KnowledgeBase())


def get_cached_orchestrator(config: ConfigManager = Depends(get_config)):
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


def get_redis_client():
    """
    Dependency injection provider for Redis client (synchronous).

    Returns:
        Redis client instance (sync)
    """
    from autobot_shared.redis_client import get_redis_client as _get_redis_client

    return _get_redis_client()


async def get_async_redis_client(database: str = "main"):
    """
    Dependency injection provider for async Redis client.

    Issue #666: Added async version to avoid blocking I/O in async contexts.

    Args:
        database: Named database for logical separation. Default: "main"

    Returns:
        Async Redis client instance
    """
    from autobot_shared.redis_client import get_redis_client as _get_redis_client

    return await _get_redis_client(async_client=True, database=database)


# Type aliases for cleaner dependency annotations
ConfigDep = Depends(get_config)
DiagnosticsDep = Depends(get_diagnostics)
KnowledgeBaseDep = Depends(get_knowledge_base)
LLMInterfaceDep = Depends(get_llm_interface)
OrchestratorDep = Depends(get_orchestrator)
SecurityLayerDep = Depends(get_security_layer)
RedisClientDep = Depends(get_redis_client)

# Cached versions
CachedKnowledgeBaseDep = Depends(get_cached_knowledge_base)
CachedOrchestratorDep = Depends(get_cached_orchestrator)
