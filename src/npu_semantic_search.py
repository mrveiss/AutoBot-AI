#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU-Enhanced Semantic Search for AutoBot
Integrates Intel NPU acceleration with ChromaDB and Redis vector store
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import numpy as np

from src.ai_hardware_accelerator import (
    HardwareDevice,
    accelerated_embedding_generation,
    get_ai_accelerator,
)
from src.config import cfg

# Import existing AutoBot components
from src.constants.threshold_constants import TimingConstants
from src.knowledge.embedding_cache import get_embedding_cache
from src.knowledge_base import KnowledgeBase
from src.utils.chromadb_client import get_chromadb_client

# Issue #387: GPU-accelerated vector search
from src.utils.gpu_vector_search import (
    FAISS_AVAILABLE,
    FAISS_GPU_AVAILABLE,
    HybridVectorSearch,
    VectorSearchConfig,
    get_hybrid_vector_search,
)
from src.utils.http_client import get_http_client
from src.utils.logging_manager import get_llm_logger

# Import ChromaDB for multi-modal vector storage
try:
    pass

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

logger = get_llm_logger("npu_semantic_search")

# Issue #380: Module-level tuple for default target modalities in cross-modal search
_DEFAULT_TARGET_MODALITIES = ("text", "image", "audio", "multimodal")


@dataclass
class SearchResult:
    """Enhanced search result with NPU optimization metrics."""

    content: str
    metadata: Dict[str, Any]
    score: float
    doc_id: str
    device_used: str
    processing_time_ms: float
    embedding_model: str


@dataclass
class SearchMetrics:
    """Search performance metrics."""

    total_documents_searched: int
    embedding_generation_time_ms: float
    similarity_computation_time_ms: float
    total_search_time_ms: float
    device_used: str
    hardware_utilization: Dict[str, float]


@dataclass
class MultiModalSearchResult:
    """Multi-modal search result with cross-modal metadata."""

    content: Any  # Could be text, image path, audio path, etc.
    modality: str  # 'text', 'image', 'audio', 'multimodal'
    metadata: Dict[str, Any]
    score: float
    doc_id: str
    source_modality: Optional[str] = None  # Original modality for fused embeddings
    fusion_confidence: Optional[float] = None


def _convert_chroma_results(
    search_results: Dict[str, Any], modality: str, threshold: float
) -> List[MultiModalSearchResult]:
    """Convert ChromaDB search results to MultiModalSearchResult objects (Issue #315).

    Args:
        search_results: Raw ChromaDB query results
        modality: Target modality name
        threshold: Minimum similarity threshold

    Returns:
        List of MultiModalSearchResult objects above threshold
    """
    results = []
    if not search_results["ids"] or len(search_results["ids"][0]) == 0:
        return results

    # Use zip for parallel iteration over ChromaDB result arrays (avoids index access)
    for doc_id, distance, metadata, content in zip(
        search_results["ids"][0],
        search_results["distances"][0],
        search_results["metadatas"][0],
        search_results["documents"][0],
    ):
        # Convert distance to similarity (ChromaDB uses L2 distance)
        similarity = 1.0 / (1.0 + distance)

        if similarity < threshold:
            continue

        result = MultiModalSearchResult(
            content=content,
            modality=modality,
            metadata=metadata,
            score=similarity,
            doc_id=doc_id,
            source_modality=metadata.get("source_modality"),
            fusion_confidence=metadata.get("fusion_confidence"),
        )
        results.append(result)

    return results


