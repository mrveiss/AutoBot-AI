# Copyright (c) mrveiss. All rights reserved.
# AutoBot - AI-Powered Automation Platform
"""
Memory Graph Semantic Search package.

Issue #3384: Query processor and hybrid scoring for memory graph entities.

Phases implemented here:
  Phase 1 — Core infrastructure: MemoryGraphQueryProcessor, indexes,
             entity / relation retrieval.
  Phase 2 — Search methods: hybrid scoring (semantic + keyword), cosine
             similarity, BM25 text matching.
"""

from knowledge.memory_graph.hybrid_scorer import HybridScorer, SearchResult
from knowledge.memory_graph.query_processor import (
    MemoryGraphQueryProcessor,
    QueryIntent,
)

__all__ = [
    "HybridScorer",
    "MemoryGraphQueryProcessor",
    "QueryIntent",
    "SearchResult",
]
