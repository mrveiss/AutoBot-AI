# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Backward Compatibility Wrappers - Drop-in replacements for legacy APIs

#10572: EnhancedMemoryManager subclass removed — all sync convenience
methods (create_task_record, start_task, complete_task, fail_task,
fail_task, log_task_execution, get_task_history_sync, add_markdown_reference,
_get_embedding_cache_size, cleanup_old_data) now live on UnifiedMemoryManager
directly.  get_enhanced_memory_manager() is retained as an alias so
existing call-sites that import it by name continue to work unchanged;
it now returns a plain UnifiedMemoryManager instance.
"""

from typing import Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton

from .enums import MemoryCategory
from .manager import UnifiedMemoryManager
from .models import MemoryEntry

logger = get_logger(__name__)


class LongTermMemoryManager:
    """Backward compatibility wrapper for memory_manager.py."""

    def __init__(self, config_path: str | None = None, db_path: str = "data/agent_memory.db"):
        """
        Initialize with memory_manager.py defaults

        Args:
            config_path: Legacy parameter (ignored, kept for backward compatibility)
            db_path: Path to SQLite database (default: "data/agent_memory.db")
        """
        self._unified = UnifiedMemoryManager(
            db_path=db_path,
            enable_cache=True,
            enable_monitoring=False,
            retention_days=90,
        )
        logger.info("LongTermMemoryManager compatibility wrapper initialized at %s", db_path)

    async def store_memory(
        self,
        category: str,
        content: str,
        metadata: Dict | None = None,
        embedding: bytes | None = None,
    ) -> int:
        """Map old API to new unified API"""
        # Convert string category to enum if possible
        try:
            cat = MemoryCategory[category.upper()]
        except (KeyError, AttributeError):
            cat = category  # Use as-is if not in enum

        return await self._unified.store_memory(cat, content, metadata, embedding=embedding)

    async def retrieve_memories(
        self, category: str, filters: Dict | None = None, limit: int = 100
    ) -> List[MemoryEntry]:
        """Map old API to new unified API"""
        filters = filters or {}

        try:
            cat = MemoryCategory[category.upper()]
        except (KeyError, AttributeError):
            cat = category

        return await self._unified.retrieve_memories(
            cat,
            limit=limit,
            start_date=filters.get("start_date"),
            end_date=filters.get("end_date"),
            reference_path=filters.get("reference_path"),
        )

    async def search_by_metadata(self, metadata_query: Dict) -> List[MemoryEntry]:
        """
        Search by metadata (limited implementation).

        WARNING: This is a limited implementation that converts metadata values
        to a text search query. It does NOT perform true metadata key/value matching.
        Results may include false positives if content happens to contain the
        metadata values as text.

        Args:
            metadata_query: Dictionary of metadata key/value pairs to search for

        Returns:
            List of MemoryEntry where content matches the search query
        """
        # Convert to content search (limited - does not do true metadata matching)
        query = " ".join(str(v) for v in metadata_query.values())
        return await self._unified.search_memories(query)

    async def initialize(self) -> None:
        """Initialize the underlying storage (called by orchestrator on startup)."""
        await self._unified._ensure_initialized()
        logger.info("LongTermMemoryManager initialized")

    async def cleanup(self) -> None:
        """Cleanup hook called by orchestrator on shutdown (no-op: no resources to release)."""
        logger.info("LongTermMemoryManager cleanup complete")

    async def search_relevant_context(self, query: str) -> List[MemoryEntry]:
        """Search memories for context relevant to the given query."""
        return await self._unified.search_memories(query)

    async def cleanup_old_memories(self, retention_days: int | None = None) -> int:
        """Cleanup old memories"""
        return await self._unified.cleanup_old_memories(retention_days)


# ============================================================================
# GLOBAL INSTANCES (for drop-in replacement)
# get_enhanced_memory_manager retained for call-site backward compatibility;
# now returns a plain UnifiedMemoryManager instance (#10572).
# ============================================================================

get_enhanced_memory_manager = lazy_singleton(UnifiedMemoryManager)
get_long_term_memory_manager = lazy_singleton(LongTermMemoryManager)


__all__ = [
    "LongTermMemoryManager",
    "get_enhanced_memory_manager",
    "get_long_term_memory_manager",
]
