#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU-Enhanced Semantic Search for AutoBot
Integrates Intel NPU acceleration with ChromaDB and Redis vector store
"""

import asyncio
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import aiohttp
import numpy as np

from ai_hardware_accelerator import (
    HardwareDevice,
    accelerated_embedding_generation,
    get_ai_accelerator,
)
from autobot_shared.http_client import get_http_client
from autobot_shared.logging_manager import get_llm_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_config import config
from config import cfg

# Import existing AutoBot components
from constants.threshold_constants import TimingConstants
from knowledge.backends import get_default_client
from knowledge.embedding_cache import get_embedding_cache
from knowledge_base import KnowledgeBase

# Issue #387: GPU-accelerated vector search
from utils.gpu_vector_search import (
    FAISS_AVAILABLE,
    FAISS_GPU_AVAILABLE,
    HybridVectorSearch,
    VectorSearchConfig,
    get_hybrid_vector_search,
)

# Import ChromaDB for multi-modal vector storage
try:
    pass

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

logger = get_llm_logger("npu_semantic_search")


# #8159: L2 embedding cache TTL. Override via AUTOBOT_NPU_EMBEDDING_CACHE_TTL (seconds).
# Default 3600s (1h) — embeddings are stable within a model version.
def _resolve_npu_embedding_cache_ttl() -> int:
    """Return TTL seconds for emb:* Redis L2 cache keys."""
    _default = 3600
    raw = os.environ.get("AUTOBOT_NPU_EMBEDDING_CACHE_TTL")
    if raw is None:
        return _default
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "AUTOBOT_NPU_EMBEDDING_CACHE_TTL=%r is not an integer; falling back to %ds (1h)",
            raw,
            _default,
        )
        return _default
    if value <= 0:
        logger.warning(
            "AUTOBOT_NPU_EMBEDDING_CACHE_TTL=%d is not positive; falling back to %ds (1h)",
            value,
            _default,
        )
        return _default
    return value


_NPU_EMBEDDING_CACHE_TTL: int = _resolve_npu_embedding_cache_ttl()

# Issue #8154: Search result cache — resolved from SSOT config with env-var overrides.
# AUTOBOT_SEARCH_RESULT_CACHE_SIZE (default 10000) and AUTOBOT_SEARCH_RESULT_CACHE_TTL (default 1800s).
_SEARCH_CACHE_MAX_SIZE: int = config.cache.l1.search_result_cache_max_size
_SEARCH_CACHE_TTL: int = config.cache.l1.search_result_cache_ttl

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
    source_modality: str | None = None  # Original modality for fused embeddings
    fusion_confidence: float | None = None


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
        self.cache_max_size = _SEARCH_CACHE_MAX_SIZE
        self.cache_ttl_seconds = _SEARCH_CACHE_TTL

        # Performance optimization settings
        self.batch_size_npu = 32  # Optimal NPU batch size
        self.batch_size_gpu = 128  # Optimal GPU batch size
        self.similarity_threshold = 0.7  # Minimum similarity for results

        # NPU Worker configuration

        npu_worker_host = config.npu_worker_host
        npu_worker_port = config.npu_worker_port
        if not npu_worker_host or not npu_worker_port:
            raise ValueError(
                "NPU Worker configuration missing: AUTOBOT_NPU_WORKER_HOST and "
                "AUTOBOT_NPU_WORKER_PORT environment variables must be set"
            )
        self.npu_worker_url = cfg.get("npu_worker.url", f"http://{npu_worker_host}:{npu_worker_port}")

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
        self.hybrid_search: HybridVectorSearch | None = None
        self.use_gpu_search = cfg.get("vector_search.use_gpu", True)

        # Issue #8159: L1/L2 embedding cache hit counters (per-worker, reset on restart)
        self._l1_hits: int = 0
        self._l2_hits: int = 0
        self._cache_misses: int = 0

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
            logger.warning("⚠️ Knowledge base vector store not ready, using basic search")

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

            self.hybrid_search = await get_hybrid_vector_search(chromadb_client=self.chroma_client, config=config)

            stats = self.hybrid_search.get_stats()
            backend = stats.get("faiss_index", {}).get("backend", "unknown")
            gpu_available = stats.get("faiss_index", {}).get("gpu_available", False)

            if gpu_available:
                logger.info(f"✅ GPU-accelerated hybrid search initialized (backend={backend})")
            else:
                logger.info(f"✅ Hybrid search initialized with CPU fallback (backend={backend})")

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
                    logger.info(f"✅ NPU Worker connected - NPU Available: {health_data.get('npu_available', False)}")
                else:
                    logger.warning(f"⚠️ NPU Worker health check failed: {response.status}")
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

    def _convert_basic_results(self, basic_results: List[Dict], device_label: str) -> List[SearchResult]:
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
        filters: Dict[str, Any] | None,
        embedding_device: str,
    ) -> List[SearchResult]:
        """Perform vector similarity search with fallback."""
        if self.knowledge_base.vector_store and self.knowledge_base.vector_index:
            return await self._vector_similarity_search(query_embedding, similarity_top_k, filters, embedding_device)

        logger.warning("Vector store not available, using basic search fallback")
        basic_results = await self.knowledge_base.search(query, similarity_top_k, filters, "text")
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
        filters: Dict[str, Any] | None,
        start_time: float,
    ) -> Tuple[List[SearchResult], SearchMetrics]:
        """Handle search error with fallback."""
        logger.error("❌ Enhanced search failed: %s", error)
        basic_results = await self.knowledge_base.search(query, similarity_top_k, filters, "auto")
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
        filters: Dict[str, Any] | None,
        enable_npu_acceleration: bool,
        force_device: HardwareDevice | None,
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
        results = await self._perform_vector_search(query, query_embedding, similarity_top_k, filters, embedding_device)
        search_time = (time.time() - search_start) * 1000
        total_time = (time.time() - start_time) * 1000

        metrics = await self._create_search_metrics(results, embedding_time, search_time, total_time, embedding_device)
        self._cache_result(cache_key, (results, metrics))
        self._log_search_completion(results, total_time, embedding_time, search_time, embedding_device)
        return results, metrics

    async def enhanced_search(
        self,
        query: str,
        similarity_top_k: int = 10,
        filters: Dict[str, Any] | None = None,
        enable_npu_acceleration: bool = True,
        force_device: HardwareDevice | None = None,
    ) -> Tuple[List[SearchResult], SearchMetrics]:
        """Perform NPU-enhanced semantic search. Issue #281, #620."""
        start_time = time.time()

        if not query.strip():
            return [], self._create_empty_metrics()

        logger.info("🔍 Enhanced search: '%s...' (top_k=%s)", query[:50], similarity_top_k)

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
            return await self._handle_search_error(e, query, similarity_top_k, filters, start_time)

    async def _generate_embedding_with_device(
        self, text: str, enable_npu: bool, force_device: HardwareDevice | None
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

        from utils.semantic_chunker import get_semantic_chunker

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
        from utils.semantic_chunker import get_semantic_chunker

        chunker = get_semantic_chunker()
        embeddings = chunker._compute_sentence_embeddings([text])
        return embeddings[0], "cpu_final_fallback"

    async def _l2_cache_get(self, text: str) -> "np.ndarray | None":
        """Check Redis L2 embedding cache. Issue #8159."""
        redis = get_async_redis_client()
        if redis is None:
            return None
        try:
            key = f"emb:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"
            cached = await redis.get(key)
            if cached:
                return np.frombuffer(cached, dtype=np.float32).copy()
        except Exception as exc:
            logger.debug("L2 cache get failed (non-fatal): %s", exc)
        return None

    async def _l2_cache_set(self, text: str, embedding: np.ndarray) -> None:
        """Store embedding in Redis L2 cache. Issue #8159."""
        redis = get_async_redis_client()
        if redis is None:
            return
        try:
            key = f"emb:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"
            await redis.set(key, embedding.astype(np.float32).tobytes(), ex=_NPU_EMBEDDING_CACHE_TTL)
        except Exception as exc:
            logger.debug("L2 cache set failed (non-fatal): %s", exc)

    async def _generate_optimized_embedding(
        self, text: str, enable_npu: bool, force_device: HardwareDevice | None
    ) -> Tuple[np.ndarray, str]:
        """Generate embedding using optimal hardware with L1+L2 caching. Issue #65 P0, #8159."""
        # L1: in-process cache (fastest)
        cached_embedding = await self.embedding_cache.get(text)
        if cached_embedding is not None:
            self._l1_hits += 1
            logger.debug("L1 cache hit for query: %s...", text[:50])
            return np.array(cached_embedding), "l1_cached"

        # L2: Redis shared cache (shared across uvicorn workers, survives restarts)
        l2_result = await self._l2_cache_get(text)
        if l2_result is not None:
            self._l2_hits += 1
            logger.debug("L2 cache hit for query: %s...", text[:50])
            await self.embedding_cache.put(text, l2_result.tolist())  # warm L1
            return l2_result, "l2_cached"

        # Miss: generate via NPU/GPU/CPU
        self._cache_misses += 1
        try:
            embedding, device_name = await self._generate_embedding_with_device(text, enable_npu, force_device)
        except Exception as e:
            logger.warning("Optimized embedding generation failed: %s, using fallback", e)
            embedding, device_name = await self._generate_fallback_embedding(text)

        await self.embedding_cache.put(text, embedding.tolist())
        await self._l2_cache_set(text, embedding)
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

    async def _search_with_llamaindex_fallback(self, top_k: int, device_used: str) -> List[SearchResult]:
        """Search using LlamaIndex query engine as fallback. Issue #620.

        Args:
            top_k: Number of results to return
            device_used: Device identifier for result metadata

        Returns:
            List of SearchResult objects
        """
        query_engine = self.knowledge_base.vector_index.as_query_engine(similarity_top_k=top_k, response_mode="no_text")
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
        filters: Dict[str, Any] | None,
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
                    return self._convert_hybrid_results(hybrid_results, hybrid_metrics, device_used)

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

    def _generate_cache_key(self, query: str, top_k: int, filters: Dict[str, Any] | None) -> str:
        """Generate cache key for search results."""
        cache_data = {
            "query": query.strip().lower(),
            "top_k": top_k,
            "filters": filters or {},
        }

        cache_string = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_string.encode(), usedforsecurity=False).hexdigest()

    def _get_cached_result(self, cache_key: str) -> Tuple[List[SearchResult], SearchMetrics] | None:
        """Get cached search result if available and not expired."""
        if cache_key in self.search_results_cache:
            cached_data, timestamp = self.search_results_cache[cache_key]

            if time.time() - timestamp < self.cache_ttl_seconds:
                return cached_data
            else:
                # Remove expired cache entry
                del self.search_results_cache[cache_key]

        return None

    def _cache_result(self, cache_key: str, result: Tuple[List[SearchResult], SearchMetrics]):
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

    def _process_batch_results(self, results: List[Any]) -> List[Tuple[List[SearchResult], SearchMetrics]]:
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

    async def _batch_chromadb_search(
        self,
        miss_indices: List[int],
        miss_embeddings: List[List[float]],
        similarity_top_k: int,
        filters: Dict[str, Any] | None,
        embedding_device: str,
    ) -> Dict[int, Tuple[List[SearchResult], SearchMetrics]]:
        """Issue #8153: run all cache-miss queries against ChromaDB in one call.

        Passes the full list of query embeddings to ``query_batch()`` so the
        underlying ``asyncio.to_thread`` is dispatched once instead of N times.
        Returns a dict mapping original query index → (results, metrics).
        """
        kb_collection = self.collections.get("text")
        if kb_collection is None:
            return {}

        start = time.time()
        try:
            batch_result = await kb_collection.query_batch(
                query_embeddings=miss_embeddings,
                n_results=similarity_top_k,
                where=filters,
            )
        except Exception as exc:
            logger.error("batch_chromadb_search failed: %s", exc)
            return {}

        query_time_ms = (time.time() - start) * 1000
        out: Dict[int, Tuple[List[SearchResult], SearchMetrics]] = {}

        ids_per_query = batch_result.get("ids") or []
        docs_per_query = batch_result.get("documents") or [None] * len(ids_per_query)
        metas_per_query = batch_result.get("metadatas") or [None] * len(ids_per_query)
        dists_per_query = batch_result.get("distances") or [None] * len(ids_per_query)

        for slice_idx, orig_idx in enumerate(miss_indices):
            ids = ids_per_query[slice_idx] if slice_idx < len(ids_per_query) else []
            docs = docs_per_query[slice_idx] if slice_idx < len(docs_per_query) else None
            metas = metas_per_query[slice_idx] if slice_idx < len(metas_per_query) else None
            dists = dists_per_query[slice_idx] if slice_idx < len(dists_per_query) else None

            results: List[SearchResult] = []
            for j, doc_id in enumerate(ids or []):
                score = 1.0 - (dists[j] if dists and j < len(dists) else 0.0)
                results.append(
                    SearchResult(
                        content=(docs[j] if docs and j < len(docs) else ""),
                        metadata=(metas[j] if metas and j < len(metas) else {}),
                        score=score,
                        doc_id=doc_id,
                        device_used=embedding_device,
                        processing_time_ms=query_time_ms / max(len(miss_indices), 1),
                        embedding_model="chromadb",
                    )
                )

            metrics = SearchMetrics(
                total_documents_searched=len(results),
                embedding_generation_time_ms=0.0,
                similarity_computation_time_ms=query_time_ms / max(len(miss_indices), 1),
                total_search_time_ms=query_time_ms / max(len(miss_indices), 1),
                device_used=embedding_device,
                hardware_utilization={},
            )
            out[orig_idx] = (results, metrics)

        return out

    async def batch_search(
        self,
        queries: List[str],
        similarity_top_k: int = 10,
        filters: Dict[str, Any] | None = None,
        enable_npu_acceleration: bool = True,
    ) -> List[Tuple[List[SearchResult], SearchMetrics]]:
        """Batch semantic search — uses a single ChromaDB call for all queries.

        Issue #8153: replaces N individual ``enhanced_search`` dispatches with:
          1. Cache check for all queries (no I/O).
          2. Concurrent embedding generation for cache misses.
          3. One ``query_batch()`` call → one ``asyncio.to_thread`` dispatch.
          4. Per-query result slicing from the batched response.

        Falls back to the individual ``enhanced_search`` path when the knowledge
        base ChromaDB collection is not available.
        """
        if not queries:
            return []

        logger.info("🔍 Batch search: %s queries (top_k=%s)", len(queries), similarity_top_k)

        cache_keys = [self._generate_cache_key(q, similarity_top_k, filters) for q in queries]
        output: List[Tuple[List[SearchResult], SearchMetrics] | None] = [None] * len(queries)

        miss_indices = [i for i, k in enumerate(cache_keys) if self._get_cached_result(k) is None]

        for i in range(len(queries)):
            if i not in miss_indices:
                output[i] = self._get_cached_result(cache_keys[i])

        if not miss_indices:
            logger.info("✅ Batch search: all %s queries from cache", len(queries))
            return output  # type: ignore[return-value]

        _emb_sem = asyncio.Semaphore(10)

        async def _embed_with_limit(i: int):
            async with _emb_sem:
                return await self._generate_optimized_embedding(queries[i], enable_npu_acceleration, None)

        emb_results = await asyncio.gather(*[_embed_with_limit(i) for i in miss_indices], return_exceptions=True)

        valid_miss_indices: List[int] = []
        valid_embeddings: List[List[float]] = []
        embedding_device = "batch_mixed"

        for pos, (orig_idx, emb_result) in enumerate(zip(miss_indices, emb_results)):
            if isinstance(emb_result, Exception):
                logger.error("Embedding failed for query %s: %s", orig_idx, emb_result)
                output[orig_idx] = self._create_error_search_result()
                continue
            emb_array, device = emb_result
            embedding_device = device
            valid_miss_indices.append(orig_idx)
            valid_embeddings.append(emb_array.tolist() if hasattr(emb_array, "tolist") else list(emb_array))

        if valid_miss_indices and self.collections.get("text") is not None:
            batch_hits = await self._batch_chromadb_search(
                valid_miss_indices, valid_embeddings, similarity_top_k, filters, embedding_device
            )
            for orig_idx, result_tuple in batch_hits.items():
                output[orig_idx] = result_tuple
                self._cache_result(cache_keys[orig_idx], result_tuple)

        uncovered = [i for i in valid_miss_indices if output[i] is None]
        if uncovered:
            semaphore = asyncio.Semaphore(10)

            async def _search_with_semaphore(idx: int) -> Tuple[int, Any]:
                async with semaphore:
                    result = await self.enhanced_search(
                        query=queries[idx],
                        similarity_top_k=similarity_top_k,
                        filters=filters,
                        enable_npu_acceleration=enable_npu_acceleration,
                    )
                    return idx, result

            fallback_results = await asyncio.gather(
                *[_search_with_semaphore(i) for i in uncovered], return_exceptions=True
            )
            for item in fallback_results:
                if isinstance(item, Exception):
                    logger.error("Fallback search failed: %s", item)
                else:
                    idx, result_tuple = item
                    output[idx] = result_tuple

        for i in range(len(queries)):
            if output[i] is None:
                output[i] = self._create_error_search_result()

        logger.info("✅ Batch search completed: %s results", len(output))
        return output  # type: ignore[return-value]

    def _calculate_device_summary(self, device_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate summary statistics for a device's benchmark results (Issue #665: extracted helper)."""
        successful_runs = [r for r in device_results if "error" not in r]

        if not successful_runs:
            return {
                "success_rate": 0,
                "total_runs": len(device_results),
                "error": "All runs failed",
            }

        avg_time = sum(r["total_time_ms"] for r in successful_runs) / len(successful_runs)
        avg_embedding_time = sum(r["embedding_time_ms"] for r in successful_runs) / len(successful_runs)
        avg_search_time = sum(r["search_time_ms"] for r in successful_runs) / len(successful_runs)

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
                        {
                            "query": query,
                            "iteration": iteration,
                            "error": "Benchmark failed",
                        }
                    )

        return device_results

    async def benchmark_search_performance(self, test_queries: List[str], iterations: int = 3) -> Dict[str, Any]:
        """Benchmark search performance across different hardware configurations."""
        logger.info(f"🏃 Starting search performance benchmark with {len(test_queries)} queries")

        results = {
            "test_queries": test_queries,
            "iterations": iterations,
            "device_performance": {},
            "summary": {},
        }

        devices_to_test = [HardwareDevice.NPU, HardwareDevice.GPU, HardwareDevice.CPU]

        for device in devices_to_test:
            device_results = await self._benchmark_single_device(device, test_queries, iterations)
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
        gpu_search_stats = self.hybrid_search.get_stats() if self.hybrid_search else None

        return {
            "embedding_cache_stats": {
                **embedding_stats,  # Issue #65 P0 L1 stats
                # Issue #8159: L1/L2 tier breakdown
                "l1_hits": self._l1_hits,
                "l2_hits": self._l2_hits,
                "misses": self._cache_misses,
            },
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
            "hardware_status": (await self._get_hardware_utilization() if self.ai_accelerator else {}),
            "knowledge_base_ready": (self.knowledge_base.vector_store is not None if self.knowledge_base else False),
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
            self.chroma_client = get_default_client(
                db_path=str(self.chroma_db_path),
                allow_reset=True,
                anonymized_telemetry=False,
            )

            # Issue #8155: build collection metadata with hnsw:space + optional SQ8.
            _quantization_type: str = config.misc.hnsw_quantization_type
            _base_hnsw: Dict[str, Any] = {"hnsw:space": "cosine"}
            if _quantization_type:
                _base_hnsw["hnsw:quantization_type"] = _quantization_type

            # Initialize collections for each modality
            for modality, collection_name in self.collection_names.items():
                try:
                    # Try to get existing collection
                    collection = self.chroma_client.get_collection(name=collection_name)
                    logger.info(f"✅ Loaded existing ChromaDB collection: {collection_name}")
                except ValueError:
                    # Create new collection if it doesn't exist
                    col_meta: Dict[str, Any] = {
                        "modality": modality,
                        "description": f"AutoBot {modality} embeddings",
                        **_base_hnsw,
                    }
                    try:
                        collection = self.chroma_client.create_collection(
                            name=collection_name,
                            metadata=col_meta,
                        )
                    except Exception:
                        # Quantization key rejected by this ChromaDB version — retry without it.
                        fallback_meta = {k: v for k, v in col_meta.items() if k != "hnsw:quantization_type"}
                        collection = self.chroma_client.create_collection(
                            name=collection_name,
                            metadata=fallback_meta,
                        )
                    logger.info(f"✅ Created new ChromaDB collection: {collection_name}")

                self.collections[modality] = collection

            logger.info("✅ ChromaDB multi-modal collections initialized")

        except Exception as e:
            logger.error("Failed to initialize ChromaDB: %s", e)
            self.chroma_client = None

    def _prepare_document_metadata(
        self, content: Any, modality: str, metadata: Dict[str, Any] | None
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
            "content_preview": (str(content)[:200] if isinstance(content, str) else f"{modality}_content"),
            **(metadata or {}),
        }

    def _generate_document_id(self, modality: str, doc_id: str | None) -> str:
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
        metadata: Dict[str, Any] | None = None,
        doc_id: str | None = None,
    ) -> bool:
        """Store multi-modal content with embeddings in ChromaDB collection."""
        if not self.chroma_client or modality not in self.collections:
            logger.warning(f"ChromaDB not available or unsupported modality: {modality}")
            return False

        try:
            # Issue #3290: prefer NPU for embedding generation; fall back to GPU
            embedding = await accelerated_embedding_generation(
                content=content, modality=modality, preferred_device=HardwareDevice.NPU
            )
            doc_metadata = self._prepare_document_metadata(content, modality, metadata)
            doc_id = self._generate_document_id(modality, doc_id)

            self._store_in_collection(modality, embedding, content, doc_metadata, doc_id)
            await self._store_in_multimodal_collection(embedding, content, doc_metadata, doc_id, modality)

            logger.info("✅ Stored %s content with ID: %s", modality, doc_id)
            return True

        except Exception as e:
            logger.error("Failed to store multimodal embedding: %s", e)
            return False

    def _generate_code_doc_id(self, element_type: str, language: str, content_hash: str) -> str:
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
        metadata: Dict[str, Any] | None,
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
        metadata: Dict[str, Any] | None = None,
    ) -> str | None:
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

    def _build_code_search_filter(self, language: str | None, element_type: str | None) -> Dict[str, Any] | None:
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
        language: str | None = None,
        element_type: str | None = None,
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

            results = self._convert_code_search_results(search_results, similarity_threshold)
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
            return {
                "available": False,
                "error": "Failed to retrieve code collection stats",
            }

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
            modality_results = _convert_chroma_results(search_results, modality, threshold)
            logger.info(f"Found {len(modality_results)} results in {modality} collection")
            return modality_results
        except Exception as e:
            logger.error("Search failed for modality %s: %s", modality, e)
            return []

    async def cross_modal_search(
        self,
        query: Any,
        query_modality: str,
        target_modalities: List[str] | None = None,
        limit: int = 10,
        similarity_threshold: float | None = None,
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
                    results[modality] = self._search_single_modality(modality, query_embedding, limit, threshold)

            return results

        except Exception as e:
            logger.error("Cross-modal search failed: %s", e)
            return {}

    async def optimize_for_workload(self, workload_type: str = "balanced") -> Dict[str, Any]:
        """Optimize search engine for specific workload types."""
        optimizations = {}

        if workload_type == "latency_optimized":
            # Optimize for fastest response times
            self.batch_size_npu = 16  # Smaller batches for lower latency
            self.batch_size_gpu = 64
            self.cache_max_size = max(_SEARCH_CACHE_MAX_SIZE, 200)
            self.similarity_threshold = 0.6  # Lower threshold for more results
            optimizations["focus"] = "Optimized for minimum latency"

        elif workload_type == "throughput_optimized":
            # Optimize for maximum throughput
            self.batch_size_npu = 64  # Larger batches
            self.batch_size_gpu = 256
            self.cache_max_size = min(_SEARCH_CACHE_MAX_SIZE, 50)
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
            self.cache_max_size = max(_SEARCH_CACHE_MAX_SIZE, 100)
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


# ---------------------------------------------------------------------------
# Issue #3828: VectorSearchEngine adapter
#
# VectorSearchEngine._NPUBackend calls get_npu_search_engine() directly and
# converts its SearchResult objects to the canonical form.  No changes to
# NPUSemanticSearch internals are required; the bridge lives entirely in
# knowledge/vector_search_engine.py.
# ---------------------------------------------------------------------------
