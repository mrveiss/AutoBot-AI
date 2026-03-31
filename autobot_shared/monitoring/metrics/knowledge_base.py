# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Metrics Recorder

Metrics for knowledge base operations including document management,
vector embeddings, search operations, and caching.
Created as part of Issue #470 - Add missing Prometheus metrics.

Covers:
- Document count and operations
- Vector embedding storage and operations
- Search latency and throughput
- Indexing performance
- Cache hit/miss rates
"""

from prometheus_client import Counter, Gauge, Histogram

from .base import BaseMetricsRecorder


class KnowledgeBaseMetricsRecorder(BaseMetricsRecorder):
    """Recorder for knowledge base and vector store metrics."""

    def _init_metrics(self) -> None:
        """Initialize knowledge base metrics.

        Issue #665: Refactored to delegate to category-specific helper methods
        to reduce function length from 140 lines to under 50 lines.
        """
        self._init_document_metrics()
        self._init_embedding_metrics()
        self._init_search_metrics()
        self._init_indexing_metrics()
        self._init_cache_metrics()

    def _init_document_metrics(self) -> None:
        """Initialize document-related metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.documents_total = Gauge(
            "autobot_knowledge_documents_total",
            "Total number of documents in knowledge base",
            ["collection", "document_type"],
            registry=self.registry,
        )

        self.document_operations = Counter(
            "autobot_knowledge_document_operations_total",
            "Total document operations",
            ["operation", "collection"],  # operation: add, update, delete
            registry=self.registry,
        )

        self.document_size_bytes = Histogram(
            "autobot_knowledge_document_size_bytes",
            "Document size in bytes",
            ["collection"],
            buckets=[1024, 10240, 102400, 1048576, 10485760, 104857600],
            registry=self.registry,
        )

    def _init_embedding_metrics(self) -> None:
        """Initialize vector embedding metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.vectors_total = Gauge(
            "autobot_knowledge_vectors_total",
            "Total number of vector embeddings",
            ["collection"],
            registry=self.registry,
        )

        self.embedding_operations = Counter(
            "autobot_knowledge_embedding_operations_total",
            "Total embedding operations",
            ["operation", "model"],  # operation: create, update, delete
            registry=self.registry,
        )

        self.embedding_dimensions = Gauge(
            "autobot_knowledge_embedding_dimensions",
            "Vector embedding dimensions",
            ["model"],
            registry=self.registry,
        )

        self.embedding_latency = Histogram(
            "autobot_knowledge_embedding_latency_seconds",
            "Embedding generation latency in seconds",
            ["model"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=self.registry,
        )

    def _init_search_metrics(self) -> None:
        """Initialize search-related metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.search_requests = Counter(
            "autobot_knowledge_search_requests_total",
            "Total search requests",
            ["search_type", "collection"],  # search_type: semantic, keyword, hybrid
            registry=self.registry,
        )

        self.search_latency = Histogram(
            "autobot_knowledge_search_latency_seconds",
            "Search latency in seconds",
            ["search_type", "collection"],
            buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
            registry=self.registry,
        )

        self.search_results_count = Histogram(
            "autobot_knowledge_search_results_count",
            "Number of search results returned",
            ["search_type"],
            buckets=[0, 1, 5, 10, 25, 50, 100, 250, 500],
            registry=self.registry,
        )

    def _init_indexing_metrics(self) -> None:
        """Initialize indexing-related metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.indexing_duration = Histogram(
            "autobot_knowledge_indexing_duration_seconds",
            "Indexing duration in seconds",
            ["collection", "index_type"],
            buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0],
            registry=self.registry,
        )

        self.indexing_operations = Counter(
            "autobot_knowledge_indexing_operations_total",
            "Total indexing operations",
            ["collection", "status"],  # status: success, failure
            registry=self.registry,
        )

        self.index_size_bytes = Gauge(
            "autobot_knowledge_index_size_bytes",
            "Index size in bytes",
            ["collection"],
            registry=self.registry,
        )

    def _init_cache_metrics(self) -> None:
        """Initialize cache-related metrics.

        Issue #665: Extracted from _init_metrics to reduce function length.
        """
        self.cache_hits = Counter(
            "autobot_knowledge_cache_hits_total",
            "Total cache hits",
            ["cache_type"],  # cache_type: embedding, search, document
            registry=self.registry,
        )

        self.cache_misses = Counter(
            "autobot_knowledge_cache_misses_total",
            "Total cache misses",
            ["cache_type"],
            registry=self.registry,
        )

        self.cache_size_items = Gauge(
            "autobot_knowledge_cache_size_items",
            "Number of items in cache",
            ["cache_type"],
            registry=self.registry,
        )

        self.cache_evictions = Counter(
            "autobot_knowledge_cache_evictions_total",
            "Total cache evictions",
            ["cache_type", "reason"],  # reason: ttl, size, manual
            registry=self.registry,
        )

    # =========================================================================
    # Document Methods
    # =========================================================================

    def set_document_count(
        self, count: int, collection: str, document_type: str = "default"
    ) -> None:
        """Set total document count for a collection."""
        self.documents_total.labels(
            collection=collection, document_type=document_type
        ).set(count)

    def record_document_operation(
        self, operation: str, collection: str, size_bytes: int = 0
    ) -> None:
        """Record a document operation."""
        self.document_operations.labels(
            operation=operation, collection=collection
        ).inc()
        if size_bytes > 0:
            self.document_size_bytes.labels(collection=collection).observe(size_bytes)

    # =========================================================================
    # Vector Methods
    # =========================================================================

    def set_vector_count(self, count: int, collection: str) -> None:
        """Set total vector count for a collection."""
        self.vectors_total.labels(collection=collection).set(count)

    def record_embedding_operation(
        self, operation: str, model: str, latency_seconds: float = 0
    ) -> None:
        """Record an embedding operation."""
        self.embedding_operations.labels(operation=operation, model=model).inc()
        if latency_seconds > 0:
            self.embedding_latency.labels(model=model).observe(latency_seconds)

    def set_embedding_dimensions(self, dimensions: int, model: str) -> None:
        """Set embedding dimensions for a model."""
        self.embedding_dimensions.labels(model=model).set(dimensions)

    # =========================================================================
    # Search Methods
    # =========================================================================

    def record_search(
        self,
        search_type: str,
        collection: str,
        latency_seconds: float,
        results_count: int,
    ) -> None:
        """Record a search operation with all metrics."""
        self.search_requests.labels(
            search_type=search_type, collection=collection
        ).inc()
        self.search_latency.labels(
            search_type=search_type, collection=collection
        ).observe(latency_seconds)
        self.search_results_count.labels(search_type=search_type).observe(results_count)

    # =========================================================================
    # Indexing Methods
    # =========================================================================

    def record_indexing(
        self,
        collection: str,
        index_type: str,
        duration_seconds: float,
        success: bool,
    ) -> None:
        """Record an indexing operation."""
        self.indexing_duration.labels(
            collection=collection, index_type=index_type
        ).observe(duration_seconds)
        status = "success" if success else "failure"
        self.indexing_operations.labels(collection=collection, status=status).inc()

    def set_index_size(self, size_bytes: int, collection: str) -> None:
        """Set index size for a collection."""
        self.index_size_bytes.labels(collection=collection).set(size_bytes)

    # =========================================================================
    # Cache Methods
    # =========================================================================

    def record_cache_hit(self, cache_type: str) -> None:
        """Record a cache hit."""
        self.cache_hits.labels(cache_type=cache_type).inc()

    def record_cache_miss(self, cache_type: str) -> None:
        """Record a cache miss."""
        self.cache_misses.labels(cache_type=cache_type).inc()

    def set_cache_size(self, size: int, cache_type: str) -> None:
        """Set cache size in items."""
        self.cache_size_items.labels(cache_type=cache_type).set(size)

    def record_cache_eviction(self, cache_type: str, reason: str) -> None:
        """Record a cache eviction."""
        self.cache_evictions.labels(cache_type=cache_type, reason=reason).inc()


__all__ = ["KnowledgeBaseMetricsRecorder"]
