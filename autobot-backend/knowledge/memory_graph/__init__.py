# Copyright (c) mrveiss. All rights reserved.
"""
knowledge.memory_graph — Redis DB 2 memory graph foundation layer.

Week 1 deliverable for issue #3385.  Provides:
- Schema constants and index creation (schema.py)
- Entity / relation CRUD and BFS traversal (graph_store.py)

Public API re-exported from this package so callers can write:
    from knowledge.memory_graph import create_entity, get_entity, create_relation
"""

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

__all__ = [
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
