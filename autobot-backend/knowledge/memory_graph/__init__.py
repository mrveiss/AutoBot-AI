# Copyright (c) mrveiss. All rights reserved.
"""
knowledge.memory_graph — Redis DB 1 (knowledge) memory graph foundation layer.

Provides:
- Semantic search query processor and hybrid scorer (query_processor.py, hybrid_scorer.py)
- Schema constants and index creation (schema.py)
- Entity / relation CRUD and BFS traversal (graph_store.py)

Public API re-exported from this package so callers can write:
    from knowledge.memory_graph import MemoryGraphQueryProcessor, create_entity
"""

from .hybrid_scorer import HybridScorer, SearchResult  # noqa: F401
from .query_processor import MemoryGraphQueryProcessor, QueryIntent  # noqa: F401

# Graph store symbols — added by PR #3608 / issue-3385
try:
    from .graph_store import (  # noqa: F401
        create_entity,
        create_relation,
        get_entity,
        get_incoming_relations,
        get_outgoing_relations,
        traverse_relations,
    )
    from .schema import (  # noqa: F401
        ENTITY_KEY_PREFIX,
        ENTITY_TYPES,
        FULLTEXT_INDEX_NAME,
        PRIMARY_INDEX_NAME,
        RELATION_TYPES,
        RELATIONS_IN_PREFIX,
        RELATIONS_OUT_PREFIX,
        ensure_indexes,
    )
except ImportError:
    pass  # graph store not yet merged; safe to skip

__all__ = [
    # query processor / hybrid scorer
    "HybridScorer",
    "MemoryGraphQueryProcessor",
    "QueryIntent",
    "SearchResult",
    # schema
    "ENTITY_KEY_PREFIX",
    "ENTITY_TYPES",
    "FULLTEXT_INDEX_NAME",
    "PRIMARY_INDEX_NAME",
    "RELATION_TYPES",
    "RELATIONS_IN_PREFIX",
    "RELATIONS_OUT_PREFIX",
    "ensure_indexes",
    # graph_store
    "create_entity",
    "create_relation",
    "get_entity",
    "get_incoming_relations",
    "get_outgoing_relations",
    "traverse_relations",
]
