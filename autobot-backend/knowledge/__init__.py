# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
    The ``knowledge/__init__.py`` module body no longer eagerly imports
    ``knowledge.base`` and its mixin siblings (which pull in redis,
    llama_index, and chromadb).  All heavy classes are deferred to
    ``knowledge/_composed.py`` and loaded on first attribute access
    via PEP 562 ``__getattr__``.
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

    ``__all__`` is the single source of truth for exported names.
    Each name is resolved via ``getattr(knowledge._composed, name)``
    and cached in module globals so subsequent accesses skip this
    function.

    Note: if a sibling mixin module (knowledge/base.py, etc.) ever
    adds a top-level ``from knowledge import X``, it will create a
    circular import through _composed.py.  Keep such imports inside
    function bodies.
    """
    if name not in __all__:
        raise AttributeError(f"module 'knowledge' has no attribute {name!r}")

    from knowledge import _composed

    value = getattr(_composed, name)
    globals()[name] = value
    return value
