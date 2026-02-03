# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
NPU-Accelerated Embeddings for Codebase Analytics

Issue #681: Integrates NPU worker for hardware-accelerated embedding generation
in codebase indexing. Uses NPU/GPU offloading with fallback to local semantic
chunker when NPU worker is unavailable.

Usage:
    from backend.api.codebase_analytics.npu_embeddings import (
        generate_codebase_embeddings_batch,
        get_embedding_stats,
    )

    embeddings = await generate_codebase_embeddings_batch(documents)
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Model used for embeddings (must match NPU worker config)
EMBEDDING_MODEL = "nomic-embed-text"

# Batch size for NPU worker requests (larger = more efficient GPU utilization)
NPU_BATCH_SIZE = 100

# Cache TTL for NPU availability check (seconds)
NPU_AVAILABILITY_CACHE_TTL = 30.0

# =============================================================================
# METRICS TRACKING
# =============================================================================


@dataclass
class EmbeddingMetrics:
    """Metrics for tracking embedding generation performance."""

    npu_embeddings: int = 0
    fallback_embeddings: int = 0
    total_time_ms: float = 0.0
    npu_time_ms: float = 0.0
    fallback_time_ms: float = 0.0
    cache_hits: int = 0
    errors: int = 0


_metrics = EmbeddingMetrics()
_metrics_lock = asyncio.Lock()


async def _update_metrics(**kwargs) -> None:
    """Thread-safe metrics update."""
    async with _metrics_lock:
        for key, value in kwargs.items():
            if hasattr(_metrics, key):
                current = getattr(_metrics, key)
                setattr(_metrics, key, current + value)


def get_embedding_stats() -> Dict[str, Any]:
    """
    Get current embedding generation statistics.

    Note: This reads metrics without a lock for performance. Values may be
    slightly inconsistent during concurrent updates, but this is acceptable
    for monitoring/reporting purposes.

    Returns:
        Dict with NPU vs fallback counts, timing, and error stats
    """
    # Take a snapshot of current values (atomic reads for each field)
    npu_count = _metrics.npu_embeddings
    fallback_count = _metrics.fallback_embeddings
    total = npu_count + fallback_count
    npu_pct = (npu_count / total * 100) if total > 0 else 0

    return {
        "total_embeddings": total,
        "npu_embeddings": npu_count,
        "fallback_embeddings": fallback_count,
        "npu_percentage": f"{npu_pct:.1f}%",
        "total_time_ms": _metrics.total_time_ms,
        "npu_time_ms": _metrics.npu_time_ms,
        "fallback_time_ms": _metrics.fallback_time_ms,
        "cache_hits": _metrics.cache_hits,
        "errors": _metrics.errors,
        "avg_time_per_embedding_ms": (
            _metrics.total_time_ms / total if total > 0 else 0
        ),
    }


async def reset_embedding_stats() -> None:
    """
    Reset embedding statistics (for testing/benchmarking).

    Thread-safe: Uses lock to prevent race conditions with concurrent updates.
    """
    global _metrics
    async with _metrics_lock:
        _metrics = EmbeddingMetrics()


# =============================================================================
# NPU CLIENT CACHING
# =============================================================================

_npu_client_cache: Optional[Any] = None
_npu_available_cache: Optional[bool] = None
_npu_cache_timestamp: float = 0.0
_npu_cache_lock = asyncio.Lock()


async def _get_npu_client_cached() -> Tuple[Optional[Any], bool]:
    """
    Get cached NPU client and availability status.

    Issue #681: Caches client instance and availability check to reduce
    overhead on repeated embedding calls during indexing.

    Thread-safe: Uses double-check locking pattern to avoid race conditions
    while minimizing lock contention.

    Returns:
        Tuple of (client, is_available)
    """
    global _npu_client_cache, _npu_available_cache, _npu_cache_timestamp

    current_time = time.time()

    # Fast path: Check if cache is still valid (read-only, no lock needed)
    if (
        _npu_client_cache is not None
        and _npu_available_cache is not None
        and (current_time - _npu_cache_timestamp) < NPU_AVAILABILITY_CACHE_TTL
    ):
        return _npu_client_cache, _npu_available_cache

    # Slow path: Refresh cache with lock to prevent concurrent refreshes
    async with _npu_cache_lock:
        # Double-check after acquiring lock (another coroutine may have refreshed)
        current_time = time.time()
        if (
            _npu_client_cache is not None
            and _npu_available_cache is not None
            and (current_time - _npu_cache_timestamp) < NPU_AVAILABILITY_CACHE_TTL
        ):
            return _npu_client_cache, _npu_available_cache

        # Refresh cache
        try:
            from backend.services.npu_client import get_npu_client

            _npu_client_cache = get_npu_client()
            _npu_available_cache = await _npu_client_cache.is_available()
            _npu_cache_timestamp = current_time

            if _npu_available_cache:
                logger.info("NPU worker available for codebase embeddings")
            else:
                logger.info("NPU worker unavailable, will use fallback")

            return _npu_client_cache, _npu_available_cache

        except Exception as e:
            logger.debug("Failed to get NPU client: %s", e)
            _npu_available_cache = False
            _npu_cache_timestamp = current_time
            return None, False


