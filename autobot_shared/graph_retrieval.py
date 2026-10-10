# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Graph-blended retrieval: the one score blend and the one set of defaults (#18141).

Graph-RAG (`services/graph_rag_service.py`) and the neural-mesh retriever
(`services/neural_mesh_retriever.py`) both fold a graph signal into a vector score. They each
wrote their own formula, their own 0.3, and their own depth literals. The formula and the
defaults live here; `RAGConfig.graph_weight` is the runtime knob that reads
`GRAPH_WEIGHT_DEFAULT`, and every path takes the weight from there.
"""

from __future__ import annotations

from autobot_shared.env_utils import env_float

#: Share of a candidate's blended score that comes from the graph signal (0.0-1.0).
GRAPH_WEIGHT_DEFAULT: float = 0.3

#: Search budget, in seconds, graph-RAG gives its underlying RAG search. Deliberately tighter than
#: the general RAG timeout: a graph-augmented chat turn must not hang for minutes.
GRAPH_RAG_TIMEOUT_SECONDS: float = env_float("AUTOBOT_GRAPH_RAG_TIMEOUT_SECONDS", 10.0)

#: Default hops for a graph-RAG neighbourhood expansion and for the knowledge-graph
#: traverse / graph-view requests. One meaning, one number.
GRAPH_DEPTH_DEFAULT: int = 2

#: Default hops when a hybrid (vector + relation) search expands each vector hit.
GRAPH_RELATION_DEPTH_DEFAULT: int = 1

#: Default maximum path length for a shortest-path ("how are X and Y connected") query.
GRAPH_PATH_DEFAULT: int = 6

#: Hops of subgraph the mesh personalised-PageRank loads around its seeds.
MESH_PPR_MAX_HOPS: int = 3


def blend_graph_score(base_score: float, graph_signal: float, graph_weight: float) -> float:
    """Blend a candidate's vector score with its graph-adjusted score.

    ``(1 - w) * base + w * graph_signal``. ``graph_signal`` is what the caller's graph says the
    candidate is worth on the same 0-1 scale as ``base_score``: graph-RAG passes
    ``base * relationship_strength``, the mesh passes ``base + ppr_boost``. A candidate the
    graph says nothing about (``graph_signal == base_score``) keeps its score bit-for-bit.
    """
    if graph_signal == base_score:
        return base_score
    return (1.0 - graph_weight) * base_score + graph_weight * graph_signal
