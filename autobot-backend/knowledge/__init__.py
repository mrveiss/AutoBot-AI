# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Package

Modular knowledge base implementation composed of specialized mixins.

This package provides a unified KnowledgeBase class that inherits functionality
from multiple focused mixins:
- KnowledgeBaseCore: Initialization, configuration, connections
- StatsMixin: Atomic stats tracking and performance monitoring
- IndexMixin: ChromaDB index management and rebuild operations
- SearchMixin: Semantic, keyword, and hybrid search
- FactsMixin: CRUD operations for individual facts
- DocumentsMixin: Document processing and ingestion
- TagsMixin: Tag management and filtering
- CategoriesMixin: Hierarchical category tree structure
- CollectionsMixin: Collections/folders for grouping documents
- SuggestionsMixin: ML-based tag and category suggestions (Issue #413)
- MetadataMixin: Custom metadata templates and validation (Issue #414)
- VersioningMixin: Fact version history and reversion (Issue #414)
- BulkOperationsMixin: Import, export, and bulk operations

Usage:
    from knowledge import get_knowledge_base

    # Get initialized instance
    kb = await get_knowledge_base()

    # Search
    results = await kb.search("Python security")

    # Store fact
    result = await kb.store_fact("Content", {"category": "general"})
"""

import asyncio
import logging
import threading
from typing import Optional

from knowledge.base import KnowledgeBaseCore
from knowledge.bulk import BulkOperationsMixin
from knowledge.categories import CategoriesMixin
from knowledge.collections import CollectionsMixin
from knowledge.documents import DocumentsMixin
from knowledge.facts import FactsMixin
from knowledge.index import IndexMixin
from knowledge.metadata import MetadataMixin
from knowledge.search import SearchMixin
from knowledge.stats import StatsMixin
from knowledge.suggestions import SuggestionsMixin
from knowledge.tags import TagsMixin
from knowledge.versioning import VersioningMixin

logger = logging.getLogger(__name__)


class KnowledgeBase(
    KnowledgeBaseCore,
    StatsMixin,
    IndexMixin,
    SearchMixin,
    FactsMixin,
    DocumentsMixin,
    TagsMixin,
    CategoriesMixin,
    CollectionsMixin,
    SuggestionsMixin,
    MetadataMixin,
    VersioningMixin,
    BulkOperationsMixin,
):
    """
    Unified Knowledge Base implementation.

    This class composes all knowledge base functionality through multiple mixins,
    providing a complete API for:
    - Fact storage and retrieval
    - Semantic and keyword search
    - Document processing
    - Tag management
    - Bulk operations
    - Statistics and monitoring
    - Index management

    The class uses Method Resolution Order (MRO) to properly inherit from all mixins,
    with KnowledgeBaseCore providing the base initialization and configuration.

    Example:
        kb = KnowledgeBase()
        await kb.initialize()

        # Store a fact
        result = await kb.store_fact(
            "Python uses indentation for blocks",
            metadata={"category": "programming", "tags": ["python", "syntax"]}
        )

        # Search
        results = await kb.search("Python syntax", top_k=5)

        # Get stats
        stats = await kb.get_stats()
    """

    def __init__(self):
        """
        Initialize the composed knowledge base.

        This calls the base __init__ from KnowledgeBaseCore which sets up
        all instance variables that are shared across mixins.
        """
        super().__init__()
        logger.debug("KnowledgeBase instance created (composed from 13 mixins)")

    async def initialize(self) -> bool:
        """
        Initialize the knowledge base asynchronously.

        This is the main initialization method that must be called after construction.
        It delegates to KnowledgeBaseCore.initialize() which handles:
        - Redis connection setup
        - LlamaIndex configuration
        - ChromaDB vector store initialization
        - Stats counter initialization

        Returns:
            bool: True if initialization succeeds, False otherwise

        Example:
            kb = KnowledgeBase()
            success = await kb.initialize()
            if success:
                logger.info("Knowledge base ready")
        """
        # Call the base class initialize which sets up everything
        success = await super().initialize()

        if success:
            # Additional initialization can go here if needed
            # For now, stats initialization is handled in KnowledgeBaseCore
            await self._initialize_stats_counters()

        return success


# ============================================================================
# FACTORY FUNCTION - Preferred way to get KnowledgeBase instance
# ============================================================================

_knowledge_base_instance: Optional[KnowledgeBase] = None
_initialization_lock = asyncio.Lock()
_reset_lock = threading.Lock()  # Thread-safe reset (Issue #613)


async def get_knowledge_base(force_new: bool = False) -> KnowledgeBase:
    """
    Get or create the singleton knowledge base instance (async factory).

    This is the preferred way to obtain a knowledge base instance. It ensures
    that only one instance exists (singleton pattern) and that it's properly
    initialized before being returned.

    Args:
        force_new: If True, create a new instance even if one exists

    Returns:
        KnowledgeBase: Fully initialized knowledge base instance

    Raises:
        RuntimeError: If initialization fails

    Example:
        # Get the knowledge base (will initialize on first call)
        kb = await get_knowledge_base()

        # Now ready to use
        results = await kb.search("machine learning")
    """
    global _knowledge_base_instance

    async with _initialization_lock:
        if force_new or _knowledge_base_instance is None:
            logger.info("Creating new KnowledgeBase instance...")
            kb = KnowledgeBase()

            # Initialize asynchronously
            success = await kb.initialize()

            if not success:
                raise RuntimeError("Failed to initialize knowledge base")

            _knowledge_base_instance = kb
            logger.info("KnowledgeBase singleton instance created and initialized")

        return _knowledge_base_instance


def reset_knowledge_base() -> None:
    """
    Reset the singleton knowledge base instance (thread-safe).

    This is primarily useful for testing or when you need to force
    reinitialization of the knowledge base.

    Note: This does not close existing connections. Call kb.close() first
    if you need to properly cleanup resources.

    Issue #613: Uses thread-safe locking to prevent race conditions.

    Example:
        kb = await get_knowledge_base()
        await kb.close()  # Cleanup resources
        reset_knowledge_base()  # Reset singleton
        kb = await get_knowledge_base()  # Get fresh instance
    """
    global _knowledge_base_instance
    with _reset_lock:
        _knowledge_base_instance = None
        logger.info("KnowledgeBase singleton instance reset")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "KnowledgeBase",
    "get_knowledge_base",
    "reset_knowledge_base",
    # Also export individual mixins for advanced use cases
    "KnowledgeBaseCore",
    "StatsMixin",
    "IndexMixin",
    "SearchMixin",
    "FactsMixin",
    "DocumentsMixin",
    "TagsMixin",
    "CategoriesMixin",
    "CollectionsMixin",
    "SuggestionsMixin",
    "MetadataMixin",
    "VersioningMixin",
    "BulkOperationsMixin",
]
