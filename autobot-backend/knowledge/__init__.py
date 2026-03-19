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
- RelationsMixin: Fact-to-fact graph relations and traversal (Issue #1279)

Usage:
    from knowledge import get_knowledge_base

    # Get initialized instance
    kb = await get_knowledge_base()

    # Search
    results = await kb.search("Python security")

    # Store fact
    result = await kb.store_fact("Content", {"category": "general"})

Lazy Loading (#1514):
    Importing ``knowledge.pipeline.*`` no longer triggers the full
    dependency chain (redis, llama_index, chromadb).  Heavy classes are
    loaded on first access via ``__getattr__``.
"""

__all__ = [
    "KnowledgeBase",
    "get_knowledge_base",
    "reset_knowledge_base",
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
    "RelationsMixin",
]


def __getattr__(name: str):
    """Lazy-load heavy knowledge base classes on first access (#1514).

    This avoids pulling redis, llama_index, and chromadb when only
    ``knowledge.pipeline.*`` subpackages are imported.
    """
    if name not in __all__:
        raise AttributeError(f"module 'knowledge' has no attribute {name!r}")

    from knowledge._composed import (  # noqa: F811
        BulkOperationsMixin,
        CategoriesMixin,
        CollectionsMixin,
        DocumentsMixin,
        FactsMixin,
        IndexMixin,
        KnowledgeBase,
        KnowledgeBaseCore,
        MetadataMixin,
        RelationsMixin,
        SearchMixin,
        StatsMixin,
        SuggestionsMixin,
        TagsMixin,
        VersioningMixin,
        get_knowledge_base,
        reset_knowledge_base,
    )

    # Populate module globals so subsequent accesses skip __getattr__
    globals().update(
        {
            "KnowledgeBase": KnowledgeBase,
            "get_knowledge_base": get_knowledge_base,
            "reset_knowledge_base": reset_knowledge_base,
            "KnowledgeBaseCore": KnowledgeBaseCore,
            "StatsMixin": StatsMixin,
            "IndexMixin": IndexMixin,
            "SearchMixin": SearchMixin,
            "FactsMixin": FactsMixin,
            "DocumentsMixin": DocumentsMixin,
            "TagsMixin": TagsMixin,
            "CategoriesMixin": CategoriesMixin,
            "CollectionsMixin": CollectionsMixin,
            "SuggestionsMixin": SuggestionsMixin,
            "MetadataMixin": MetadataMixin,
            "VersioningMixin": VersioningMixin,
            "BulkOperationsMixin": BulkOperationsMixin,
            "RelationsMixin": RelationsMixin,
        }
    )

    return globals()[name]
