# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Metrics for graph-aware RAG search (Issue #372).

Split out of ``services.graph_rag_service`` (which re-exports ``GraphRAGMetrics``) so that
module stays under its size ceiling.
"""

from dataclasses import dataclass
from typing import Any, Dict

from advanced_rag_optimizer import RAGMetrics


@dataclass
class GraphRAGMetrics(RAGMetrics):
    """
    Extended metrics for graph-RAG operations.

    Inherits all standard RAG metrics and adds graph-specific tracking.
    """

    graph_traversal_time: float = 0.0
    entities_explored: int = 0
    relationships_traversed: int = 0
    graph_expansion_enabled: bool = False
    graph_results_added: int = 0

    # === Issue #372: Feature Envy Reduction Methods ===

    def copy_from_rag_metrics(self, rag_metrics: "RAGMetrics") -> None:
        """Copy base metrics from RAG search (Issue #372 - reduces feature envy)."""
        self.query_processing_time = rag_metrics.query_processing_time
        self.retrieval_time = rag_metrics.retrieval_time
        self.reranking_time = rag_metrics.reranking_time
        self.documents_considered = rag_metrics.documents_considered
        self.hybrid_search_enabled = rag_metrics.hybrid_search_enabled

    def record_graph_results(self, graph_traversal_time: float, results_added: int) -> None:
        """Record graph expansion results (Issue #372 - reduces feature envy)."""
        self.graph_expansion_enabled = True
        self.graph_traversal_time = graph_traversal_time
        self.graph_results_added = results_added

    def finalize(self, final_count: int, total_time: float) -> None:
        """Finalize metrics with final counts (Issue #372 - reduces feature envy)."""
        self.final_results_count = final_count
        self.total_time = total_time

    def get_timing_summary(self) -> str:
        """Get timing summary string (Issue #372 - reduces feature envy)."""
        return (
            f"{self.total_time:.3f}s total "
            f"(RAG: {self.retrieval_time:.3f}s, "
            f"Graph: {self.graph_traversal_time:.3f}s)"
        )

    def to_response_dict(self) -> Dict[str, Any]:
        """Convert metrics to API response dictionary (Issue #372 - reduces feature envy)."""
        return {
            "query_processing_time": self.query_processing_time,
            "retrieval_time": self.retrieval_time,
            "reranking_time": self.reranking_time,
            "graph_traversal_time": self.graph_traversal_time,
            "total_time": self.total_time,
            "documents_considered": self.documents_considered,
            "final_results_count": self.final_results_count,
            "entities_explored": self.entities_explored,
            "graph_expansion_enabled": self.graph_expansion_enabled,
            "graph_results_added": self.graph_results_added,
        }