class NPUSemanticSearch:
    """
    NPU-Enhanced Semantic Search Engine for AutoBot.

    Provides intelligent hardware acceleration for semantic search operations:
    - NPU for lightweight embedding generation and similarity computation
    - GPU for heavy document processing and complex models
    - CPU fallback for reliability
    """

    def __init__(self):
        """Initialize NPU semantic search with hardware detection and caching."""
        self.knowledge_base = None
        self.ai_accelerator = None
        # Use Issue #65 P0 optimized EmbeddingCache (60-80% improvement for repeated queries)
        self.embedding_cache = get_embedding_cache()
        self.search_results_cache = {}  # Cache for complete search results
        self.cache_max_size = 100
        self.cache_ttl_seconds = 300  # 5 minutes

        # Performance optimization settings
        self.batch_size_npu = 32  # Optimal NPU batch size
        self.batch_size_gpu = 128  # Optimal GPU batch size
        self.similarity_threshold = 0.7  # Minimum similarity for results

        # NPU Worker configuration
        import os

        npu_worker_host = os.getenv("AUTOBOT_NPU_WORKER_HOST")
        npu_worker_port = os.getenv("AUTOBOT_NPU_WORKER_PORT")
        if not npu_worker_host or not npu_worker_port:
            raise ValueError(
                "NPU Worker configuration missing: AUTOBOT_NPU_WORKER_HOST and "
                "AUTOBOT_NPU_WORKER_PORT environment variables must be set"
            )
        self.npu_worker_url = cfg.get(
            "npu_worker.url", f"http://{npu_worker_host}:{npu_worker_port}"
        )

        # ChromaDB multi-modal collections
        self.chroma_client = None
        self.chroma_db_path = Path("data/chromadb")
        self.collections = {}
        self.collection_names = {
            "text": "autobot_text_embeddings",
            "image": "autobot_image_embeddings",
            "audio": "autobot_audio_embeddings",
            "multimodal": "autobot_multimodal_fused",
            "code": "autobot_code_embeddings",  # Issue #207: Code semantic search
        }

        # Issue #387: GPU-accelerated hybrid vector search
        self.hybrid_search: Optional[HybridVectorSearch] = None
        self.use_gpu_search = cfg.get("vector_search.use_gpu", True)

    async def initialize(self):
        """Initialize NPU semantic search engine."""
        logger.info("🚀 Initializing NPU Semantic Search Engine")

        # Initialize dependencies
        self.ai_accelerator = await get_ai_accelerator()
        self.knowledge_base = KnowledgeBase()

        # Wait for knowledge base initialization
        max_wait = TimingConstants.SHORT_TIMEOUT  # seconds
        wait_time = 0
        while not self.knowledge_base.vector_store and wait_time < max_wait:
            await asyncio.sleep(TimingConstants.STANDARD_DELAY)
            wait_time += 1

        if self.knowledge_base.vector_store:
            logger.info("✅ Knowledge base vector store ready")
        else:
            logger.warning(
                "⚠️ Knowledge base vector store not ready, using basic search"
            )

        # Initialize ChromaDB for multi-modal storage
        await self._initialize_chromadb()

        # Issue #387: Initialize GPU-accelerated hybrid search
        if self.use_gpu_search and FAISS_AVAILABLE:
            await self._initialize_hybrid_search()

        # Test NPU connectivity
        await self._test_npu_connectivity()

        logger.info("✅ NPU Semantic Search Engine initialized")

    async def _initialize_hybrid_search(self):
        """Issue #387: Initialize GPU-accelerated hybrid vector search."""
        try:
            config = VectorSearchConfig(
                embedding_dim=384,  # sentence-transformers default
                use_gpu=True,
                index_path="data/faiss_index",
            )

            self.hybrid_search = await get_hybrid_vector_search(
                chromadb_client=self.chroma_client, config=config
            )

            stats = self.hybrid_search.get_stats()
            backend = stats.get("faiss_index", {}).get("backend", "unknown")
            gpu_available = stats.get("faiss_index", {}).get("gpu_available", False)

            if gpu_available:
                logger.info(
                    f"✅ GPU-accelerated hybrid search initialized (backend={backend})"
                )
            else:
                logger.info(
                    f"✅ Hybrid search initialized with CPU fallback (backend={backend})"
                )

        except Exception as e:
            logger.warning("⚠️ Failed to initialize hybrid search: %s", e)
            self.hybrid_search = None

    async def _test_npu_connectivity(self):
        """Test NPU Worker connectivity and capabilities."""
        try:
            # Use singleton HTTP client for connection pooling
            http_client = get_http_client()
            async with await http_client.get(
                f"{self.npu_worker_url}/health", timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    health_data = await response.json()
                    logger.info(
                        f"✅ NPU Worker connected - NPU Available: {health_data.get('npu_available', False)}"
                    )
                else:
                    logger.warning(
                        f"⚠️ NPU Worker health check failed: {response.status}"
                    )
        except Exception as e:
            logger.warning("⚠️ NPU Worker connectivity test failed: %s", e)

    def _create_empty_metrics(self) -> SearchMetrics:
        """Create metrics for empty query case."""
        return SearchMetrics(
            total_documents_searched=0,
            embedding_generation_time_ms=0,
            similarity_computation_time_ms=0,
            total_search_time_ms=0,
            device_used="none",
            hardware_utilization={},
        )

    def _convert_basic_results(
        self, basic_results: List[Dict], device_label: str
    ) -> List[SearchResult]:
        """Convert basic search results to SearchResult objects."""
        return [
            SearchResult(
                content=r["content"],
                metadata=r["metadata"],
                score=r["score"],
                doc_id=r.get("doc_id", str(uuid.uuid4())),
                device_used=device_label,
                processing_time_ms=0,
                embedding_model=device_label,
            )
            for r in basic_results
        ]

    async def _perform_vector_search(
        self,
        query: str,
        query_embedding: np.ndarray,
        similarity_top_k: int,
        filters: Optional[Dict[str, Any]],
        embedding_device: str,
    ) -> List[SearchResult]:
        """Perform vector similarity search with fallback."""
        if self.knowledge_base.vector_store and self.knowledge_base.vector_index:
            return await self._vector_similarity_search(
                query_embedding, similarity_top_k, filters, embedding_device
            )

        logger.warning("Vector store not available, using basic search fallback")
        basic_results = await self.knowledge_base.search(
            query, similarity_top_k, filters, "text"
        )
        return self._convert_basic_results(basic_results, "cpu_fallback")

    async def _create_search_metrics(
        self,
        results: List[SearchResult],
        embedding_time: float,
        search_time: float,
        total_time: float,
        embedding_device: str,
    ) -> SearchMetrics:
        """Create performance metrics for search results."""
        return SearchMetrics(
            total_documents_searched=len(results),
            embedding_generation_time_ms=embedding_time,
            similarity_computation_time_ms=search_time,
            total_search_time_ms=total_time,
            device_used=embedding_device,
            hardware_utilization=await self._get_hardware_utilization(),
        )

    async def _handle_search_error(
        self,
        error: Exception,
        query: str,
        similarity_top_k: int,
        filters: Optional[Dict[str, Any]],
        start_time: float,
    ) -> Tuple[List[SearchResult], SearchMetrics]:
        """Handle search error with fallback."""
        logger.error("❌ Enhanced search failed: %s", error)
        basic_results = await self.knowledge_base.search(
            query, similarity_top_k, filters, "auto"
        )
        fallback_results = self._convert_basic_results(basic_results, "fallback")
        total_time = (time.time() - start_time) * 1000

        fallback_metrics = SearchMetrics(
            total_documents_searched=len(fallback_results),
            embedding_generation_time_ms=0,
            similarity_computation_time_ms=total_time,
            total_search_time_ms=total_time,
            device_used="fallback",
            hardware_utilization={},
        )
        return fallback_results, fallback_metrics

    def _log_search_completion(
        self,
        results: List[SearchResult],
        total_time: float,
        embedding_time: float,
        search_time: float,
        device: str,
    ) -> None:
        """Log search completion with timing details. Issue #620.

        Args:
            results: Search results list
            total_time: Total search time in ms
            embedding_time: Embedding generation time in ms
            search_time: Similarity search time in ms
            device: Device used for embedding
        """
        logger.info(
            f"✅ Search completed: {len(results)} results in {total_time:.2f}ms "
            f"(embedding: {embedding_time:.2f}ms, search: {search_time:.2f}ms) "
            f"using {device}"
        )

    async def _execute_search_pipeline(
        self,
        query: str,
        similarity_top_k: int,
        filters: Optional[Dict[str, Any]],
        enable_npu_acceleration: bool,
        force_device: Optional[HardwareDevice],
        start_time: float,
        cache_key: str,
    ) -> Tuple[List[SearchResult], SearchMetrics]:
        """Execute the core search pipeline with embedding and vector search. Issue #620.

        Args:
            query: Search query string
            similarity_top_k: Number of results to return
            filters: Optional metadata filters
            enable_npu_acceleration: Whether to use NPU
            force_device: Force specific device
            start_time: Search start timestamp
            cache_key: Cache key for result storage

        Returns:
            Tuple of (search_results, performance_metrics)
        """
        embedding_start = time.time()
        query_embedding, embedding_device = await self._generate_optimized_embedding(
            query, enable_npu_acceleration, force_device
        )
        embedding_time = (time.time() - embedding_start) * 1000

        search_start = time.time()
        results = await self._perform_vector_search(
            query, query_embedding, similarity_top_k, filters, embedding_device
        )
        search_time = (time.time() - search_start) * 1000
        total_time = (time.time() - start_time) * 1000

        metrics = await self._create_search_metrics(
            results, embedding_time, search_time, total_time, embedding_device
        )
        self._cache_result(cache_key, (results, metrics))
        self._log_search_completion(
            results, total_time, embedding_time, search_time, embedding_device
        )
        return results, metrics

    async def enhanced_search(
        self,
        query: str,
        similarity_top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        enable_npu_acceleration: bool = True,
        force_device: Optional[HardwareDevice] = None,
    ) -> Tuple[List[SearchResult], SearchMetrics]:
        """Perform NPU-enhanced semantic search. Issue #281, #620."""
        start_time = time.time()

        if not query.strip():
            return [], self._create_empty_metrics()

        logger.info(
            "🔍 Enhanced search: '%s...' (top_k=%s)", query[:50], similarity_top_k
        )

        cache_key = self._generate_cache_key(query, similarity_top_k, filters)
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            logger.info("⚡ Returning cached search result")
            return cached_result

        try:
            return await self._execute_search_pipeline(
                query,
                similarity_top_k,
                filters,
                enable_npu_acceleration,
                force_device,
                start_time,
                cache_key,
            )
        except Exception as e:
            return await self._handle_search_error(
                e, query, similarity_top_k, filters, start_time
            )

    async def _generate_embedding_with_device(
        self, text: str, enable_npu: bool, force_device: Optional[HardwareDevice]
    ) -> Tuple[np.ndarray, str]:
        """Generate embedding using specified device configuration. Issue #620.

        Args:
            text: Text to generate embedding for
            enable_npu: Whether NPU acceleration is enabled
            force_device: Specific device to force (overrides auto-selection)

        Returns:
            Tuple of (embedding array, device name used)
        """
        if force_device:
            embedding = await accelerated_embedding_generation(text, force_device)
            return embedding, force_device.value

        if enable_npu:
            embedding = await accelerated_embedding_generation(text)
            return embedding, "auto_selected"

        from src.utils.semantic_chunker import get_semantic_chunker

        chunker = get_semantic_chunker()
        await chunker._initialize_model()
        embeddings = await chunker._compute_sentence_embeddings_async([text])
        return embeddings[0], "gpu_fallback"

    async def _generate_fallback_embedding(self, text: str) -> Tuple[np.ndarray, str]:
        """Generate embedding using CPU fallback method. Issue #620.

        Args:
            text: Text to generate embedding for

        Returns:
            Tuple of (embedding array, device name)
        """
        from src.utils.semantic_chunker import get_semantic_chunker

        chunker = get_semantic_chunker()
        embeddings = chunker._compute_sentence_embeddings([text])
        return embeddings[0], "cpu_final_fallback"

    async def _generate_optimized_embedding(
        self, text: str, enable_npu: bool, force_device: Optional[HardwareDevice]
    ) -> Tuple[np.ndarray, str]:
        """Generate embedding using optimal hardware with caching. Issue #65 P0."""
        cached_embedding = await self.embedding_cache.get(text)
        if cached_embedding is not None:
            logger.debug("✅ Using cached embedding for query: %s...", text[:50])
            return np.array(cached_embedding), "cached"

        try:
            embedding, device_name = await self._generate_embedding_with_device(
                text, enable_npu, force_device
            )
            await self.embedding_cache.put(text, embedding.tolist())
            return embedding, device_name

        except Exception as e:
            logger.warning(
                f"⚠️ Optimized embedding generation failed: {e}, using fallback"
            )
            embedding, device_name = await self._generate_fallback_embedding(text)
            await self.embedding_cache.put(text, embedding.tolist())
            return embedding, device_name

    def _convert_hybrid_results(
        self, hybrid_results: List[Any], hybrid_metrics: Any, device_used: str
    ) -> List[SearchResult]:
        """Convert hybrid search results to SearchResult format. Issue #620.

        Args:
            hybrid_results: Results from hybrid vector search
            hybrid_metrics: Performance metrics from hybrid search
            device_used: Fallback device identifier

        Returns:
            List of SearchResult objects
        """
        results = []
        for hr in hybrid_results:
            result = SearchResult(
                content=hr.content or "",
                metadata=hr.metadata,
                score=hr.score,
                doc_id=hr.doc_id,
                device_used="gpu" if hybrid_metrics.gpu_utilized else device_used,
                processing_time_ms=hybrid_metrics.query_time_ms,
                embedding_model="hybrid_gpu",
            )
            results.append(result)

        logger.debug(
            f"GPU hybrid search: {len(results)} results in "
            f"{hybrid_metrics.query_time_ms:.2f}ms "
            f"(backend={hybrid_metrics.backend_used.value})"
        )
        return results

    async def _search_with_llamaindex_fallback(
        self, top_k: int, device_used: str
    ) -> List[SearchResult]:
        """Search using LlamaIndex query engine as fallback. Issue #620.

        Args:
            top_k: Number of results to return
            device_used: Device identifier for result metadata

        Returns:
            List of SearchResult objects
        """
        query_engine = self.knowledge_base.vector_index.as_query_engine(
            similarity_top_k=top_k, response_mode="no_text"
        )
        response = await asyncio.to_thread(query_engine.query, "search query")

        results = []
        if hasattr(response, "source_nodes"):
            for node in response.source_nodes:
                result = SearchResult(
                    content=node.node.text,
                    metadata=node.node.metadata or {},
                    score=getattr(node, "score", 0.0),
                    doc_id=node.node.id_ or str(uuid.uuid4()),
                    device_used=device_used,
                    processing_time_ms=0,
                    embedding_model="enhanced_model",
                )
                results.append(result)
        return results

    async def _vector_similarity_search(
        self,
        query_embedding: np.ndarray,
        top_k: int,
        filters: Optional[Dict[str, Any]],
        device_used: str,
    ) -> List[SearchResult]:
        """Perform vector similarity search using GPU-accelerated hybrid or knowledge base."""
        try:
            if self.hybrid_search is not None:
                hybrid_results, hybrid_metrics = await self.hybrid_search.search(
                    query_embedding=query_embedding,
                    top_k=top_k,
                    metadata_filter=filters,
                    include_documents=True,
                )
                if hybrid_results:
                    return self._convert_hybrid_results(
                        hybrid_results, hybrid_metrics, device_used
                    )

            return await self._search_with_llamaindex_fallback(top_k, device_used)

        except Exception as e:
            logger.error("❌ Vector similarity search failed: %s", e)
            return []

    async def _get_hardware_utilization(self) -> Dict[str, float]:
        """Get current hardware utilization metrics."""
        try:
            if self.ai_accelerator:
                status = await self.ai_accelerator.get_hardware_status()
                utilization = {}

                for device, info in status.get("devices", {}).items():
                    metrics = info.get("metrics")
                    if metrics:
                        utilization[device] = metrics.get("utilization_percent", 0.0)
                    else:
                        utilization[device] = 0.0

                return utilization
        except Exception as e:
            logger.warning("⚠️ Could not get hardware utilization: %s", e)

        return {}

    def _generate_cache_key(
        self, query: str, top_k: int, filters: Optional[Dict[str, Any]]
    ) -> str:
        """Generate cache key for search results."""
        import hashlib

        cache_data = {
            "query": query.strip().lower(),
            "top_k": top_k,
            "filters": filters or {},
        }

        cache_string = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_string.encode(), usedforsecurity=False).hexdigest()

    def _get_cached_result(
        self, cache_key: str
    ) -> Optional[Tuple[List[SearchResult], SearchMetrics]]:
        """Get cached search result if available and not expired."""
        if cache_key in self.search_results_cache:
            cached_data, timestamp = self.search_results_cache[cache_key]

            if time.time() - timestamp < self.cache_ttl_seconds:
                return cached_data
            else:
                # Remove expired cache entry
                del self.search_results_cache[cache_key]

        return None

    def _cache_result(
        self, cache_key: str, result: Tuple[List[SearchResult], SearchMetrics]
    ):
        """Cache search result with TTL."""
        # Implement simple LRU eviction
        if len(self.search_results_cache) >= self.cache_max_size:
            # Remove oldest entry
            oldest_key = min(
                self.search_results_cache.keys(),
                key=lambda k: self.search_results_cache[k][1],
            )
            del self.search_results_cache[oldest_key]

        self.search_results_cache[cache_key] = (result, time.time())

    def _create_error_search_result(
        self,
    ) -> Tuple[List[SearchResult], SearchMetrics]:
        """Create empty result tuple for failed batch search query. Issue #620.

        Returns:
            Tuple of empty results list and error metrics
        """
        return (
            [],
            SearchMetrics(
                total_documents_searched=0,
                embedding_generation_time_ms=0,
                similarity_computation_time_ms=0,
                total_search_time_ms=0,
                device_used="error",
                hardware_utilization={},
            ),
        )

    def _process_batch_results(
        self, results: List[Any]
    ) -> List[Tuple[List[SearchResult], SearchMetrics]]:
        """Process batch search results, handling exceptions. Issue #620.

        Args:
            results: Raw results from asyncio.gather with return_exceptions=True

        Returns:
            List of processed result tuples
        """
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Batch search failed for query %s: %s", i, result)
                processed_results.append(self._create_error_search_result())
            else:
                processed_results.append(result)
        return processed_results

    async def batch_search(
        self,
        queries: List[str],
        similarity_top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        enable_npu_acceleration: bool = True,
    ) -> List[Tuple[List[SearchResult], SearchMetrics]]:
        """
        Perform batch semantic search for multiple queries with NPU acceleration.

        Args:
            queries: List of search query strings
            similarity_top_k: Number of results per query
            filters: Optional metadata filters
            enable_npu_acceleration: Whether to use NPU acceleration

        Returns:
            List of tuples (search_results, metrics) for each query
        """
        if not queries:
            return []

        logger.info(
            "🔍 Batch search: %s queries (top_k=%s)", len(queries), similarity_top_k
        )

        semaphore = asyncio.Semaphore(10)

        async def _search_with_semaphore(query: str):
            """Execute single search with semaphore for concurrency control."""
            async with semaphore:
                return await self.enhanced_search(
                    query=query,
                    similarity_top_k=similarity_top_k,
                    filters=filters,
                    enable_npu_acceleration=enable_npu_acceleration,
                )

        results = await asyncio.gather(
            *[_search_with_semaphore(q) for q in queries], return_exceptions=True
        )

        processed_results = self._process_batch_results(results)
        logger.info("✅ Batch search completed: %s results", len(processed_results))
        return processed_results

    def _calculate_device_summary(
        self, device_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate summary statistics for a device's benchmark results (Issue #665: extracted helper)."""
        successful_runs = [r for r in device_results if "error" not in r]

        if not successful_runs:
            return {
                "success_rate": 0,
                "total_runs": len(device_results),
                "error": "All runs failed",
            }

        avg_time = sum(r["total_time_ms"] for r in successful_runs) / len(
            successful_runs
        )
        avg_embedding_time = sum(r["embedding_time_ms"] for r in successful_runs) / len(
            successful_runs
        )
        avg_search_time = sum(r["search_time_ms"] for r in successful_runs) / len(
            successful_runs
        )

        return {
            "average_total_time_ms": avg_time,
            "average_embedding_time_ms": avg_embedding_time,
            "average_search_time_ms": avg_search_time,
            "success_rate": len(successful_runs) / len(device_results) * 100,
            "total_runs": len(device_results),
        }

    async def _benchmark_single_device(
        self,
        device: HardwareDevice,
        test_queries: List[str],
        iterations: int,
    ) -> List[Dict[str, Any]]:
        """Benchmark a single device with all queries and iterations (Issue #665: extracted helper)."""
        device_results = []

        logger.info("🔧 Testing device: %s", device.value)

        # Issue #509, #616: O(n²) nested loops here are INTENTIONAL for benchmarking.
        # queries (n) × iterations (m) = complete benchmark matrix per device.
        for query in test_queries:
            for iteration in range(iterations):
                try:
                    start_time = time.time()

                    search_results, metrics = await self.enhanced_search(
                        query=query,
                        similarity_top_k=5,
                        enable_npu_acceleration=True,
                        force_device=device,
                    )

                    end_time = time.time()

                    device_results.append(
                        {
                            "query": query,
                            "iteration": iteration,
                            "total_time_ms": (end_time - start_time) * 1000,
                            "results_count": len(search_results),
                            "embedding_time_ms": (metrics.embedding_generation_time_ms),
                            "search_time_ms": (metrics.similarity_computation_time_ms),
                            "device_used": metrics.device_used,
                        }
                    )

                except Exception as e:
                    logger.error("❌ Benchmark failed for %s: %s", device.value, e)
                    device_results.append(
                        {"query": query, "iteration": iteration, "error": str(e)}
                    )

        return device_results

    async def benchmark_search_performance(
        self, test_queries: List[str], iterations: int = 3
    ) -> Dict[str, Any]:
        """Benchmark search performance across different hardware configurations."""
        logger.info(
            f"🏃 Starting search performance benchmark with {len(test_queries)} queries"
        )

        results = {
            "test_queries": test_queries,
            "iterations": iterations,
            "device_performance": {},
            "summary": {},
        }

        devices_to_test = [HardwareDevice.NPU, HardwareDevice.GPU, HardwareDevice.CPU]

        for device in devices_to_test:
            device_results = await self._benchmark_single_device(
                device, test_queries, iterations
            )
            results["device_performance"][device.value] = device_results

        # Calculate summary statistics
        for device, device_results in results["device_performance"].items():
            results["summary"][device] = self._calculate_device_summary(device_results)

        logger.info("✅ Search performance benchmark completed")
        return results

    async def get_search_statistics(self) -> Dict[str, Any]:
        """Get comprehensive search engine statistics including embedding cache."""
        embedding_stats = self.embedding_cache.get_stats()

        # Issue #387: Include GPU vector search stats
        gpu_search_stats = (
            self.hybrid_search.get_stats() if self.hybrid_search else None
        )

        return {
            "embedding_cache_stats": embedding_stats,  # Issue #65 P0 metrics
            "search_results_cache_stats": {
                "cache_size": len(self.search_results_cache),
                "cache_max_size": self.cache_max_size,
                "cache_ttl_seconds": self.cache_ttl_seconds,
            },
            "configuration": {
                "batch_size_npu": self.batch_size_npu,
                "batch_size_gpu": self.batch_size_gpu,
                "similarity_threshold": self.similarity_threshold,
                "npu_worker_url": self.npu_worker_url,
                "use_gpu_search": self.use_gpu_search,
            },
            "hardware_status": (
                await self._get_hardware_utilization() if self.ai_accelerator else {}
            ),
            "knowledge_base_ready": (
                self.knowledge_base.vector_store is not None
                if self.knowledge_base
                else False
            ),
            # Issue #387: GPU-accelerated vector search stats
            "gpu_vector_search": gpu_search_stats,
            "faiss_available": FAISS_AVAILABLE,
            "faiss_gpu_available": FAISS_GPU_AVAILABLE,
        }

    async def _initialize_chromadb(self):
        """Initialize ChromaDB client and multi-modal collections."""
        if not CHROMADB_AVAILABLE:
            logger.warning("ChromaDB not available. Multi-modal storage disabled.")
            return

        try:
            # Initialize ChromaDB client using shared utility function
            self.chroma_client = get_chromadb_client(
                db_path=str(self.chroma_db_path),
                allow_reset=True,
                anonymized_telemetry=False,
            )

            # Initialize collections for each modality
            for modality, collection_name in self.collection_names.items():
                try:
                    # Try to get existing collection
                    collection = self.chroma_client.get_collection(name=collection_name)
                    logger.info(
                        f"✅ Loaded existing ChromaDB collection: {collection_name}"
                    )
                except ValueError:
                    # Create new collection if it doesn't exist
                    collection = self.chroma_client.create_collection(
                        name=collection_name,
                        metadata={
                            "modality": modality,
                            "description": f"AutoBot {modality} embeddings",
                        },
                    )
                    logger.info(f"✅ Created new ChromaDB collection: {collection_name}")

                self.collections[modality] = collection

            logger.info("✅ ChromaDB multi-modal collections initialized")

        except Exception as e:
            logger.error("Failed to initialize ChromaDB: %s", e)
            self.chroma_client = None

    def _prepare_document_metadata(
        self, content: Any, modality: str, metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Prepare metadata dictionary for document storage.

        Issue #665: Extracted from store_multimodal_embedding

        Args:
            content: The content being stored
            modality: Type of content ('text', 'image', 'audio')
            metadata: Additional metadata to merge

        Returns:
            Dict containing prepared metadata with modality, timestamp, and preview
        """
        return {
            "modality": modality,
            "timestamp": time.time(),
            "content_preview": (
                str(content)[:200]
                if isinstance(content, str)
                else f"{modality}_content"
            ),
            **(metadata or {}),
        }

    def _generate_document_id(self, modality: str, doc_id: Optional[str]) -> str:
        """Generate or validate document ID for storage.

        Issue #665: Extracted from store_multimodal_embedding

        Args:
            modality: Type of content ('text', 'image', 'audio')
            doc_id: Optional document ID (auto-generated if None)

        Returns:
            Document ID string
        """
        if doc_id is None:
            return f"{modality}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
        return doc_id

    async def _store_in_multimodal_collection(
        self,
        embedding: np.ndarray,
        content: Any,
        doc_metadata: Dict[str, Any],
        doc_id: str,
        modality: str,
    ) -> None:
        """Store embedding in fused multimodal collection.

        Issue #665: Extracted from store_multimodal_embedding

        Args:
            embedding: Generated embedding vector
            content: Original content
            doc_metadata: Base metadata dictionary
            doc_id: Document ID
            modality: Source modality type

        Returns:
            None
        """
        if modality == "multimodal" or not self.ai_accelerator:
            return

        try:
            fused_metadata = {
                **doc_metadata,
                "source_modality": modality,
                "fusion_type": "single_modal_to_unified",
            }

            multimodal_collection = self.collections.get("multimodal")
            if multimodal_collection:
                multimodal_collection.add(
                    embeddings=[embedding.tolist()],
                    metadatas=[fused_metadata],
                    documents=[str(content)],
                    ids=[f"fused_{doc_id}"],
                )
        except Exception as e:
            logger.warning("Failed to store in multimodal collection: %s", e)

    def _store_in_collection(
        self,
        modality: str,
        embedding: np.ndarray,
        content: Any,
        doc_metadata: Dict[str, Any],
        doc_id: str,
    ) -> None:
        """Store embedding in the modality-specific collection. Issue #620.

        Args:
            modality: Target modality collection name
            embedding: Generated embedding vector
            content: Original content
            doc_metadata: Metadata dictionary
            doc_id: Document ID
        """
        collection = self.collections[modality]
        collection.add(
            embeddings=[embedding.tolist()],
            metadatas=[doc_metadata],
            documents=[str(content)],
            ids=[doc_id],
        )

    async def store_multimodal_embedding(
        self,
        content: Any,
        modality: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> bool:
        """Store multi-modal content with embeddings in ChromaDB collection."""
        if not self.chroma_client or modality not in self.collections:
            logger.warning(
                f"ChromaDB not available or unsupported modality: {modality}"
            )
            return False

        try:
            embedding = await accelerated_embedding_generation(
                content=content, modality=modality, preferred_device=HardwareDevice.GPU
            )
            doc_metadata = self._prepare_document_metadata(content, modality, metadata)
            doc_id = self._generate_document_id(modality, doc_id)

            self._store_in_collection(
                modality, embedding, content, doc_metadata, doc_id
            )
            await self._store_in_multimodal_collection(
                embedding, content, doc_metadata, doc_id, modality
            )

            logger.info("✅ Stored %s content with ID: %s", modality, doc_id)
            return True

        except Exception as e:
            logger.error("Failed to store multimodal embedding: %s", e)
            return False

    def _generate_code_doc_id(
        self, element_type: str, language: str, content_hash: str
    ) -> str:
        """Generate unique document ID for code embedding. Issue #620.

        Args:
            element_type: Type of code element
            language: Programming language
            content_hash: Hash of code content

        Returns:
            Unique document ID string. Issue #620.
        """
        return f"code_{element_type}_{language}_{content_hash[:16]}_{int(time.time() * 1000)}"

    def _prepare_code_metadata(
        self,
        file_path: str,
        line_number: int,
        element_type: str,
        element_name: str,
        language: str,
        content_hash: str,
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Prepare metadata dictionary for code embedding storage. Issue #620.

        Args:
            file_path: Path to source file
            line_number: Line number of element
            element_type: Type of code element
            element_name: Name of the element
            language: Programming language
            content_hash: Hash of code content
            metadata: Additional metadata to merge

        Returns:
            Complete metadata dictionary. Issue #620.
        """
        return {
            "file_path": file_path,
            "line_number": line_number,
            "element_type": element_type,
            "element_name": element_name,
            "language": language,
            "content_hash": content_hash,
            "indexed_at": time.time(),
            **(metadata or {}),
        }

    async def store_code_embedding(
        self,
        embedding: np.ndarray,
        code_content: str,
        file_path: str,
        line_number: int,
        element_type: str,
        element_name: str,
        language: str,
        content_hash: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Store code element embedding in ChromaDB collection. Issue #207, #620."""
        if not self.chroma_client or "code" not in self.collections:
            logger.warning("ChromaDB code collection not available")
            return None

        try:
            doc_id = self._generate_code_doc_id(element_type, language, content_hash)
            doc_metadata = self._prepare_code_metadata(
                file_path,
                line_number,
                element_type,
                element_name,
                language,
                content_hash,
                metadata,
            )

            collection = self.collections["code"]
            collection.add(
                embeddings=[embedding.tolist()],
                metadatas=[doc_metadata],
                documents=[code_content],
                ids=[doc_id],
            )

            logger.debug(
                "Stored code embedding: %s:%s (%s)",
                file_path,
                element_name,
                element_type,
            )
            return doc_id

        except Exception as e:
            logger.error("Failed to store code embedding: %s", e)
            return None

    def _build_code_search_filter(
        self, language: Optional[str], element_type: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Build ChromaDB where filter for code search. Issue #620.

        Args:
            language: Filter by programming language
            element_type: Filter by element type (function, class, etc.)

        Returns:
            ChromaDB where filter dict or None if no filters. Issue #620.
        """
        if not language and not element_type:
            return None

        conditions = []
        if language:
            conditions.append({"language": language})
        if element_type:
            conditions.append({"element_type": element_type})

        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def _convert_code_search_results(
        self,
        search_results: Dict[str, Any],
        similarity_threshold: float,
    ) -> List[Dict[str, Any]]:
        """Convert ChromaDB results to code search result format. Issue #620.

        Args:
            search_results: Raw ChromaDB query results
            similarity_threshold: Minimum similarity score to include

        Returns:
            List of result dicts with doc_id, content, metadata, score. Issue #620.
        """
        results = []
        if not search_results["ids"] or len(search_results["ids"][0]) == 0:
            return results

        for i, doc_id in enumerate(search_results["ids"][0]):
            distance = search_results["distances"][0][i]
            similarity = 1.0 / (1.0 + distance)

            if similarity < similarity_threshold:
                continue

            result = {
                "doc_id": doc_id,
                "content": search_results["documents"][0][i],
                "metadata": search_results["metadatas"][0][i],
                "score": similarity,
                "distance": distance,
            }
            results.append(result)

        return results

    async def search_code_embeddings(
        self,
        query_embedding: np.ndarray,
        language: Optional[str] = None,
        element_type: Optional[str] = None,
        max_results: int = 20,
        similarity_threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Search code embeddings collection. Issue #207, #620.

        Args:
            query_embedding: Query embedding vector
            language: Filter by programming language
            element_type: Filter by element type
            max_results: Maximum number of results
            similarity_threshold: Minimum similarity score

        Returns:
            List of search results with metadata
        """
        if not self.chroma_client or "code" not in self.collections:
            logger.warning("ChromaDB code collection not available")
            return []

        try:
            collection = self.collections["code"]
            where_filter = self._build_code_search_filter(language, element_type)

            search_results = collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=max_results,
                where=where_filter,
                include=["metadatas", "documents", "distances"],
            )

            results = self._convert_code_search_results(
                search_results, similarity_threshold
            )
            logger.info(
                "Code search found %d results (threshold=%.2f)",
                len(results),
                similarity_threshold,
            )
            return results

        except Exception as e:
            logger.error("Code embedding search failed: %s", e)
            return []

    async def get_code_collection_stats(self) -> Dict[str, Any]:
        """Get statistics for the code embeddings collection."""
        if not self.chroma_client or "code" not in self.collections:
            return {"available": False}

        try:
            collection = self.collections["code"]
            count = collection.count()
            return {
                "available": True,
                "collection_name": self.collection_names["code"],
                "document_count": count,
            }
        except Exception as e:
            logger.error("Failed to get code collection stats: %s", e)
            return {"available": False, "error": str(e)}

    def _search_single_modality(
        self,
        modality: str,
        query_embedding: np.ndarray,
        limit: int,
        threshold: float,
    ) -> List[MultiModalSearchResult]:
        """Search a single modality collection and return results. Issue #620.

        Args:
            modality: Target modality name
            query_embedding: Query embedding vector
            limit: Maximum results to return
            threshold: Minimum similarity threshold

        Returns:
            List of MultiModalSearchResult objects
        """
        try:
            collection = self.collections[modality]
            search_results = collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=limit,
                include=["metadatas", "documents", "distances"],
            )
            modality_results = _convert_chroma_results(
                search_results, modality, threshold
            )
            logger.info(
                f"Found {len(modality_results)} results in {modality} collection"
            )
            return modality_results
        except Exception as e:
            logger.error("Search failed for modality %s: %s", modality, e)
            return []

    async def cross_modal_search(
        self,
        query: Any,
        query_modality: str,
        target_modalities: Optional[List[str]] = None,
        limit: int = 10,
        similarity_threshold: Optional[float] = None,
    ) -> Dict[str, List[MultiModalSearchResult]]:
        """
        Perform cross-modal similarity search.

        Args:
            query: Query content (text, image, audio)
            query_modality: Type of query ('text', 'image', 'audio')
            target_modalities: Modalities to search in (None for all)
            limit: Maximum results per modality
            similarity_threshold: Minimum similarity score

        Returns:
            Dict mapping modality to search results
        """
        if not self.chroma_client:
            logger.warning("ChromaDB not available for cross-modal search")
            return {}

        try:
            query_embedding = await accelerated_embedding_generation(
                content=query,
                modality=query_modality,
                preferred_device=HardwareDevice.GPU,
            )

            if target_modalities is None:
                target_modalities = _DEFAULT_TARGET_MODALITIES

            threshold = similarity_threshold or self.similarity_threshold
            results = {}

            for modality in target_modalities:
                if modality in self.collections:
                    results[modality] = self._search_single_modality(
                        modality, query_embedding, limit, threshold
                    )

            return results

        except Exception as e:
            logger.error("Cross-modal search failed: %s", e)
            return {}

    async def optimize_for_workload(
        self, workload_type: str = "balanced"
    ) -> Dict[str, Any]:
        """Optimize search engine for specific workload types."""
        optimizations = {}

        if workload_type == "latency_optimized":
            # Optimize for fastest response times
            self.batch_size_npu = 16  # Smaller batches for lower latency
            self.batch_size_gpu = 64
            self.cache_max_size = 200  # Larger cache
            self.similarity_threshold = 0.6  # Lower threshold for more results
            optimizations["focus"] = "Optimized for minimum latency"

        elif workload_type == "throughput_optimized":
            # Optimize for maximum throughput
            self.batch_size_npu = 64  # Larger batches
            self.batch_size_gpu = 256
            self.cache_max_size = 50  # Smaller cache to save memory
            self.similarity_threshold = 0.8  # Higher threshold for quality
            optimizations["focus"] = "Optimized for maximum throughput"

        elif workload_type == "quality_optimized":
            # Optimize for best search quality
            self.batch_size_npu = 32
            self.batch_size_gpu = 128
            self.similarity_threshold = 0.75  # Balanced threshold
            optimizations["focus"] = "Optimized for search quality"

        else:  # balanced (default)
            # Balanced optimization
            self.batch_size_npu = 32
            self.batch_size_gpu = 128
            self.cache_max_size = 100
            self.similarity_threshold = 0.7
            optimizations["focus"] = "Balanced optimization"

        optimizations.update(
            {
                "batch_size_npu": self.batch_size_npu,
                "batch_size_gpu": self.batch_size_gpu,
                "cache_max_size": self.cache_max_size,
                "similarity_threshold": self.similarity_threshold,
            }
        )

        logger.info("🎯 Search engine optimized for %s", workload_type)
        return optimizations


# Global instance (thread-safe)
import asyncio as _asyncio_lock

_npu_search_engine = None
_npu_search_engine_lock = _asyncio_lock.Lock()


async def get_npu_search_engine() -> NPUSemanticSearch:
    """Get the global NPU semantic search engine instance (thread-safe)."""
    global _npu_search_engine
    if _npu_search_engine is None:
        async with _npu_search_engine_lock:
            # Double-check after acquiring lock
            if _npu_search_engine is None:
                _npu_search_engine = NPUSemanticSearch()
                await _npu_search_engine.initialize()
    return _npu_search_engine
