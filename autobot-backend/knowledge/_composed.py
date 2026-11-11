# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Composed KnowledgeBase class and singleton factory (#1514).

This module holds the heavy imports (redis, llama_index, chromadb) that
are triggered by the mixin chain.  ``knowledge/__init__.py`` lazily
imports from here so that ``knowledge.pipeline.*`` can be used without
pulling in the full dependency tree.
"""

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

    def __init__(self, config_manager=None):
        """Compose the knowledge base, optionally with an injected ConfigManager (#13162)."""
        super().__init__(config_manager=config_manager)
        logger.debug("KnowledgeBase instance created (composed from 14 mixins)")

    async def initialize(self) -> bool:
        """Initialize the knowledge base asynchronously."""
        success = await super().initialize()
        if success:
            await self._initialize_stats_counters()
        return success


# Facade over the one store (#18122 S2)
async def get_knowledge_base(
    force_new: bool = False,
) -> KnowledgeBase:
    """Return the shared KnowledgeBase from ``knowledge_factory`` (#18122).

    This module keeps no instance and no lock; creation, the retry cooldown and
    legacy-fact adoption all live in ``knowledge_factory``. ``force_new`` is accepted
    for call-site compatibility, logged and ignored (owner D3), matching
    ``knowledge_base_factory``'s ``force_reinit``.

    Raises:
        RuntimeError: when the factory returns None (init failed or cooling down).
    """
    from knowledge_factory import get_knowledge_base_async

    if force_new:
        logger.warning("get_knowledge_base(force_new=True) ignored: the shared instance is returned")
    kb = await get_knowledge_base_async()
    if kb is None:
        raise RuntimeError("Failed to initialize knowledge base")
    return kb


def reset_knowledge_base(app=None) -> None:
    """Clear the shared singleton, and ``app``'s projection if given (Issue #613, #18122)."""
    from knowledge_factory import reset_knowledge_base as _reset

    _reset(app)
