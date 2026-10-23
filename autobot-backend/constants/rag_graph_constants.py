# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Graph-blended retrieval defaults, declared once (#18141); the weight is env-backed.

Read through ``RAGConfig`` (``graph_weight``, ``graph_traversal_depth``) by graph-RAG, the
Neural Mesh retriever and the API request schemas; ``RAG_PPR_MAX_HOPS`` is PPR's own default.
"""

from autobot_shared.env_utils import env_float

# Weight of the graph signal in the pre-rerank blend (0.0 = vector score only).
RAG_GRAPH_WEIGHT: float = env_float("AUTOBOT_RAG_GRAPH_WEIGHT", 0.3)
# Default neighbourhood depth, in hops, for graph expansion requests.
RAG_GRAPH_TRAVERSAL_DEPTH: int = 2
# Deadline for a graph-RAG search when the caller sets none (the pre-#18141 private budget).
RAG_GRAPH_TIMEOUT_SECONDS: float = env_float("AUTOBOT_RAG_GRAPH_TIMEOUT_SECONDS", 10.0)
# Hops loaded by Personalized PageRank when the caller does not narrow it.
RAG_PPR_MAX_HOPS: int = 3
