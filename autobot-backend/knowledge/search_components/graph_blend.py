# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one pre-rerank vector+graph score blend (#18141).

Graph-RAG expansion and the Neural Mesh retriever both fold a graph signal into a
vector score before the cross-encoder runs.  They share this function, and the weight
comes from ``RAGConfig.graph_weight``.  The post-rerank stage stays
``compute_blended_score`` in ``reranking.py``.
"""


def blend_graph_score(base_score: float, graph_signal: float, graph_weight: float) -> float:
    """Return ``(1 - w) * base_score + w * graph_signal`` for ``w`` clamped to [0, 1].

    A convex combination: with both inputs in 0-1 the result stays in 0-1, so the
    cross-encoder blend that follows keeps its documented range.
    """
    weight = min(1.0, max(0.0, graph_weight))
    return (1.0 - weight) * base_score + weight * graph_signal
