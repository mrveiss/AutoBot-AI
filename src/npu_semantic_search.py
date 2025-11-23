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
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
import numpy as np

from src.utils.http_client import get_http_client
from src.ai_hardware_accelerator import (
    HardwareDevice,
    ProcessingTask,
    TaskComplexity,
    accelerated_embedding_generation,
    get_ai_accelerator,
)

# Import existing AutoBot components
from src.constants.network_constants import NetworkConstants
from src.knowledge_base import KnowledgeBase
from src.unified_config_manager import cfg
from src.utils.chromadb_client import get_chromadb_client
from src.utils.logging_manager import get_llm_logger

# Import ChromaDB for multi-modal vector storage
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

logger = get_llm_logger("npu_semantic_search")


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


class NPUSemanticSearch:
    """
    NPU-Enhanced Semantic Search Engine for AutoBot.

    Provides intelligent hardware acceleration for semantic search operations:
    - NPU for lightweight embedding generation and similarity computation
    - GPU for heavy document processing and complex models
    - CPU fallback for reliability
    """

    def __init__(self):
        self.knowledge_base = None
        self.ai_accelerator = None
        self.search_cache = {}  # Simple LRU cache for repeated queries
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
                "NPU Worker configuration missing: AUTOBOT_NPU_WORKER_HOST and AUTOBOT_NPU_WORKER_PORT environment variables must be set"
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
        }

    async def initialize(self):
        """Initialize NPU semantic search engine."""
        logger.info("🚀 Initializing NPU Semantic Search Engine")

        # Initialize dependencies
        self.ai_accelerator = await get_ai_accelerator()
        self.knowledge_base = KnowledgeBase()

        # Wait for knowledge base initialization
        max_wait = 30  # seconds
        wait_time = 0
        while not self.knowledge_base.vector_store and wait_time < max_wait:
            await asyncio.sleep(1)
            wait_time += 1

        if self.knowledge_base.vector_store:
            logger.info("✅ Knowledge base vector store ready")
        else:
            logger.warning(
                "⚠️ Knowledge base vector store not ready, using basic search"
            )

        # Initialize ChromaDB for multi-modal storage
        await self._initialize_chromadb()

        # Test NPU connectivity
        await self._test_npu_connectivity()

        logger.info("✅ NPU Semantic Search Engine initialized")

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
            logger.warning(f"⚠️ NPU Worker connectivity test failed: {e}")

    async def enhanced_search(
        self,
        query: str,
        similarity_top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        enable_npu_acceleration: bool = True,
        force_device: Optional[HardwareDevice] = None,
    ) -> Tuple[List[SearchResult], SearchMetrics]:
        """
        Perform NPU-enhanced semantic search.

        Args:
            query: Search query string
            similarity_top_k: Number of results to return
            filters: Optional metadata filters
            enable_npu_acceleration: Whether to use NPU acceleration
            force_device: Force specific device for testing

        Returns:
            Tuple of (search_results, performance_metrics)
        """
        start_time = time.time()

        if not query.strip():
            return [], SearchMetrics(
                total_documents_searched=0,
                embedding_generation_time_ms=0,
                similarity_computation_time_ms=0,
                total_search_time_ms=0,
                device_used="none",
                hardware_utilization={},
            )

        logger.info(f"🔍 Enhanced search: '{query[:50]}...' (top_k={similarity_top_k})")

        # Check cache first
        cache_key = self._generate_cache_key(query, similarity_top_k, filters)
        cached_result = self._get_cached_result(cache_key)
        if cached_result:
            logger.info("⚡ Returning cached search result")
            return cached_result

        try:
            # Step 1: Generate query embedding with optimal hardware
            embedding_start = time.time()
            query_embedding, embedding_device = (
                await self._generate_optimized_embedding(
                    query, enable_npu_acceleration, force_device
                )
            )
            embedding_time = (time.time() - embedding_start) * 1000

            # Step 2: Perform vector similarity search
            search_start = time.time()

            if self.knowledge_base.vector_store and self.knowledge_base.vector_index:
                # Use existing vector store with enhanced processing
                results = await self._vector_similarity_search(
                    query_embedding, similarity_top_k, filters, embedding_device
                )
            else:
                # Fallback to basic search
                logger.warning(
                    "Vector store not available, using basic search fallback"
                )
                basic_results = await self.knowledge_base.search(
                    query, similarity_top_k, filters, "text"
                )
                results = [
                    SearchResult(
                        content=r["content"],
                        metadata=r["metadata"],
                        score=r["score"],
                        doc_id=r.get("doc_id", str(uuid.uuid4())),
                        device_used="cpu_fallback",
                        processing_time_ms=0,
                        embedding_model="basic_search",
                    )
                    for r in basic_results
                ]

            search_time = (time.time() - search_start) * 1000
            total_time = (time.time() - start_time) * 1000

            # Create performance metrics
            metrics = SearchMetrics(
                total_documents_searched=len(results),
                embedding_generation_time_ms=embedding_time,
                similarity_computation_time_ms=search_time,
                total_search_time_ms=total_time,
                device_used=embedding_device,
                hardware_utilization=await self._get_hardware_utilization(),
            )

            # Cache the results
            self._cache_result(cache_key, (results, metrics))

            logger.info(
                f"✅ Search completed: {len(results)} results in {total_time:.2f}ms "
                f"(embedding: {embedding_time:.2f}ms, search: {search_time:.2f}ms) "
                f"using {embedding_device}"
            )

            return results, metrics

        except Exception as e:
            logger.error(f"❌ Enhanced search failed: {e}")
            # Fallback to basic knowledge base search
            basic_results = await self.knowledge_base.search(
                query, similarity_top_k, filters, "auto"
            )

            fallback_results = [
                SearchResult(
                    content=r["content"],
                    metadata=r["metadata"],
                    score=r["score"],
                    doc_id=r.get("doc_id", str(uuid.uuid4())),
                    device_used="fallback",
                    processing_time_ms=0,
                    embedding_model="fallback",
                )
                for r in basic_results
            ]

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

    async def _generate_optimized_embedding(
        self, text: str, enable_npu: bool, force_device: Optional[HardwareDevice]
    ) -> Tuple[np.ndarray, str]:
        """Generate embedding using optimal hardware."""
        try:
            # Use AI accelerator for optimal embedding generation
            if force_device:
                embedding = await accelerated_embedding_generation(text, force_device)
                return embedding, force_device.value
            elif enable_npu:
                # Let the accelerator choose optimal device
                embedding = await accelerated_embedding_generation(text)
                return embedding, "auto_selected"
            else:
                # Use GPU/CPU fallback through semantic chunker
                from src.utils.semantic_chunker import get_semantic_chunker

                chunker = get_semantic_chunker()
                await chunker._initialize_model()

                embeddings = await chunker._compute_sentence_embeddings_async([text])
                return embeddings[0], "gpu_fallback"

        except Exception as e:
            logger.warning(
                f"⚠️ Optimized embedding generation failed: {e}, using fallback"
            )

            # Final fallback - basic embedding
            from src.utils.semantic_chunker import get_semantic_chunker

            chunker = get_semantic_chunker()

            # Use sync method as final fallback
            embeddings = chunker._compute_sentence_embeddings([text])
            return embeddings[0], "cpu_final_fallback"

    async def _vector_similarity_search(
        self,
        query_embedding: np.ndarray,
        top_k: int,
        filters: Optional[Dict[str, Any]],
        device_used: str,
    ) -> List[SearchResult]:
        """Perform vector similarity search using the knowledge base."""
        try:
            # Convert to list for LlamaIndex compatibility
            query_embedding_list = query_embedding.tolist()

            # Use LlamaIndex retriever for vector search
            retriever = self.knowledge_base.vector_index.as_retriever(
                similarity_top_k=top_k, vector_store_query_mode="default"
            )

            # Perform retrieval using the embedding
            # Note: LlamaIndex typically handles embedding internally,
            # but we can use the query engine approach
            query_engine = self.knowledge_base.vector_index.as_query_engine(
                similarity_top_k=top_k, response_mode="no_text"
            )

            # For now, use text query and let LlamaIndex handle embedding
            # TODO: Enhance to use our pre-computed embedding
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
                        processing_time_ms=0,  # Individual node processing time
                        embedding_model="enhanced_model",
                    )
                    results.append(result)

            return results

        except Exception as e:
            logger.error(f"❌ Vector similarity search failed: {e}")
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
            logger.warning(f"⚠️ Could not get hardware utilization: {e}")

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
        return hashlib.md5(cache_string.encode()).hexdigest()

    def _get_cached_result(
        self, cache_key: str
    ) -> Optional[Tuple[List[SearchResult], SearchMetrics]]:
        """Get cached search result if available and not expired."""
        if cache_key in self.search_cache:
            cached_data, timestamp = self.search_cache[cache_key]

            if time.time() - timestamp < self.cache_ttl_seconds:
                return cached_data
            else:
                # Remove expired cache entry
                del self.search_cache[cache_key]

        return None

    def _cache_result(
        self, cache_key: str, result: Tuple[List[SearchResult], SearchMetrics]
    ):
        """Cache search result with TTL."""
        # Implement simple LRU eviction
        if len(self.search_cache) >= self.cache_max_size:
            # Remove oldest entry
            oldest_key = min(
                self.search_cache.keys(), key=lambda k: self.search_cache[k][1]
            )
            del self.search_cache[oldest_key]

        self.search_cache[cache_key] = (result, time.time())

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
            device_results = []

            logger.info(f"🔧 Testing device: {device.value}")

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
                                "embedding_time_ms": metrics.embedding_generation_time_ms,
                                "search_time_ms": metrics.similarity_computation_time_ms,
                                "device_used": metrics.device_used,
                            }
                        )

                    except Exception as e:
                        logger.error(f"❌ Benchmark failed for {device.value}: {e}")
                        device_results.append(
                            {"query": query, "iteration": iteration, "error": str(e)}
                        )

            results["device_performance"][device.value] = device_results

        # Calculate summary statistics
        for device, device_results in results["device_performance"].items():
            successful_runs = [r for r in device_results if "error" not in r]

            if successful_runs:
                avg_time = sum(r["total_time_ms"] for r in successful_runs) / len(
                    successful_runs
                )
                avg_embedding_time = sum(
                    r["embedding_time_ms"] for r in successful_runs
                ) / len(successful_runs)
                avg_search_time = sum(
                    r["search_time_ms"] for r in successful_runs
                ) / len(successful_runs)

                results["summary"][device] = {
                    "average_total_time_ms": avg_time,
                    "average_embedding_time_ms": avg_embedding_time,
                    "average_search_time_ms": avg_search_time,
                    "success_rate": len(successful_runs) / len(device_results) * 100,
                    "total_runs": len(device_results),
                }
            else:
                results["summary"][device] = {
                    "success_rate": 0,
                    "total_runs": len(device_results),
                    "error": "All runs failed",
                }

        logger.info("✅ Search performance benchmark completed")
        return results

    async def get_search_statistics(self) -> Dict[str, Any]:
        """Get comprehensive search engine statistics."""
        return {
            "cache_stats": {
                "cache_size": len(self.search_cache),
                "cache_max_size": self.cache_max_size,
                "cache_ttl_seconds": self.cache_ttl_seconds,
            },
            "configuration": {
                "batch_size_npu": self.batch_size_npu,
                "batch_size_gpu": self.batch_size_gpu,
                "similarity_threshold": self.similarity_threshold,
                "npu_worker_url": self.npu_worker_url,
            },
            "hardware_status": (
                await self._get_hardware_utilization() if self.ai_accelerator else {}
            ),
            "knowledge_base_ready": (
                self.knowledge_base.vector_store is not None
                if self.knowledge_base
                else False
            ),
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
                    logger.info(
                        f"✅ Created new ChromaDB collection: {collection_name}"
                    )

                self.collections[modality] = collection

            logger.info("✅ ChromaDB multi-modal collections initialized")

        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self.chroma_client = None

    async def store_multimodal_embedding(
        self,
        content: Any,
        modality: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> bool:
        """
        Store multi-modal content with embeddings in appropriate ChromaDB collection.

        Args:
            content: The content to store (text, image path, audio data, etc.)
            modality: Type of content ('text', 'image', 'audio')
            metadata: Additional metadata to store
            doc_id: Document ID (auto-generated if not provided)

        Returns:
            bool: True if storage successful, False otherwise
        """
        if not self.chroma_client or modality not in self.collections:
            logger.warning(
                f"ChromaDB not available or unsupported modality: {modality}"
            )
            return False

        try:
            # Generate embedding using enhanced accelerated_embedding_generation
            embedding = await accelerated_embedding_generation(
                content=content, modality=modality, preferred_device=HardwareDevice.GPU
            )

            # Prepare metadata
            doc_metadata = {
                "modality": modality,
                "timestamp": time.time(),
                "content_preview": (
                    str(content)[:200]
                    if isinstance(content, str)
                    else f"{modality}_content"
                ),
                **(metadata or {}),
            }

            # Generate document ID if not provided
            if doc_id is None:
                doc_id = f"{modality}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

            # Store in appropriate collection
            collection = self.collections[modality]
            collection.add(
                embeddings=[embedding.tolist()],
                metadatas=[doc_metadata],
                documents=[str(content)],
                ids=[doc_id],
            )

            # Also store in fused collection if we have multi-modal fusion capability
            if modality != "multimodal" and self.ai_accelerator:
                try:
                    # Generate fused embedding (this would use the fusion engine)
                    fused_metadata = {
                        **doc_metadata,
                        "source_modality": modality,
                        "fusion_type": "single_modal_to_unified",
                    }

                    multimodal_collection = self.collections.get("multimodal")
                    if multimodal_collection:
                        multimodal_collection.add(
                            embeddings=[
                                embedding.tolist()
                            ],  # Use same embedding for now
                            metadatas=[fused_metadata],
                            documents=[str(content)],
                            ids=[f"fused_{doc_id}"],
                        )

                except Exception as e:
                    logger.warning(f"Failed to store in multimodal collection: {e}")

            logger.info(f"✅ Stored {modality} content with ID: {doc_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to store multimodal embedding: {e}")
            return False

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
            # Generate query embedding
            query_embedding = await accelerated_embedding_generation(
                content=query,
                modality=query_modality,
                preferred_device=HardwareDevice.GPU,
            )

            # Determine target modalities
            if target_modalities is None:
                target_modalities = ["text", "image", "audio", "multimodal"]

            # Use configured threshold if not provided
            threshold = similarity_threshold or self.similarity_threshold

            results = {}

            # Search across specified modalities
            for modality in target_modalities:
                if modality not in self.collections:
                    continue

                try:
                    collection = self.collections[modality]

                    # Perform similarity search
                    search_results = collection.query(
                        query_embeddings=[query_embedding.tolist()],
                        n_results=limit,
                        include=["metadatas", "documents", "distances"],
                    )

                    # Convert to MultiModalSearchResult objects
                    modality_results = []
                    if search_results["ids"] and len(search_results["ids"][0]) > 0:
                        for i in range(len(search_results["ids"][0])):
                            # Convert distance to similarity score (ChromaDB uses L2 distance)
                            distance = search_results["distances"][0][i]
                            similarity = 1.0 / (
                                1.0 + distance
                            )  # Convert distance to similarity

                            if similarity >= threshold:
                                metadata = search_results["metadatas"][0][i]
                                result = MultiModalSearchResult(
                                    content=search_results["documents"][0][i],
                                    modality=modality,
                                    metadata=metadata,
                                    score=similarity,
                                    doc_id=search_results["ids"][0][i],
                                    source_modality=metadata.get("source_modality"),
                                    fusion_confidence=metadata.get("fusion_confidence"),
                                )
                                modality_results.append(result)

                    results[modality] = modality_results
                    logger.info(
                        f"Found {len(modality_results)} results in {modality} collection"
                    )

                except Exception as e:
                    logger.error(f"Search failed for modality {modality}: {e}")
                    results[modality] = []

            return results

        except Exception as e:
            logger.error(f"Cross-modal search failed: {e}")
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

        logger.info(f"🎯 Search engine optimized for {workload_type}")
        return optimizations


# Global instance
_npu_search_engine = None


async def get_npu_search_engine() -> NPUSemanticSearch:
    """Get the global NPU semantic search engine instance."""
    global _npu_search_engine
    if _npu_search_engine is None:
        _npu_search_engine = NPUSemanticSearch()
        await _npu_search_engine.initialize()
    return _npu_search_engine
