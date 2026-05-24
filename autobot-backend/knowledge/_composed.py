# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Composed KnowledgeBase class and singleton factory (#1514).

This module holds the heavy imports (redis, llama_index, chromadb) that
are triggered by the mixin chain.  ``knowledge/__init__.py`` lazily
imports from here so that ``knowledge.pipeline.*`` can be used without
pulling in the full dependency tree.
"""

import asyncio
import threading

from autobot_shared.logging_manager import get_logger
from knowledge.base import KnowledgeBaseCore
from knowledge.bulk import BulkOperationsMixin
from knowledge.categories import CategoriesMixin
from knowledge.collections import CollectionsMixin
from knowledge.documents import DocumentsMixin
from knowledge.facts import FactsMixin
from knowledge.index import IndexMixin
from knowledge.metadata import MetadataMixin
from knowledge.relations import RelationsMixin
from knowledge.search import SearchMixin
from knowledge.stats import StatsMixin
from knowledge.suggestions import SuggestionsMixin
from knowledge.tags import TagsMixin
from knowledge.versioning import VersioningMixin

logger = get_logger(__name__)


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
    RelationsMixin,
):
    """Unified Knowledge Base composed from 14 specialised mixins."""

    def __init__(self):
        super().__init__()
        logger.debug("KnowledgeBase instance created (composed from 14 mixins)")

    async def initialize(self) -> bool:
        """Initialize the knowledge base asynchronously."""
        success = await super().initialize()
        if success:
            await self._initialize_stats_counters()
        return success


# Singleton factory
_knowledge_base_instance: KnowledgeBase | None = None
_initialization_lock = asyncio.Lock()
_reset_lock = threading.Lock()


async def get_knowledge_base(
    force_new: bool = False,
) -> KnowledgeBase:
    """Get or create the singleton KnowledgeBase instance."""
    global _knowledge_base_instance

    async with _initialization_lock:
        if force_new or _knowledge_base_instance is None:
            logger.info("Creating new KnowledgeBase instance...")
            kb = KnowledgeBase()
            success = await kb.initialize()
            if not success:
                raise RuntimeError("Failed to initialize knowledge base")
            _knowledge_base_instance = kb
            logger.info("KnowledgeBase singleton instance created and initialized")

        return _knowledge_base_instance


def reset_knowledge_base() -> None:
    """Reset the singleton (thread-safe, Issue #613)."""
    global _knowledge_base_instance
    with _reset_lock:
        _knowledge_base_instance = None
        logger.info("KnowledgeBase singleton instance reset")
