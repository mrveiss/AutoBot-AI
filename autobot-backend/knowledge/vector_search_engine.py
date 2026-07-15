# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
VectorSearchEngine — single unified entry point for all vector/semantic search.

Issue #3828: Consolidate 6 vector search implementations under one engine.

Hardware dispatch priority (when hardware_backend="auto"):
  NPU  (config.feature.npu_enabled)
  GPU  (FAISS_GPU_AVAILABLE via gpu_vector_search)
  CPU  (ChromaDB / basic KB fallback — always available)

Canonical result type: SearchResult dataclass (text, score, metadata, source).

All callers should import from this module:
    from knowledge.vector_search_engine import get_vector_search_engine, SearchResult
from autobot_shared.logging_manager import get_logger
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """Canonical search result returned by VectorSearchEngine.

    Fields
    ------
    text     : document text / content
    score    : similarity score in [0, 1] (higher == more similar)
    metadata : arbitrary key/value metadata from the document store
    source   : logical source identifier (e.g. fact_id, doc_id, file path)
    """

    text: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = ""


# ---------------------------------------------------------------------------
# Hardware availability helpers
# ---------------------------------------------------------------------------

# Lazy-import flags — evaluated once at first engine construction.
_FAISS_GPU_AVAILABLE: bool | None = None
_FAISS_AVAILABLE: bool | None = None


def _check_faiss_flags() -> tuple[bool, bool]:
    """Return (faiss_available, faiss_gpu_available), evaluated once."""
    global _FAISS_AVAILABLE, _FAISS_GPU_AVAILABLE
    if _FAISS_AVAILABLE is None:
        try:
            from utils.gpu_vector_search import (  # noqa: PLC0415
                FAISS_AVAILABLE,
                FAISS_GPU_AVAILABLE,
            )

            _FAISS_AVAILABLE = bool(FAISS_AVAILABLE)
            _FAISS_GPU_AVAILABLE = bool(FAISS_GPU_AVAILABLE)
        except Exception:
            _FAISS_AVAILABLE = False
            _FAISS_GPU_AVAILABLE = False
    return _FAISS_AVAILABLE, _FAISS_GPU_AVAILABLE


def _npu_enabled() -> bool:
    """Return True when NPU subsystem is enabled in feature flags."""
    try:
        return bool(config.feature.npu_enabled)
    except Exception:
        return False


def _gpu_available() -> bool:
    """Return True when FAISS-GPU is available."""
    _, gpu = _check_faiss_flags()
    return gpu


# ---------------------------------------------------------------------------
# Hardware-backend adapters
# ---------------------------------------------------------------------------


class _NPUBackend:
    """Thin adapter over NPUSemanticSearch for use by VectorSearchEngine."""

    def __init__(self) -> None:
        self._engine: Any | None = None

    async def _get_engine(self) -> Any:
        if self._engine is None:
            from npu_semantic_search import get_npu_search_engine  # noqa: PLC0415

            self._engine = await get_npu_search_engine()
        return self._engine

    async def search(
        self,
        query: str,
        top_k: int,
        filters: Dict[str, Any] | None,
    ) -> List[SearchResult]:
        engine = await self._get_engine()
        npu_results, _ = await engine.search(
            query=query,
            similarity_top_k=top_k,
            filters=filters,
            enable_npu_acceleration=True,
        )
        return [
            SearchResult(
                text=r.content,
                score=r.score,
                metadata=r.metadata,
                source=r.doc_id,
            )
            for r in npu_results
        ]


class _GPUBackend:
    """Thin adapter over HybridVectorSearch for use by VectorSearchEngine.

    The GPU backend requires an already-generated query embedding. This adapter
    generates that embedding via the NPU-fallback path before delegating to
    HybridVectorSearch so the caller always passes plain text queries.
    """

    def __init__(self) -> None:
        self._hybrid: Any | None = None

    async def _get_hybrid(self) -> Any:
        if self._hybrid is None:
            from utils.gpu_vector_search import (  # noqa: PLC0415
                VectorSearchConfig,
                get_hybrid_vector_search,
            )

            config_obj = VectorSearchConfig(use_gpu=True)
            self._hybrid = await get_hybrid_vector_search(config=config_obj)
        return self._hybrid

    async def _generate_embedding(self, query: str):
        """Generate a query embedding via the canonical NPU-fallback path.

        Issue #5105: Calls ``services.npu_client.generate_embedding_with_fallback``
        directly — same pattern as ``knowledge/memory_graph/query_processor.py``.
        """
        from services.npu_client import (  # noqa: PLC0415
            generate_embedding_with_fallback,
        )

        return await generate_embedding_with_fallback(query)

    async def search(
        self,
        query: str,
        top_k: int,
        filters: Dict[str, Any] | None,
    ) -> List[SearchResult]:
        import numpy as np  # noqa: PLC0415

        hybrid = await self._get_hybrid()
        embedding = await self._generate_embedding(query)
        embedding_array = np.array(embedding, dtype=np.float32)

        gpu_results, _ = await hybrid.search(
            query_embedding=embedding_array,
            top_k=top_k,
            metadata_filter=filters,
        )
        return [
            SearchResult(
                text=r.content or "",
                score=r.score,
                metadata=r.metadata,
                source=r.doc_id,
            )
            for r in gpu_results
        ]


