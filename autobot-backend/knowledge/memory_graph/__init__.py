# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) mrveiss. All rights reserved.
"""Compatibility shim — all symbols live in autobot_memory_graph (#3612).

PRs #3608 and #3609 introduced knowledge/memory_graph/ as a parallel package.
This shim redirects every import to the canonical autobot_memory_graph package
so those PRs can be merged without breaking any import sites.
"""

from autobot_memory_graph import *  # noqa: F401, F403
from autobot_memory_graph import (  # noqa: F401
    ENTITY_TYPES,
    RELATION_TYPES,
    VALID_ACTIVITY_TYPES,
    AutoBotMemoryGraph,
    AutoBotMemoryGraphCore,
    HybridScorer,
    MemoryGraphQueryProcessor,
    QueryIntent,
    SearchResult,
    ensure_indexes,
)
from autobot_memory_graph.entities import EntityOperationsMixin  # noqa: F401
from autobot_memory_graph.relations import RelationOperationsMixin  # noqa: F401

# Convenience aliases used in the rejected parallel-package design
create_entity = (
    AutoBotMemoryGraph.create_entity
    if hasattr(AutoBotMemoryGraph, "create_entity")  # type: ignore[attr-defined]
    else None
)
create_relation = (
    AutoBotMemoryGraph.create_relation
    if hasattr(AutoBotMemoryGraph, "create_relation")  # type: ignore[attr-defined]
    else None
)
get_entity = (
    AutoBotMemoryGraph.get_entity if hasattr(AutoBotMemoryGraph, "get_entity") else None  # type: ignore[attr-defined]
)
