# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cache management package.

Provides unified cache coordination with memory-pressure-aware eviction.

Issue #743: Memory Optimization - Unified CacheCoordinator

Usage:
    from cache import get_cache_coordinator, register_all_caches

    # At application startup
    register_all_caches()

    # Get coordinator for stats/eviction
    coordinator = get_cache_coordinator()
    stats = coordinator.get_unified_stats()
"""

import logging
from typing import Callable, List, Tuple

from .coordinator import CacheCoordinator, get_cache_coordinator
from .protocols import CacheProtocol

logger = logging.getLogger(__name__)

__all__ = [
    "CacheProtocol",
    "CacheCoordinator",
    "get_cache_coordinator",
    "register_all_caches",
]


def _get_cache_registry() -> List[Tuple[str, str, Callable[[], CacheProtocol]]]:
    """
    Return the list of cache classes to register with the coordinator.

    Each entry is a tuple of (module_path, class_name, factory_function).
    Extracted from register_all_caches for maintainability. Issue #620.

    Returns:
        List of tuples containing module path, class name, and factory function.
    """

    def _lru_cache_factory() -> CacheProtocol:
        from memory.cache import LRUCacheManager

        return LRUCacheManager()

    def _embedding_cache_factory() -> CacheProtocol:
        from knowledge.embedding_cache import EmbeddingCache

        return EmbeddingCache()

    def _llm_cache_factory() -> CacheProtocol:
        from llm_interface_pkg.cache import LLMResponseCache

        return LLMResponseCache()

    def _ast_cache_factory() -> CacheProtocol:
        from code_intelligence.shared.ast_cache import ASTCache

        return ASTCache()

    def _file_cache_factory() -> CacheProtocol:
        from code_intelligence.shared.file_cache import FileListCache

        return FileListCache()

    return [
        ("src.memory.cache", "LRUCacheManager", _lru_cache_factory),
        ("src.knowledge.embedding_cache", "EmbeddingCache", _embedding_cache_factory),
        ("src.llm_interface_pkg.cache", "LLMResponseCache", _llm_cache_factory),
        ("src.code_intelligence.shared.ast_cache", "ASTCache", _ast_cache_factory),
        (
            "src.code_intelligence.shared.file_cache",
            "FileListCache",
            _file_cache_factory,
        ),
    ]


def _register_single_cache(
    coordinator: CacheCoordinator,
    module_path: str,
    class_name: str,
    factory: Callable[[], CacheProtocol],
) -> bool:
    """
    Register a single cache instance with the coordinator.

    Handles import errors and registration failures gracefully.
    Extracted from register_all_caches for maintainability. Issue #620.

    Args:
        coordinator: The CacheCoordinator instance to register with.
        module_path: The module path for logging purposes.
        class_name: The class name for logging purposes.
        factory: A callable that creates the cache instance.

    Returns:
        True if registration succeeded, False otherwise.
    """
    try:
        cache = factory()
        coordinator.register(cache)
        logger.debug("Registered %s with CacheCoordinator", class_name)
        return True
    except Exception as e:
        logger.warning("Failed to register %s: %s", class_name, e)
        return False


def register_all_caches() -> int:
    """
    Register all known caches with the CacheCoordinator.

    Issue #743: Central registration function for coordinated cache management.

    This function should be called at application startup to enable
    memory-pressure-aware coordinated eviction across all caches.

    Returns:
        Number of caches successfully registered

    Example:
        from cache import register_all_caches
        count = register_all_caches()
        logger.info(f"Registered {count} caches with coordinator")
    """
    coordinator = get_cache_coordinator()
    registered = 0

    for module_path, class_name, factory in _get_cache_registry():
        if _register_single_cache(coordinator, module_path, class_name, factory):
            registered += 1

    logger.info(
        "CacheCoordinator: Registered %d caches for coordinated management", registered
    )
    return registered