class _CPUBackend:
    """CPU/ChromaDB fallback adapter over the canonical knowledge base."""

    async def search(
        self,
        query: str,
        top_k: int,
        filters: Dict[str, Any] | None,
    ) -> List[SearchResult]:
        from knowledge import get_knowledge_base  # noqa: PLC0415

        kb = await get_knowledge_base()
        raw = await kb.search(query=query, top_k=top_k, filters=filters)
        return [
            SearchResult(
                text=r.get("content", ""),
                score=r.get("score", 0.0),
                metadata=r.get("metadata", {}),
                source=(r.get("metadata", {}).get("fact_id") or r.get("node_id", "")),
            )
            for r in raw
        ]


# ---------------------------------------------------------------------------
# VectorSearchEngine
# ---------------------------------------------------------------------------

# Reranker callable type: (query: str, results: List[SearchResult]) -> Awaitable[List[SearchResult]]
RerankerCallable = Callable[[str, List[SearchResult]], Any]


class VectorSearchEngine:
    """Unified vector search engine with hardware dispatch and optional reranking.

    Usage
    -----
    engine = await get_vector_search_engine()
    results = await engine.search("how to deploy docker", top_k=10)

    Hardware selection
    ------------------
    hardware_backend="auto"  -> NPU > GPU > CPU (based on availability flags)
    hardware_backend="npu"   -> force NPU path
    hardware_backend="gpu"   -> force GPU path
    hardware_backend="cpu"   -> force CPU/ChromaDB path
    """

    def __init__(self) -> None:
        self._npu = _NPUBackend()
        self._gpu = _GPUBackend()
        self._cpu = _CPUBackend()

    def _select_backend(self, hardware_backend: str) -> Any:
        """Return the appropriate backend object."""
        if hardware_backend == "npu":
            return self._npu
        if hardware_backend == "gpu":
            return self._gpu
        if hardware_backend == "cpu":
            return self._cpu

        # "auto": NPU > GPU > CPU
        # Note: IVFPQ activation for large collections (>ivfpq_min_vectors) is handled
        # inside FAISSIVFPQBuilder.build_or_load(), called from GPUVectorIndex
        # initialization when IndexType.IVF_PQ is selected via VectorSearchConfig.
        if _npu_enabled():
            logger.debug("VectorSearchEngine: auto-selected NPU backend")
            return self._npu
        if _gpu_available():
            logger.debug("VectorSearchEngine: auto-selected GPU backend")
            return self._gpu
        logger.debug("VectorSearchEngine: auto-selected CPU backend")
        return self._cpu

    async def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Dict[str, Any] | None = None,
        hardware_backend: str = "auto",
        reranker: RerankerCallable | None = None,
    ) -> List[SearchResult]:
        """Execute vector search and return standardized SearchResult list.

        Parameters
        ----------
        query            : plain-text search query
        top_k            : maximum number of results to return
        filters          : optional metadata pre-filter dict (passed to backend)
        hardware_backend : "auto" | "npu" | "gpu" | "cpu"
        reranker         : optional async callable(query, results) -> results

        Returns
        -------
        List[SearchResult] sorted by score descending.
        """
        if not query.strip():
            return []

        backend = self._select_backend(hardware_backend)
        backend_name = type(backend).__name__

        try:
            results = await backend.search(query=query, top_k=top_k, filters=filters)
        except Exception as exc:
            logger.warning(
                "VectorSearchEngine: backend %s failed (%s), falling back to CPU",
                backend_name,
                exc,
            )
            try:
                results = await self._cpu.search(query=query, top_k=top_k, filters=filters)
            except Exception as cpu_exc:
                logger.error("VectorSearchEngine: CPU fallback also failed: %s", cpu_exc)
                return []

        if reranker is not None and results:
            try:
                results = await reranker(query, results)
            except Exception as rerr:
                logger.warning("VectorSearchEngine: reranker raised %s, skipping rerank", rerr)

        # Guarantee descending score order regardless of backend
        results.sort(key=lambda r: r.score, reverse=True)
        logger.info(
            "VectorSearchEngine.search: query=%r top_k=%d backend=%s results=%d",
            query[:60],
            top_k,
            backend_name,
            len(results),
        )
        return results


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: VectorSearchEngine | None = None
_lock = asyncio.Lock()


async def get_vector_search_engine() -> VectorSearchEngine:
    """Return the process-wide VectorSearchEngine singleton (lazy, thread-safe)."""
    global _instance
    if _instance is None:
        async with _lock:
            if _instance is None:
                _instance = VectorSearchEngine()
                logger.info("VectorSearchEngine singleton created")
    return _instance
