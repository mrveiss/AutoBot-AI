# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cache management package.

Provides unified cache coordination with memory-pressure-aware eviction.

Issue #743: Memory Optimization - Unified CacheCoordinator

Usage:
    from src.cache import get_cache_coordinator, register_all_caches

    # At application startup
    register_all_caches()

    # Get coordinator for stats/eviction
    coordinator = get_cache_coordinator()
    stats = coordinator.get_unified_stats()
"""

import logging

from .coordinator import CacheCoordinator, get_cache_coordinator
from .protocols import CacheProtocol

logger = logging.getLogger(__name__)

__all__ = [
    "CacheProtocol",
    "CacheCoordinator",
    "get_cache_coordinator",
    "register_all_caches",
]


def register_all_caches() -> int:
    """
    Register all known caches with the CacheCoordinator.

    Issue #743: Central registration function for coordinated cache management.

    This function should be called at application startup to enable
    memory-pressure-aware coordinated eviction across all caches.

    Returns:
        Number of caches successfully registered

    Example:
        from src.cache import register_all_caches
        count = register_all_caches()
        logger.info(f"Registered {count} caches with coordinator")
    """
    coordinator = get_cache_coordinator()
    registered = 0

    # LRU Memory Cache (src/memory/cache.py)
    try:
        from src.memory.cache import LRUCacheManager

        cache = LRUCacheManager()
        coordinator.register(cache)
        registered += 1
        logger.debug("Registered LRUCacheManager with CacheCoordinator")
    except Exception as e:
        logger.warning("Failed to register LRUCacheManager: %s", e)

    # Embedding Cache (src/knowledge/embedding_cache.py)
    try:
        from src.knowledge.embedding_cache import EmbeddingCache

        cache = EmbeddingCache()
        coordinator.register(cache)
        registered += 1
        logger.debug("Registered EmbeddingCache with CacheCoordinator")
    except Exception as e:
        logger.warning("Failed to register EmbeddingCache: %s", e)

    # LLM Response Cache (src/llm_interface_pkg/cache.py)
    try:
        from src.llm_interface_pkg.cache import LLMResponseCache

        cache = LLMResponseCache()
        coordinator.register(cache)
        registered += 1
        logger.debug("Registered LLMResponseCache with CacheCoordinator")
    except Exception as e:
        logger.warning("Failed to register LLMResponseCache: %s", e)

    # AST Cache (src/code_intelligence/shared/ast_cache.py)
    try:
        from src.code_intelligence.shared.ast_cache import ASTCache

        cache = ASTCache()
        coordinator.register(cache)
        registered += 1
        logger.debug("Registered ASTCache with CacheCoordinator")
    except Exception as e:
        logger.warning("Failed to register ASTCache: %s", e)

    # File List Cache (src/code_intelligence/shared/file_cache.py)
    try:
        from src.code_intelligence.shared.file_cache import FileListCache

        cache = FileListCache()
        coordinator.register(cache)
        registered += 1
        logger.debug("Registered FileListCache with CacheCoordinator")
    except Exception as e:
        logger.warning("Failed to register FileListCache: %s", e)

    logger.info(
        "CacheCoordinator: Registered %d caches for coordinated management", registered
    )
    return registered
