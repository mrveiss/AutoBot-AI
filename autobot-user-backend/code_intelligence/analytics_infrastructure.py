# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analytics Infrastructure Mixin

Issue #554: Provides shared infrastructure for code analysis modules including:
- ChromaDB: Vector embeddings for semantic similarity search
- Redis: Caching analysis results for performance
- LLM: Semantic analysis and intelligent pattern detection
- Embedding Cache: Performance optimization for repeated embeddings

Issue #640: NPU Worker Integration
- When NPU worker is available, embedding generation is offloaded to NPU/GPU
- Falls back to Ollama if NPU worker is unavailable
- Provides 3-10x faster embedding generation on supported hardware

This mixin can be added to any analyzer class to provide standardized
infrastructure access following the pattern established in cross_language_patterns.

Part of EPIC #217 - Advanced Code Intelligence Methods
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Issue #640: NPU Worker availability flag (lazy-checked)
_npu_worker_available: Optional[bool] = None
_npu_worker_check_time: float = 0
NPU_CHECK_INTERVAL = 60  # Re-check NPU availability every 60 seconds

# Default configuration
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_CACHE_TTL = 3600  # 1 hour
DEFAULT_EMBEDDING_CACHE_SIZE = 500
DEFAULT_REDIS_DATABASE = "analytics"
MAX_ERROR_COUNT = 100  # Issue #554: Limit error list growth for memory safety

# Similarity thresholds for semantic matching
SIMILARITY_HIGH = 0.85
SIMILARITY_MEDIUM = 0.70
SIMILARITY_LOW = 0.50

# Issue #554: Security - Allowed collection name pattern (alphanumeric, underscore, hyphen)
import re

COLLECTION_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")

# Issue #554: Security - Allowed Redis key characters
REDIS_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_:.-]+$")


@dataclass
class InfrastructureMetrics:
    """Metrics for infrastructure usage."""

    cache_hits: int = 0
    cache_misses: int = 0
    embeddings_generated: int = 0
    redis_operations: int = 0
    chromadb_operations: int = 0
    llm_requests: int = 0
    analysis_time_ms: float = 0
    errors: List[str] = field(default_factory=list)
    _errors_truncated: int = 0  # Issue #554: Track truncated errors

    def add_error(self, error: str) -> None:
        """
        Add error with bounded list size.

        Issue #554: Security - Prevents unbounded memory growth from error accumulation.
        """
        if len(self.errors) < MAX_ERROR_COUNT:
            self.errors.append(error)
        else:
            self._errors_truncated += 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        total_cache = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_cache * 100) if total_cache > 0 else 0

        result = {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": round(hit_rate, 2),
            "embeddings_generated": self.embeddings_generated,
            "redis_operations": self.redis_operations,
            "chromadb_operations": self.chromadb_operations,
            "llm_requests": self.llm_requests,
            "analysis_time_ms": round(self.analysis_time_ms, 2),
            "errors": self.errors,
        }
        if self._errors_truncated > 0:
            result["errors_truncated"] = self._errors_truncated
        return result


