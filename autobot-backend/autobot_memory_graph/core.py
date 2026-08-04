# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Memory Graph - Core Module

This module contains the core base class, constants, and initialization logic
for the modular autobot_memory_graph package.

Part of Issue #716 - Refactored from monolithic autobot_memory_graph.py
"""

import asyncio
import inspect
from typing import Any, Dict, List, Set

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_management.types import DATABASE_MAPPING
from autobot_shared.ssot_config import config as _ssot_config

logger = get_logger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

ENTITY_TYPES: Set[str] = {
    "CONVERSATION",
    "BUG",
    "FEATURE",
    "DECISION",
    "TASK",
    "USER",  # Issue #608
    "SECRET",  # Issue #608
    "TERMINAL_ACTIVITY",  # Issue #608
    "FILE_ACTIVITY",  # Issue #608
    "BROWSER_ACTIVITY",  # Issue #608
    "DESKTOP_ACTIVITY",  # Issue #608
    "SECRET_USAGE",  # Issue #608
}

# ----------------------------------------------------------------------------
# Relation vocabulary (Issue #13452)
#
# CORE_RELATION_TYPES is the single canonical, domain-neutral relation
# vocabulary for the whole codebase. Every other relation store derives from
# it instead of restating its own list:
#   - autobot_memory_graph  -> RELATION_TYPES     (core + identity extras)
#   - knowledge.relations   -> KB_RELATION_TYPES  (core, fact-to-fact)
#   - api.schemas_knowledge -> RelationCreateRequest validator
#
# Before #13452 the memory graph spelled the general relation "related_to"
# while the knowledge base spelled it "relates_to", and neither accepted the
# other's spelling. create_relation() raises ValueError for unknown types and
# several callers swallow it, so every edge written with the wrong spelling
# was silently dropped (#13367 fixed one call site; the divergence itself is
# fixed here). "related_to" is canonical; "relates_to" survives only as a
# read/write alias in RELATION_TYPE_ALIASES so already-persisted Redis
# relations stay resolvable without a data migration.
# ----------------------------------------------------------------------------

CORE_RELATION_TYPES: Set[str] = {
    "contains",
    "depends_on",
    "implements",
    "references",
    "caused_by",
    "related_to",
    "leads_to",
    "blocks",
    # Document/issue-level names — previously knowledge-base-only, promoted to
    # the canonical set because agents.graph_entity_extractor infers them and
    # writes them straight into the memory graph.
    "fixes",
    "informs",
    "guides",
    "follows",
    "supersedes",
    "contradicts",
}

# Identity/activity relations — memory-graph only, meaningless between facts.
IDENTITY_RELATION_TYPES: Set[str] = {
    "owns",  # Issue #608 - User owns Secret
    "has_secret",  # Issue #608 - User/Session has Secret
    "shared_with",  # Issue #608 - Secret shared with User
    "has_participant",  # Issue #608 - Session has User
    "performed_by",  # Issue #608 - Activity performed by User
    "used_secret",  # Issue #608 - Activity used Secret
}

RELATION_TYPES: Set[str] = CORE_RELATION_TYPES | IDENTITY_RELATION_TYPES

# Legacy/alternate spellings mapped onto their canonical name. Callers are
# canonicalised on write, so no new relation is ever persisted under an alias,
# while relations already stored under one keep resolving.
RELATION_TYPE_ALIASES: Dict[str, str] = {
    "relates_to": "related_to",  # knowledge-base spelling before #13452
}


def canonical_relation_type(relation_type: str) -> str:
    """Return the canonical spelling for a relation type.

    Unknown names are returned unchanged so the caller's own validation still
    reports them, rather than this helper masking a genuine typo.

    Args:
        relation_type: Relation name as supplied by the caller.

    Returns:
        The canonical relation name.
    """
    return RELATION_TYPE_ALIASES.get(relation_type, relation_type)


def relation_type_matches(stored_type: str, wanted_type: str | None) -> bool:
    """Compare a stored relation type against a caller-supplied filter.

    Both sides are canonicalised, so relations persisted under a legacy
    spelling stay reachable through the canonical name and vice versa — reads
    and deletes therefore stay symmetric with writes, which canonicalise. An
    empty or absent filter matches everything.

    Args:
        stored_type: Relation type as read back from the store.
        wanted_type: Relation type the caller filtered on, or None/"" for any.

    Returns:
        True when the stored relation satisfies the filter.
    """
    if not wanted_type:
        return True
    return canonical_relation_type(stored_type) == canonical_relation_type(wanted_type)


def canonical_relation_filter(relation_types: List[str] | None) -> Set[str] | None:
    """Canonicalise a list-shaped relation filter once, for repeated matching.

    Args:
        relation_types: Relation names the caller filtered on, or None for any.

    Returns:
        A set of canonical names, or None when no filter was supplied.
    """
    if not relation_types:
        return None
    return {canonical_relation_type(rt) for rt in relation_types}


VALID_ACTIVITY_TYPES: Set[str] = {
    "chat",
    "terminal",
    "file_browser",
    "browser",
    "novnc",
}

# Relation direction constants
OUTGOING_DIRECTIONS: Set[str] = {"outgoing", "both"}
INCOMING_DIRECTIONS: Set[str] = {"incoming", "both"}


# ============================================================================
# CONFIGURATION
# ============================================================================


class Config:
    """Configuration for AutoBotMemoryGraph."""

    def __init__(self):
        self.redis_host = _ssot_config.vm.redis  # (#1148)
        self.redis_port = 6379
        self.redis_db = DATABASE_MAPPING["memory"]  # DB 0 — required for RediSearch FT.* (#9943)
        self.index_prefix = "autobot:entities"
        self.relations_prefix = "autobot:relations"
        self.embedding_model = "nomic-embed-text"
        self.embedding_dimensions = 768


config = Config()


# ============================================================================
# CORE BASE CLASS
# ============================================================================


class AutoBotMemoryGraphCore:
    """
    Core base class for AutoBotMemoryGraph.

    Provides initialization, configuration, and foundational methods
    that all mixin classes depend on.

    This class is not meant to be used directly. Instead, use the
    AutoBotMemoryGraph class which combines this core with all mixins.
    """

    def __init__(self, chat_history_manager: Any | None = None) -> None:
        """Initialize the memory graph core.

        Args:
            chat_history_manager: Optional ChatHistoryManager instance to wire in
                so memory graph mixins can read/write chat history. Restored in
                #6613 — the kwarg was lost in a refactor but
                ``chat_history/base.py`` still passes it.
        """
        self.redis_client: Any | None = None
        self.chat_history_manager: Any | None = chat_history_manager
        self.embedding_cache: Dict[str, List[float]] = {}
        self.embedding_model_name: str = config.embedding_model
        self.embedding_dimensions: int = config.embedding_dimensions
        self._initialized: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()
        self.index_name: str = f"{config.index_prefix}:idx"

    @property
    def initialized(self) -> bool:
        """Public readiness flag — True once ``initialize()`` has completed.

        Exposes the private ``_initialized`` state so callers (e.g. the
        Graph-RAG health probe, #12316) can read readiness without touching a
        private attribute or triggering ``AttributeError``.
        """
        return self._initialized

    def ensure_initialized(self) -> None:
        """Sync guard — raise if ``initialize()`` has not been awaited.

        Mixin methods call this before performing operations that require the
        Redis client and search index. Restored in #6613 — multiple call sites
        in user_session.py / property_graph_mixin.py / queries.py / relations.py
        rely on it but the method had been removed in a refactor.
        """
        if not self._initialized:
            raise RuntimeError("AutoBotMemoryGraph not initialized — call await initialize() first")

    async def initialize(self) -> bool:
        """
        Initialize Redis connection and search indexes.

        This method is idempotent and thread-safe.

        Returns:
            True once the graph is usable.

        #12873: this used to be declared ``-> None`` and returned nothing, but
        ``chat_history/base.py`` does ``initialized = await
        memory_graph.initialize()`` and then ``if initialized:``. A SUCCESSFUL
        init therefore returned None, which is falsy, so conversation entity
        tracking was disabled on every boot while the graph itself was fine —
        and nothing logged an error, because nothing had failed. That is why
        #12780's fix removed the visible errors without recovering the feature.
        """
        async with self._lock:
            if self._initialized:
                logger.debug("AutoBotMemoryGraph already initialized")
                return True

            try:
                # Initialize Redis client
                # RediSearch FT.CREATE only operates on Redis logical DB 0.
                # Both the FT indexes (memory_entity_idx, memory_fulltext_idx) and
                # the data keys (memory:entity:*, memory:relations:*) must live on
                # the same DB.  The "memory" alias maps to DB 0 for exactly this
                # purpose — see autobot_shared/redis_management/types.py _ALIASES.
                # Fixed by #9943 (same root cause as #9904).
                self.redis_client = await get_async_redis_client(database="memory")

                # Create search indexes if they don't exist
                await self._create_search_indexes()

                self._initialized = True
                logger.info("AutoBotMemoryGraph initialized successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to initialize AutoBotMemoryGraph: {e}")
                raise

    async def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        if self.redis_client:
            try:
                # redis-py's async client deprecated close() (which now returns
                # None) in favour of aclose(); awaiting the None return raised
                # "object NoneType can't be used in 'await' expression" on every
                # shutdown. Prefer aclose() and only await an awaitable result.
                closer = getattr(self.redis_client, "aclose", None) or self.redis_client.close
                result = closer()
                if inspect.isawaitable(result):
                    await result
                logger.info("AutoBotMemoryGraph closed successfully")
            except Exception as e:
                logger.error(f"Error closing AutoBotMemoryGraph: {e}")

        self._initialized = False
        self.embedding_cache.clear()

    async def _create_search_indexes(self) -> None:
        """
        Create the RediSearch FT indexes for entity/full-text search.

        Delegates to the canonical ``ensure_indexes`` coroutine in
        ``semantic_search`` (the single source of the FT.CREATE schema for
        ``memory_entity_idx`` / ``memory_fulltext_idx`` over ``memory:entity:*``
        JSON keys).  Without this call the production init path created no
        index, so FT.SEARCH always degraded to the slow SCAN fallback (#9943).

        Imported lazily because ``semantic_search`` imports from this module
        at import time (circular-import guard).

        Issue #665 / #9943: Helper for initialize().
        """
        from .semantic_search import ensure_indexes

        # ensure_indexes performs its own per-index existence check and swallows
        # creation errors with a warning, so initialization is never blocked.
        await ensure_indexes(self.redis_client)

    async def _check_index_exists(self, index_name: str) -> bool:
        """
        Check if a Redis search index exists.

        Issue #665: Helper for _create_search_indexes()

        Args:
            index_name: Name of the index to check

        Returns:
            True if index exists, False otherwise
        """
        try:
            if not self.redis_client:
                return False

            # Try to get index info
            # This is a simplified check
            info = await self.redis_client.execute_command("FT.INFO", index_name)
            return info is not None

        except Exception:
            # Index doesn't exist or error occurred
            return False


# ============================================================================
# PUBLIC EXPORTS
# ============================================================================

__all__ = [
    # Core class
    "AutoBotMemoryGraphCore",
    # Constants
    "ENTITY_TYPES",
    "CORE_RELATION_TYPES",
    "IDENTITY_RELATION_TYPES",
    "RELATION_TYPES",
    "RELATION_TYPE_ALIASES",
    "VALID_ACTIVITY_TYPES",
    "OUTGOING_DIRECTIONS",
    "INCOMING_DIRECTIONS",
    # Helpers
    "canonical_relation_type",
    "canonical_relation_filter",
    "relation_type_matches",
    # Config
    "config",
]
