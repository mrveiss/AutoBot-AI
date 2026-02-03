# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Cache protocol definitions for coordinator integration."""

from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class CacheProtocol(Protocol):
    """
    Interface all caches must implement to register with CacheCoordinator.

    This protocol enables coordinated memory management across all cache types
    (L1 in-memory, L2 Redis, L3 SQLite).
    """

    @property
    def name(self) -> str:
        """Unique cache identifier (e.g., 'lru_memory', 'embedding', 'llm_l1')."""
        ...

    @property
    def size(self) -> int:
        """Current number of items in cache."""
        ...

    @property
    def max_size(self) -> int:
        """Maximum capacity (0 for unlimited)."""
        ...

    def evict(self, count: int) -> int:
        """
        Evict `count` oldest/least-used items from cache.

        Args:
            count: Number of items to evict

        Returns:
            Actual number of items evicted (may be less if cache is smaller)
        """
        ...

    def get_stats(self) -> Dict[str, Any]:
        """
        Return cache statistics.

        Returns:
            Dict with keys: size, max_size, hits, misses, hit_rate, etc.
        """
        ...

    def clear(self) -> None:
        """Clear all items from cache."""
        ...