class AnalyticsInfrastructureMixin:
    """
    Mixin class providing shared analytics infrastructure.

    Usage:
        class MyAnalyzer(AnalyticsInfrastructureMixin):
            def __init__(self):
                super().__init__()
                self._init_infrastructure(
                    collection_name="my_analyzer_vectors",
                    use_llm=True,
                    use_cache=True,
                )

            async def analyze(self, code: str):
                # Get embedding for code
                embedding = await self._get_embedding(code)

                # Store in ChromaDB
                collection = await self._get_chromadb_collection()
                await collection.add(...)

                # Cache results in Redis
                await self._cache_result("key", result)
    """

    def _init_infrastructure(
        self,
        collection_name: str = "code_analysis_vectors",
        use_llm: bool = True,
        use_cache: bool = True,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        redis_database: str = DEFAULT_REDIS_DATABASE,
        embedding_cache_size: int = DEFAULT_EMBEDDING_CACHE_SIZE,
    ) -> None:
        """
        Initialize infrastructure configuration.

        Args:
            collection_name: Name for ChromaDB collection
            use_llm: Whether to use LLM for embeddings/analysis
            use_cache: Whether to use Redis caching
            embedding_model: Ollama model for embeddings
            cache_ttl: TTL for cached results in seconds
            redis_database: Redis database name
            embedding_cache_size: Max entries in embedding cache (default 500)

        Raises:
            ValueError: If collection_name contains invalid characters
        """
        # Issue #554: Security - Validate collection name to prevent injection
        if not COLLECTION_NAME_PATTERN.match(collection_name):
            raise ValueError(
                f"Invalid collection name '{collection_name}'. "
                "Must start with letter, contain only alphanumeric, underscore, hyphen, "
                "and be 1-64 characters."
            )

        self._collection_name = collection_name
        self._use_llm = use_llm
        self._use_cache = use_cache
        self._embedding_model = embedding_model
        self._cache_ttl = cache_ttl
        self._redis_database = redis_database
        self._embedding_cache_size = embedding_cache_size

        # Lazy-loaded resources
        self._chromadb_client = None
        self._chromadb_collection = None
        self._redis_client = None
        self._embedding_cache = None

        # Thread-safe initialization lock
        self._infra_lock = asyncio.Lock()

        # Metrics tracking
        self._metrics = InfrastructureMetrics()

    async def _get_chromadb_collection(self):
        """Get or create ChromaDB collection for vector storage."""
        if self._chromadb_collection is None:
            async with self._infra_lock:
                if self._chromadb_collection is None:
                    try:
                        from src.utils.async_chromadb_client import (
                            get_async_chromadb_client,
                        )

                        self._chromadb_client = await get_async_chromadb_client()
                        self._chromadb_collection = await self._chromadb_client.get_or_create_collection(
                            name=self._collection_name,
                            metadata={
                                "description": f"Vectors for {self._collection_name}",
                                "hnsw:space": "cosine",
                                "hnsw:construction_ef": 200,
                                "hnsw:search_ef": 100,
                                "hnsw:M": 24,
                            },
                        )
                        logger.info(
                            "ChromaDB collection '%s' initialized",
                            self._collection_name,
                        )
                    except Exception as e:
                        logger.error("Failed to initialize ChromaDB: %s", e)
                        self._metrics.add_error(f"ChromaDB init failed: {e}")
                        self._chromadb_collection = None
        return self._chromadb_collection

    async def _get_redis_client(self):
        """Get Redis client for caching."""
        if self._redis_client is None and self._use_cache:
            async with self._infra_lock:
                if self._redis_client is None:
                    try:
                        from src.utils.redis_client import get_redis_client

                        self._redis_client = await get_redis_client(
                            async_client=True, database=self._redis_database
                        )
                        logger.info(
                            "Redis client initialized for '%s'", self._redis_database
                        )
                    except Exception as e:
                        logger.warning("Redis not available for caching: %s", e)
                        self._metrics.add_error(f"Redis init failed: {e}")
                        self._redis_client = None
        return self._redis_client

    async def _get_embedding_cache(self):
        """Get embedding cache with thread-safe lazy initialization."""
        if self._embedding_cache is None:
            async with self._infra_lock:
                if self._embedding_cache is None:
                    try:
                        from src.knowledge.embedding_cache import EmbeddingCache

                        self._embedding_cache = EmbeddingCache(
                            maxsize=self._embedding_cache_size,
                            ttl_seconds=self._cache_ttl,
                        )
                    except ImportError:
                        logger.warning("EmbeddingCache not available")
                        self._embedding_cache = None
        return self._embedding_cache

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Get embedding for text using NPU worker (preferred) or Ollama (fallback).

        Issue #640: Attempts to use NPU worker for hardware-accelerated embedding
        generation. Falls back to Ollama if NPU worker is unavailable.

        Args:
            text: Text to generate embedding for

        Returns:
            Embedding vector or None if generation failed
        """
        if not self._use_llm or not text.strip():
            return None

        # Issue #554: Truncate text to prevent token limit errors
        # nomic-embed-text has ~8192 token limit, roughly 4 chars per token
        max_chars = 30000  # Conservative limit
        if len(text) > max_chars:
            text = text[:max_chars]

        cache = await self._get_embedding_cache()
        if cache:
            cached = await cache.get(text)
            if cached:
                self._metrics.cache_hits += 1
                return cached
            self._metrics.cache_misses += 1

        # Issue #640: Try NPU worker first for hardware acceleration
        embedding = await self._get_embedding_via_npu(text)
        if embedding:
            self._metrics.embeddings_generated += 1
            self._metrics.llm_requests += 1
            if cache:
                await cache.put(text, embedding)
            return embedding

        # Fallback to Ollama
        embedding = await self._get_embedding_via_ollama(text)
        if embedding:
            self._metrics.embeddings_generated += 1
            self._metrics.llm_requests += 1
            if cache:
                await cache.put(text, embedding)
            return embedding

        return None

    async def _get_embedding_via_npu(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding using NPU worker.

        Issue #640: Offloads embedding generation to NPU/GPU for acceleration.

        Args:
            text: Text to embed

        Returns:
            Embedding vector or None if NPU worker unavailable/failed
        """
        global _npu_worker_available, _npu_worker_check_time
        import time

        # Check if we should re-verify NPU availability
        current_time = time.time()
        if _npu_worker_available is False:
            if current_time - _npu_worker_check_time < NPU_CHECK_INTERVAL:
                return None  # Skip NPU - recently confirmed unavailable

        try:
            from backend.services.npu_client import get_npu_client

            client = get_npu_client()

            # Check availability (uses cached result if recent)
            if not await client.is_available():
                _npu_worker_available = False
                _npu_worker_check_time = current_time
                return None

            _npu_worker_available = True
            embedding = await client.generate_embedding(text, self._embedding_model)
            if embedding:
                logger.debug("Embedding generated via NPU worker")
                return embedding

        except ImportError:
            logger.debug("NPU client not available (import failed)")
            _npu_worker_available = False
            _npu_worker_check_time = current_time
        except Exception as e:
            logger.debug("NPU worker embedding failed: %s", e)

        return None

    async def _get_embedding_via_ollama(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding using Ollama (fallback method).

        Args:
            text: Text to embed

        Returns:
            Embedding vector or None if failed
        """
        try:
            import aiohttp

            from src.config.ssot_config import get_config

            ssot = get_config()
            url = f"{ssot.ollama_url}/api/embeddings"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json={"model": self._embedding_model, "prompt": text},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        embedding = data.get("embedding")
                        if embedding:
                            logger.debug("Embedding generated via Ollama")
                            return embedding
        except Exception as e:
            logger.warning("Ollama embedding generation failed: %s", e)
            self._metrics.add_error(f"Embedding generation failed: {e}")

        return None

    async def _get_embeddings_batch(
        self, texts: List[str], max_concurrent: int = 5
    ) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts in parallel.

        Issue #554: Uses asyncio.gather for 3-5x faster batch embedding generation.
        Issue #640: Uses NPU worker batch endpoint when available for optimal throughput.

        Args:
            texts: List of texts to generate embeddings for
            max_concurrent: Maximum concurrent embedding requests (default 5)

        Returns:
            List of embeddings (or None for failed/empty texts)
        """
        if not self._use_llm or not texts:
            return [None] * len(texts)

        # Issue #640: Try NPU worker batch endpoint first (most efficient)
        npu_results = await self._get_embeddings_batch_via_npu(texts)
        if npu_results and len(npu_results) == len(texts):
            # Check if we got valid results (not all None)
            valid_count = sum(1 for r in npu_results if r is not None)
            if valid_count > 0:
                self._metrics.embeddings_generated += valid_count
                return npu_results

        # Fallback to parallel individual requests
        semaphore = asyncio.Semaphore(max_concurrent)

        async def get_with_limit(text: str) -> Optional[List[float]]:
            async with semaphore:
                return await self._get_embedding(text) if text.strip() else None

        # Execute all embeddings in parallel with rate limiting
        tasks = [get_with_limit(text) for text in texts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to None
        return [r if isinstance(r, list) else None for r in results]

    async def _get_embeddings_batch_via_npu(
        self, texts: List[str]
    ) -> Optional[List[Optional[List[float]]]]:
        """
        Generate embeddings batch using NPU worker.

        Issue #640: Uses NPU worker's batch endpoint for efficient bulk processing.

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings or None if NPU worker unavailable
        """
        global _npu_worker_available, _npu_worker_check_time
        import time

        current_time = time.time()
        if _npu_worker_available is False:
            if current_time - _npu_worker_check_time < NPU_CHECK_INTERVAL:
                return None

        try:
            from backend.services.npu_client import get_npu_client

            client = get_npu_client()

            if not await client.is_available():
                _npu_worker_available = False
                _npu_worker_check_time = current_time
                return None

            _npu_worker_available = True
            result = await client.generate_embeddings(texts, self._embedding_model)
            if result and result.embeddings:
                logger.info(
                    "Batch embeddings (%d) generated via NPU worker in %.1fms",
                    len(texts),
                    result.processing_time_ms,
                )
                return result.embeddings

        except ImportError:
            _npu_worker_available = False
            _npu_worker_check_time = current_time
        except Exception as e:
            logger.debug("NPU worker batch embedding failed: %s", e)

        return None

    def _sanitize_redis_key(self, key: str, prefix: str = "") -> Optional[str]:
        """
        Sanitize and validate Redis key.

        Issue #554: Security - Prevents Redis key injection attacks by validating
        key format and sanitizing to allowed characters only.

        Args:
            key: The cache key to sanitize
            prefix: Optional prefix for the key

        Returns:
            Sanitized key or None if invalid
        """
        if not key:
            return None

        # Build full key
        full_key = f"{prefix}:{key}" if prefix else key

        # Issue #554: Validate key format to prevent injection
        if not REDIS_KEY_PATTERN.match(full_key):
            # Sanitize by removing invalid characters
            sanitized = re.sub(r"[^a-zA-Z0-9_:.-]", "_", full_key)
            if not sanitized or len(sanitized) > 256:
                logger.warning("Redis key rejected after sanitization: %s", key[:50])
                return None
            full_key = sanitized

        # Limit key length (Redis max is 512MB but practical limit is much lower)
        if len(full_key) > 256:
            # Hash long keys to maintain uniqueness
            key_hash = hashlib.sha256(full_key.encode()).hexdigest()[:32]
            full_key = f"{full_key[:200]}:{key_hash}"

        return full_key

    async def _cache_result(
        self,
        key: str,
        result: Any,
        ttl: Optional[int] = None,
        prefix: str = "",
    ) -> bool:
        """Cache result in Redis."""
        redis = await self._get_redis_client()
        if not redis:
            return False

        # Issue #554: Security - Sanitize Redis key
        full_key = self._sanitize_redis_key(key, prefix)
        if not full_key:
            return False

        try:
            cache_data = json.dumps(result, default=str)
            await redis.setex(full_key, ttl or self._cache_ttl, cache_data)
            self._metrics.redis_operations += 1
            return True
        except Exception as e:
            logger.warning("Failed to cache result: %s", e)
            self._metrics.add_error(f"Redis cache failed: {e}")
            return False

    async def _get_cached_result(self, key: str, prefix: str = "") -> Optional[Any]:
        """Get cached result from Redis."""
        redis = await self._get_redis_client()
        if not redis:
            return None

        # Issue #554: Security - Sanitize Redis key
        full_key = self._sanitize_redis_key(key, prefix)
        if not full_key:
            return None

        try:
            cached = await redis.get(full_key)
            self._metrics.redis_operations += 1

            if cached:
                self._metrics.cache_hits += 1
                return json.loads(cached)
            else:
                self._metrics.cache_misses += 1
                return None
        except Exception as e:
            logger.warning("Failed to get cached result: %s", e)
            return None

    async def _store_vectors(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """Store vectors in ChromaDB with error recovery."""
        collection = await self._get_chromadb_collection()
        if not collection:
            return 0

        stored_count = 0

        try:
            await collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas or [{} for _ in ids],
            )
            stored_count = len(ids)
            self._metrics.chromadb_operations += 1
        except Exception as batch_error:
            logger.warning("Batch insertion failed: %s, using individual", batch_error)
            for i, (vid, emb, doc) in enumerate(zip(ids, embeddings, documents)):
                try:
                    meta = metadatas[i] if metadatas else {}
                    await collection.add(
                        ids=[vid],
                        embeddings=[emb],
                        documents=[doc],
                        metadatas=[meta],
                    )
                    stored_count += 1
                    self._metrics.chromadb_operations += 1
                except Exception as e:
                    logger.debug("Failed to store vector %s: %s", vid, e)

        return stored_count

    async def _query_similar(
        self,
        embedding: List[float],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        min_similarity: float = SIMILARITY_LOW,
    ) -> List[Dict[str, Any]]:
        """Query for similar vectors in ChromaDB."""
        collection = await self._get_chromadb_collection()
        if not collection:
            return []

        results = []

        try:
            query_result = await collection.query(
                query_embeddings=[embedding],
                n_results=n_results,
                where=where,
            )
            self._metrics.chromadb_operations += 1

            if query_result and query_result.get("distances"):
                for i, (distance, doc_id) in enumerate(
                    zip(query_result["distances"][0], query_result["ids"][0])
                ):
                    similarity = 1 - distance
                    if similarity >= min_similarity:
                        result = {"id": doc_id, "similarity": similarity}
                        if query_result.get("documents"):
                            result["document"] = query_result["documents"][0][i]
                        if query_result.get("metadatas"):
                            result["metadata"] = query_result["metadatas"][0][i]
                        results.append(result)
        except Exception as e:
            logger.warning("Query failed: %s", e)
            self._metrics.add_error(f"ChromaDB query failed: {e}")

        return results

    def _generate_content_hash(self, content: str) -> str:
        """Generate hash for content-based deduplication."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_infrastructure_metrics(self) -> Dict[str, Any]:
        """Get current infrastructure metrics."""
        return self._metrics.to_dict()

    def _reset_infrastructure_metrics(self) -> None:
        """Reset infrastructure metrics."""
        self._metrics = InfrastructureMetrics()

    async def _cleanup_infrastructure(self) -> None:
        """Cleanup infrastructure resources."""
        if self._redis_client:
            try:
                await self._redis_client.close()
            except Exception:  # nosec B110 - cleanup ignores close errors
                pass
            self._redis_client = None
        logger.info("Infrastructure resources cleaned up")


class SemanticAnalysisMixin(AnalyticsInfrastructureMixin):
    """Extended mixin with semantic analysis capabilities."""

    def _compute_batch_similarities(
        self,
        embeddings: List[Optional[List[float]]],
        min_similarity: float = SIMILARITY_MEDIUM,
    ) -> List[tuple]:
        """
        Compute pairwise cosine similarities for embeddings batch.

        Issue #554: Performance - Uses numpy for O(n) vectorized computation when available,
        falls back to pure Python O(n^2) otherwise. Provides 10-50x speedup for large batches.
        Issue #620: Refactored to extract helper methods.

        Args:
            embeddings: List of embedding vectors (None entries are skipped)
            min_similarity: Minimum similarity threshold

        Returns:
            List of (i, j, similarity) tuples for pairs above threshold
        """
        # Filter to valid embeddings with original indices
        valid = [(i, emb) for i, emb in enumerate(embeddings) if emb is not None]
        if len(valid) < 2:
            return []

        try:
            import numpy as np

            return self._compute_similarities_numpy(valid, min_similarity, np)
        except ImportError:
            return self._compute_similarities_python(valid, min_similarity)

    def _compute_similarities_numpy(
        self,
        valid: List[tuple],
        min_similarity: float,
        np,
    ) -> List[tuple]:
        """
        Compute cosine similarities using numpy vectorized operations.

        Issue #554: Performance - Vectorized numpy computation.
        Issue #620: Extracted from _compute_batch_similarities. Issue #620.

        Args:
            valid: List of (index, embedding) tuples for valid embeddings
            min_similarity: Minimum similarity threshold
            np: numpy module reference

        Returns:
            List of (i, j, similarity) tuples for pairs above threshold
        """
        indices = [v[0] for v in valid]
        matrix = np.array([v[1] for v in valid], dtype=np.float32)

        # Normalize rows for cosine similarity
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)  # Avoid division by zero
        normalized = matrix / norms

        # Compute full similarity matrix (upper triangle only needed)
        sim_matrix = np.dot(normalized, normalized.T)

        # Extract pairs above threshold
        results = []
        n = len(indices)
        for i in range(n):
            for j in range(i + 1, n):
                sim = float(sim_matrix[i, j])
                if sim >= min_similarity:
                    results.append((indices[i], indices[j], sim))
        return results

    def _compute_similarities_python(
        self,
        valid: List[tuple],
        min_similarity: float,
    ) -> List[tuple]:
        """
        Compute cosine similarities using pure Python (fallback when numpy unavailable).

        Issue #620: Extracted from _compute_batch_similarities. Issue #620.

        Args:
            valid: List of (index, embedding) tuples for valid embeddings
            min_similarity: Minimum similarity threshold

        Returns:
            List of (i, j, similarity) tuples for pairs above threshold
        """
        results = []
        for idx1, (i, emb1) in enumerate(valid):
            for idx2 in range(idx1 + 1, len(valid)):
                j, emb2 = valid[idx2]
                dot_product = sum(a * b for a, b in zip(emb1, emb2))
                norm1 = sum(a * a for a in emb1) ** 0.5
                norm2 = sum(b * b for b in emb2) ** 0.5
                if norm1 > 0 and norm2 > 0:
                    sim = dot_product / (norm1 * norm2)
                    if sim >= min_similarity:
                        results.append((i, j, sim))
        return results

    async def _normalize_code_for_embedding(
        self, code: str, language: str = "python"
    ) -> str:
        """Normalize code to language-independent representation."""
        lines = []
        in_multiline_comment = False

        for line in code.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue

            if language == "python":
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    in_multiline_comment = not in_multiline_comment
                    continue
                if in_multiline_comment or stripped.startswith("#"):
                    continue
            elif language in ("typescript", "javascript"):
                if stripped.startswith("//"):
                    continue
                if "/*" in stripped:
                    in_multiline_comment = True
                if "*/" in stripped:
                    in_multiline_comment = False
                    continue
                if in_multiline_comment:
                    continue

            lines.append(stripped)

        return " ".join(lines)

    def _cosine_similarity(self, emb1: List[float], emb2: List[float]) -> float:
        """
        Compute cosine similarity between two embeddings.

        Issue #554: Performance - Uses numpy when available for faster computation.
        """
        try:
            import numpy as np

            v1 = np.array(emb1, dtype=np.float32)
            v2 = np.array(emb2, dtype=np.float32)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return float(np.dot(v1, v2) / (norm1 * norm2))
        except ImportError:
            # Fallback to pure Python
            dot_product = sum(a * b for a, b in zip(emb1, emb2))
            norm1 = sum(a * a for a in emb1) ** 0.5
            norm2 = sum(b * b for b in emb2) ** 0.5
            if norm1 == 0 or norm2 == 0:
                return 0.0
            return dot_product / (norm1 * norm2)

    async def _compute_semantic_similarity(
        self, code1: str, code2: str, language: str = "python"
    ) -> float:
        """Compute semantic similarity between two code snippets."""
        if not self._use_llm:
            return 0.0

        norm1 = await self._normalize_code_for_embedding(code1, language)
        norm2 = await self._normalize_code_for_embedding(code2, language)

        emb1 = await self._get_embedding(norm1)
        emb2 = await self._get_embedding(norm2)

        if not emb1 or not emb2:
            return 0.0

        return self._cosine_similarity(emb1, emb2)

    async def _find_semantic_duplicates(
        self,
        items: List[Dict[str, Any]],
        code_key: str = "code",
        min_similarity: float = SIMILARITY_MEDIUM,
    ) -> List[Dict[str, Any]]:
        """Find semantically similar items in a list."""
        if not self._use_llm or len(items) < 2:
            return []

        # Issue #554: Use parallel embedding generation for 3-5x speedup
        codes = [item.get(code_key, "") for item in items]
        embeddings = await self._get_embeddings_batch(codes)

        # Issue #554: Performance - Use vectorized similarity computation
        similarity_pairs = self._compute_batch_similarities(embeddings, min_similarity)

        duplicates = []
        for i, j, similarity in similarity_pairs:
            duplicates.append(
                {
                    "item1": items[i],
                    "item2": items[j],
                    "similarity": similarity,
                }
            )

        return duplicates

    def _extract_code_and_metadata(
        self,
        item: Any,
        code_extractors: List[str],
        metadata_keys: Dict[str, str],
        min_code_length: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Extract code and metadata from an item for duplicate detection.

        Issue #620.

        Args:
            item: Object with code content
            code_extractors: Attribute names to try for code extraction
            metadata_keys: Dict mapping output keys to object attributes
            min_code_length: Minimum code length to consider

        Returns:
            Dict with code and metadata, or None if extraction fails
        """
        code = None
        for extractor in code_extractors:
            code = getattr(item, extractor, "") or ""
            if code and len(code) >= min_code_length:
                break

        if not code or len(code) < min_code_length:
            return None

        item_data: Dict[str, Any] = {"code": code, "_original": item}
        for out_key, attr_name in metadata_keys.items():
            value = getattr(item, attr_name, None)
            if hasattr(value, "value"):
                value = value.value
            item_data[out_key] = value
        return item_data

    async def _find_semantic_duplicates_with_extraction(
        self,
        items: List[Any],
        code_extractors: List[str],
        metadata_keys: Dict[str, str],
        min_code_length: int = 20,
        min_similarity: float = SIMILARITY_MEDIUM,
    ) -> List[Dict[str, Any]]:
        """
        Generic semantic duplicate finder with custom extraction logic.

        Issue #554: Extracts common pattern from all analyzer-specific duplicate
        finders (~120 lines reduced to single reusable method).

        Args:
            items: List of objects with code content (e.g., AntiPatternResult)
            code_extractors: Attribute names to try for code extraction
            metadata_keys: Dict mapping output keys to object attributes
            min_code_length: Minimum code length to consider (default 20)
            min_similarity: Minimum similarity threshold (default SIMILARITY_MEDIUM)

        Returns:
            List of duplicate pairs with similarity scores
        """
        if not hasattr(self, "use_semantic_analysis") or not self.use_semantic_analysis:
            return []

        if not items or len(items) < 2:
            return []

        items_with_code = []
        for item in items:
            extracted = self._extract_code_and_metadata(
                item, code_extractors, metadata_keys, min_code_length
            )
            if extracted:
                items_with_code.append(extracted)

        if len(items_with_code) < 2:
            return []

        return await self._find_semantic_duplicates(
            items_with_code, code_key="code", min_similarity=min_similarity
        )
