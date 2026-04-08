# Copyright (c) mrveiss. All rights reserved.
"""Compatibility shim — all symbols live in autobot_memory_graph (#3612).

PRs #3608 and #3609 introduced knowledge/memory_graph/ as a parallel package.
This shim redirects every import to the canonical autobot_memory_graph package
so those PRs can be merged without breaking any import sites.
"""

from autobot_memory_graph import *  # noqa: F401, F403
from autobot_memory_graph import (  # noqa: F401
    AutoBotMemoryGraph,
    AutoBotMemoryGraphCore,
    ENTITY_TYPES,
    RELATION_TYPES,
    VALID_ACTIVITY_TYPES,
    HybridScorer,
    MemoryGraphQueryProcessor,
    QueryIntent,
    SearchResult,
    ensure_indexes,
)
from autobot_memory_graph.entities import EntityOperationsMixin  # noqa: F401
from autobot_memory_graph.relations import RelationOperationsMixin  # noqa: F401

# Convenience aliases used in the rejected parallel-package design
create_entity = AutoBotMemoryGraph.create_entity if hasattr(  # type: ignore[attr-defined]
    AutoBotMemoryGraph, "create_entity"
) else None
create_relation = AutoBotMemoryGraph.create_relation if hasattr(  # type: ignore[attr-defined]
    AutoBotMemoryGraph, "create_relation"
) else None
get_entity = AutoBotMemoryGraph.get_entity if hasattr(  # type: ignore[attr-defined]
    AutoBotMemoryGraph, "get_entity"
) else None