# =============================================================================
# FALLBACK EMBEDDING (LOCAL SEMANTIC CHUNKER)
# =============================================================================

_semantic_chunker_cache: Optional[Any] = None
_semantic_chunker_lock = asyncio.Lock()


async def _get_semantic_chunker():
    """Get or initialize the semantic chunker singleton."""
    global _semantic_chunker_cache

    async with _semantic_chunker_lock:
        if _semantic_chunker_cache is None:
            try:
                from src.utils.semantic_chunker import get_semantic_chunker

                _semantic_chunker_cache = get_semantic_chunker()
                await _semantic_chunker_cache._initialize_model()
                logger.info("Initialized semantic chunker for fallback embeddings")
            except Exception as e:
                logger.warning("Failed to initialize semantic chunker: %s", e)
                return None
        return _semantic_chunker_cache


async def _generate_fallback_embeddings(
    documents: List[str],
    batch_size: int = 100,
) -> List[List[float]]:
    """
    Generate embeddings using local semantic chunker (fallback).

    Issue #681: Used when NPU worker is unavailable. Uses the same
    all-MiniLM-L6-v2 model as the original codebase indexing.

    Args:
        documents: List of document strings to embed
        batch_size: Number of documents per batch

    Returns:
        List of embedding vectors (384 dimensions for MiniLM-L6-v2)
    """
    if not documents:
        return []

    chunker = await _get_semantic_chunker()
    if chunker is None:
        logger.error("Semantic chunker unavailable, returning empty embeddings")
        return [[0.0] * 384 for _ in documents]

    all_embeddings = []
    start_time = time.time()

    for i in range(0, len(documents), batch_size):
        batch_docs = documents[i : i + batch_size]

        try:
            # Use async batch embedding method
            batch_embeddings = await chunker._compute_sentence_embeddings_async(
                batch_docs
            )

            # Convert numpy arrays to lists
            for emb in batch_embeddings:
                all_embeddings.append(
                    emb.tolist() if hasattr(emb, "tolist") else list(emb)
                )

            # Yield to event loop periodically
            if i % (batch_size * 2) == 0:
                await asyncio.sleep(0)

        except Exception as e:
            logger.error("Fallback batch embedding failed at index %d: %s", i, e)
            # Fill with zero embeddings for failed batch
            for _ in batch_docs:
                all_embeddings.append([0.0] * 384)

    elapsed_ms = (time.time() - start_time) * 1000
    await _update_metrics(
        fallback_embeddings=len(documents),
        fallback_time_ms=elapsed_ms,
        total_time_ms=elapsed_ms,
    )

    logger.info(
        "Generated %d fallback embeddings in %.2fms (%.1f docs/sec)",
        len(all_embeddings),
        elapsed_ms,
        len(documents) / (elapsed_ms / 1000) if elapsed_ms > 0 else 0,
    )

    return all_embeddings


# =============================================================================
# NPU-ACCELERATED EMBEDDING
# =============================================================================


