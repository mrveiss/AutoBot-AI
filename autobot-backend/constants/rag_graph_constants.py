# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Graph-blended retrieval defaults, declared once (#18141); the weight and score threshold are env-backed.

Read through ``RAGConfig`` (``graph_weight``, ``graph_traversal_depth``) by graph-RAG, the
Neural Mesh retriever and the API request schemas; ``RAG_PPR_MAX_HOPS`` is PPR's own default.
The path and relation-expansion depths are the request-schema and service defaults of those
two operations, referenced from both so they cannot drift. ``autobot_memory_graph`` takes its
traversal defaults from here too (#19280): ``multi_hop`` / ``subgraph`` the traversal depth,
``shortest_path`` / ``find_path`` the path depth, ``get_related_entities`` the relation depth.
The library already imports backend modules (``knowledge.serving``), so this stays the one home;
``services/rag_single_definition_19280_test`` fails if a literal default is re-added.
"""

from autobot_shared.env_utils import env_float
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def env_unit_interval(name: str, default: float) -> float:
    """A 0-1 weight or score from *name*; NaN or a value outside 0-1 falls back to *default*.

    Clamping is wrong here (#19354 review): NaN clamps to 0.0 and admits every result, and a typo
    such as ``30`` clamps to 1.0 and rejects every result. ``not 0 <= v <= 1`` is also True for NaN.
    """
    value = env_float(name, default)
    if not 0.0 <= value <= 1.0:
        logger.warning("Invalid %s=%r (must be 0-1); using %s", name, value, default)
        return default
    return value


# Weight of the graph signal in the pre-rerank blend (0.0 = vector score only).
RAG_GRAPH_WEIGHT: float = env_unit_interval("AUTOBOT_RAG_GRAPH_WEIGHT", 0.3)
# Default neighbourhood depth, in hops, for graph expansion requests.
RAG_GRAPH_TRAVERSAL_DEPTH: int = 2
# Deadline for a graph-RAG search when the caller sets none (the pre-#18141 private budget).
RAG_GRAPH_TIMEOUT_SECONDS: float = env_float("AUTOBOT_RAG_GRAPH_TIMEOUT_SECONDS", 10.0)
# Hops loaded by Personalized PageRank when the caller does not narrow it.
RAG_PPR_MAX_HOPS: int = 3
# Longest relationship path, in hops, a shortest-path query searches by default.
RAG_GRAPH_PATH_DEPTH: int = 6
# Fact-relation hops a KB hybrid search expands its vector matches by.
RAG_RELATION_DEPTH: int = 1
# Minimum relevance score a knowledge-retrieval result needs to be kept (#1532 aligned it, #1526 lowered
# it from 0.7; #19354 gave it this one home). Every retrieval signature and caller reads it.
RAG_SCORE_THRESHOLD: float = env_unit_interval("AUTOBOT_RAG_SCORE_THRESHOLD", 0.3)