async def _generate_npu_embeddings(
    documents: List[str],
    batch_size: int = NPU_BATCH_SIZE,
) -> Optional[List[List[float]]]:
    """
    Generate embeddings using NPU worker with GPU/NPU acceleration.

    Issue #681: Offloads embedding computation to NPU worker (VM2/Windows)
    for hardware-accelerated inference.

    Args:
        documents: List of document strings to embed
        batch_size: Number of documents per batch (default: 100)

    Returns:
        List of embedding vectors if successful, None if failed
    """
    if not documents:
        return []

    client, is_available = await _get_npu_client_cached()
    if not is_available or client is None:
        return None

    all_embeddings: List[List[float]] = []
    start_time = time.time()
    total_docs = len(documents)

    try:
        for i in range(0, total_docs, batch_size):
            batch_docs = documents[i : i + batch_size]

            result = await client.generate_embeddings(
                batch_docs, model_name=EMBEDDING_MODEL, use_cache=True
            )

            if result is None or len(result.embeddings) != len(batch_docs):
                logger.warning("NPU batch returned incomplete results at index %d", i)
                return None

            all_embeddings.extend(result.embeddings)

            # Log progress for large batches
            if total_docs > 100 and (i + batch_size) % (batch_size * 5) == 0:
                progress = min(100, int((i + batch_size) / total_docs * 100))
                logger.info("NPU embedding progress: %d%%", progress)

            # Yield to event loop periodically
            if i % (batch_size * 2) == 0:
                await asyncio.sleep(0)

        elapsed_ms = (time.time() - start_time) * 1000
        await _update_metrics(
            npu_embeddings=len(documents),
            npu_time_ms=elapsed_ms,
            total_time_ms=elapsed_ms,
        )

        logger.info(
            "Generated %d NPU embeddings in %.2fms (%.1f docs/sec)",
            len(all_embeddings),
            elapsed_ms,
            len(documents) / (elapsed_ms / 1000) if elapsed_ms > 0 else 0,
        )

        return all_embeddings

    except Exception as e:
        logger.warning("NPU embedding generation failed: %s", e)
        await _update_metrics(errors=1)
        return None


# =============================================================================
# MAIN API
# =============================================================================


async def generate_codebase_embeddings_batch(
    documents: List[str],
    batch_size: int = NPU_BATCH_SIZE,
) -> List[List[float]]:
    """
    Generate embeddings for codebase documents with NPU acceleration.

    Issue #681: Primary embedding function for codebase indexing. Tries
    NPU worker first for hardware acceleration, falls back to local
    semantic chunker if unavailable.

    Args:
        documents: List of document strings to embed
        batch_size: Number of documents per batch

    Returns:
        List of embedding vectors (dimension depends on model)
    """
    if not documents:
        return []

    logger.info(
        "Generating embeddings for %d codebase documents (batch_size=%d)",
        len(documents),
        batch_size,
    )

    # Try NPU worker first
    npu_embeddings = await _generate_npu_embeddings(documents, batch_size)
    if npu_embeddings is not None:
        return npu_embeddings

    # Fallback to local semantic chunker
    logger.info("Falling back to local embedding generation")
    return await _generate_fallback_embeddings(documents, batch_size)


async def generate_single_embedding(document: str) -> List[float]:
    """
    Generate embedding for a single document.

    Args:
        document: Document text to embed

    Returns:
        Embedding vector
    """
    result = await generate_codebase_embeddings_batch([document], batch_size=1)
    return result[0] if result else []


async def warmup_npu_for_codebase() -> Dict[str, Any]:
    """
    Warm up NPU connection for codebase indexing.

    Issue #681: Called during backend startup to eliminate first-request
    latency and verify NPU worker availability.

    Returns:
        Dict with warmup status and timing information
    """
    start_time = time.time()

    result = {
        "status": "skipped",
        "npu_available": False,
        "warmup_time_ms": 0.0,
        "message": "",
    }

    try:
        client, is_available = await _get_npu_client_cached()

        if not is_available:
            result["status"] = "npu_unavailable"
            result["message"] = "NPU worker not available, will use local fallback"
            return result

        # Perform test embedding
        test_text = "Codebase indexing NPU warmup test"
        embeddings = await _generate_npu_embeddings([test_text], batch_size=1)

        warmup_time = (time.time() - start_time) * 1000

        if embeddings and len(embeddings) == 1 and len(embeddings[0]) > 0:
            result["status"] = "success"
            result["npu_available"] = True
            result["warmup_time_ms"] = warmup_time
            result["embedding_dimensions"] = len(embeddings[0])
            result[
                "message"
            ] = f"NPU connection warmed up for codebase indexing in {warmup_time:.1f}ms"

            # Get device info
            if client:
                try:
                    device_info = await client.get_device_info()
                    if device_info:
                        result["device"] = device_info.device_name
                        result["is_npu"] = device_info.is_npu
                        result["is_gpu"] = device_info.is_gpu
                except Exception:
                    pass

            logger.info(
                "Codebase NPU warmup complete: %d dimensions in %.1fms",
                len(embeddings[0]),
                warmup_time,
            )
        else:
            result["status"] = "empty_embedding"
            result["message"] = "NPU returned empty embedding during warmup"

    except Exception as e:
        warmup_time = (time.time() - start_time) * 1000
        result["status"] = "error"
        result["warmup_time_ms"] = warmup_time
        result["message"] = f"NPU warmup failed: {e}"
        logger.warning("Codebase NPU warmup failed: %s", e)

    return result
