#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Semantic Query Cache — cosine similarity matching for LLM response reuse.

Instead of exact-match hashing, this cache embeds each query and searches
a ChromaDB collection for semantically similar past queries. When a match
exceeds the configured similarity threshold (default 0.95), the cached
LLM response is returned from Redis without invoking the full RAG pipeline.

Issue: #1372

Architecture:
  ChromaDB collection ``semantic_query_cache``
    ├─ id: uuid
    ├─ embedding: query vector
    └─ metadata: {response_key, model, timestamp, query_text_hash}

  Redis L2 (database "cache")
    └─ sem_cache:<uuid> → JSON-serialised response payload
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_SIMILARITY_THRESHOLD = config.cache.l2.semantic_cache_threshold
_DEFAULT_MAX_COLLECTION_SIZE = config.cache.l1.semantic_cache_max_size
_DEFAULT_RESPONSE_TTL = config.cache.l2.semantic_cache
_COLLECTION_NAME = "semantic_query_cache"
_REDIS_KEY_PREFIX = "sem_cache:"
_REDIS_DATABASE = "cache"


@dataclass
class SemanticCacheConfig:
    """Runtime-tunable knobs for the semantic query cache."""

    similarity_threshold: float = _DEFAULT_SIMILARITY_THRESHOLD
    max_collection_size: int = _DEFAULT_MAX_COLLECTION_SIZE
    response_ttl: int = _DEFAULT_RESPONSE_TTL
    enabled: bool = True


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SemanticCacheEntry:
    """A cached response looked up via semantic similarity."""

    response_text: str
    model: str
    original_query: str
    similarity_score: float
    cached_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class SemanticQueryCache:
    """Embedding-based query cache backed by ChromaDB + Redis.

    Lifecycle:
        cache = SemanticQueryCache()
        await cache.initialize()
        hit = await cache.lookup(query_text)
        if hit is None:
            response = <run full pipeline>
            await cache.store(query_text, response, model)
    """

    def __init__(
        self,
        cache_config: Optional[SemanticCacheConfig] = None,
    ):
        self._config = cache_config or SemanticCacheConfig()
        self._collection = None
        self._initialized = False
        self._init_lock = asyncio.Lock()

        # Metrics
        self._hits = 0
        self._misses = 0
        self._stores = 0
        self._errors = 0

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    async def initialize(self) -> bool:
        """Create / open the ChromaDB collection (lazy, idempotent)."""
        if self._initialized:
            return True

        async with self._init_lock:
            if self._initialized:
                return True
            try:
                collection = await self._get_or_create_collection()
                if collection is None:
                    return False
                self._collection = collection
                self._initialized = True
                logger.info(
                    "SemanticQueryCache initialised " "(threshold=%.2f, max_size=%d)",
                    self._config.similarity_threshold,
                    self._config.max_collection_size,
                )
                return True
            except Exception as exc:
                logger.error("SemanticQueryCache init failed: %s", exc)
                self._errors += 1
                return False

    async def _get_or_create_collection(self):
        """Open or create the ChromaDB collection."""
        from utils.async_chromadb_client import get_async_chromadb_client

        client = await get_async_chromadb_client()
        if client is None:
            logger.warning("ChromaDB async client unavailable")
            return None

        collection = await client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        return collection

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def _evaluate_similarity(self, results: Dict, query: str) -> Optional[tuple]:
        """Evaluate ChromaDB query result for similarity match. Ref: #1372.

        Returns:
            (similarity, metadata, entry_id) tuple on match, None otherwise.
        """
        if not results or not results.get("ids") or not results["ids"][0]:
            self._misses += 1
            return None

        distance = results["distances"][0][0]
        similarity = 1.0 - distance

        if similarity < self._config.similarity_threshold:
            self._misses += 1
            logger.debug(
                "Semantic cache near-miss (%.3f < %.3f) for: %s...",
                similarity,
                self._config.similarity_threshold,
                query[:60],
            )
            return None

        meta = results["metadatas"][0][0]
        entry_id = results["ids"][0][0]
        return similarity, meta, entry_id

    async def _resolve_cache_hit(
        self, similarity: float, meta: Dict, entry_id: str, query: str
    ) -> Optional[SemanticCacheEntry]:
        """Fetch Redis payload and build cache entry. Ref: #1372."""
        response_key = meta.get("response_key", "")
        if not response_key:
            self._misses += 1
            return None

        payload = await self._fetch_response(response_key)
        if payload is None:
            await self._delete_entry(entry_id)
            self._misses += 1
            return None

        self._hits += 1
        logger.info(
            "Semantic cache HIT (sim=%.3f) for: %s...",
            similarity,
            query[:60],
        )
        return SemanticCacheEntry(
            response_text=payload.get("response_text", ""),
            model=payload.get("model", ""),
            original_query=payload.get("original_query", ""),
            similarity_score=similarity,
            cached_at=payload.get("cached_at", 0.0),
            metadata=payload.get("metadata", {}),
        )

    async def lookup(
        self,
        query: str,
        embedding: Optional[List[float]] = None,
    ) -> Optional[SemanticCacheEntry]:
        """Search for a semantically similar cached query.

        Args:
            query: The user query text.
            embedding: Pre-computed embedding (if available).

        Returns:
            A ``SemanticCacheEntry`` on hit, or *None* on miss.
        """
        if not self._config.enabled or not self._initialized:
            return None

        try:
            if embedding is None:
                embedding = await self._embed(query)
                if embedding is None:
                    return None

            results = await self._collection.query(
                query_embeddings=[embedding],
                n_results=1,
                include=["metadatas", "distances"],
            )

            match = self._evaluate_similarity(results, query)
            if match is None:
                return None

            similarity, meta, entry_id = match
            return await self._resolve_cache_hit(similarity, meta, entry_id, query)
        except Exception as exc:
            self._errors += 1
            logger.warning("Semantic cache lookup error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    async def _persist_entry(
        self,
        query: str,
        response_text: str,
        model: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]],
    ) -> bool:
        """Write entry to Redis + ChromaDB. Ref: #1372."""
        entry_id = str(uuid.uuid4())
        response_key = f"{_REDIS_KEY_PREFIX}{entry_id}"
        now = time.time()

        payload = {
            "response_text": response_text,
            "model": model,
            "original_query": query,
            "cached_at": now,
            "metadata": metadata or {},
        }

        if not await self._store_response(response_key, payload):
            return False

        query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
        await self._collection.add(
            ids=[entry_id],
            embeddings=[embedding],
            metadatas=[
                {
                    "response_key": response_key,
                    "model": model,
                    "cached_at": now,
                    "query_hash": query_hash,
                }
            ],
        )
        return True

    async def store(
        self,
        query: str,
        response_text: str,
        model: str,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Cache a query-response pair for future semantic matching.

        Returns:
            *True* on success, *False* otherwise.
        """
        if not self._config.enabled or not self._initialized:
            return False

        try:
            if embedding is None:
                embedding = await self._embed(query)
                if embedding is None:
                    return False

            success = await self._persist_entry(
                query, response_text, model, embedding, metadata
            )
            if not success:
                return False

            self._stores += 1
            await self._maybe_evict()
            logger.debug(
                "Semantic cache STORE: %s (model=%s)",
                query[:60],
                model,
            )
            return True

        except Exception as exc:
            self._errors += 1
            logger.warning("Semantic cache store error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    async def _fetch_response(self, key: str) -> Optional[Dict]:
        """Fetch cached response payload from Redis."""
        try:
            client = await get_redis_client(async_client=True, database=_REDIS_DATABASE)
            if client is None:
                return None
            raw = await client.get(key)
            if raw is None:
                return None
            return json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
        except Exception as exc:
            logger.debug("Redis fetch failed for %s: %s", key, exc)
            return None

    async def _store_response(self, key: str, payload: Dict) -> bool:
        """Persist response payload in Redis with TTL."""
        try:
            client = await get_redis_client(async_client=True, database=_REDIS_DATABASE)
            if client is None:
                return False
            await client.set(
                key,
                json.dumps(payload, default=str),
                ex=self._config.response_ttl,
            )
            return True
        except Exception as exc:
            logger.debug("Redis store failed for %s: %s", key, exc)
            return False

    # ------------------------------------------------------------------
    # ChromaDB helpers
    # ------------------------------------------------------------------

    async def _delete_entry(self, entry_id: str) -> None:
        """Remove a stale entry from ChromaDB."""
        try:
            await self._collection.delete(ids=[entry_id])
        except Exception as exc:
            logger.debug("ChromaDB delete failed for %s: %s", entry_id, exc)

    async def _maybe_evict(self) -> None:
        """Evict oldest entries when collection exceeds max size."""
        try:
            count = await self._collection.count()
            if count <= self._config.max_collection_size:
                return

            excess = count - self._config.max_collection_size + 100
            results = await self._collection.get(
                limit=excess,
                include=["metadatas"],
            )
            if results and results.get("ids"):
                ids_to_delete = results["ids"]

                # Clean up Redis keys
                for meta in results.get("metadatas", []):
                    rkey = meta.get("response_key", "")
                    if rkey:
                        try:
                            client = await get_redis_client(
                                async_client=True,
                                database=_REDIS_DATABASE,
                            )
                            if client:
                                await client.delete(rkey)
                        except Exception:
                            pass

                await self._collection.delete(ids=ids_to_delete)
                logger.info(
                    "Semantic cache evicted %d entries " "(collection size was %d)",
                    len(ids_to_delete),
                    count,
                )
        except Exception as exc:
            logger.debug("Semantic cache eviction error: %s", exc)

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    @staticmethod
    async def _embed(text: str) -> Optional[List[float]]:
        """Generate embedding for a query string."""
        try:
            from knowledge.facts import _generate_embedding_with_npu_fallback

            return await _generate_embedding_with_npu_fallback(text)
        except Exception as exc:
            logger.warning("Embedding generation failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    async def clear(self) -> Dict[str, int]:
        """Wipe all entries from both ChromaDB and Redis."""
        chromadb_deleted = 0
        redis_deleted = 0

        try:
            if self._collection:
                results = await self._collection.get(include=["metadatas"])
                if results and results.get("ids"):
                    # Clean Redis
                    client = await get_redis_client(
                        async_client=True, database=_REDIS_DATABASE
                    )
                    if client:
                        for meta in results.get("metadatas", []):
                            rkey = meta.get("response_key", "")
                            if rkey:
                                redis_deleted += await client.delete(rkey)

                    await self._collection.delete(ids=results["ids"])
                    chromadb_deleted = len(results["ids"])

        except Exception as exc:
            logger.error("Semantic cache clear error: %s", exc)

        self._hits = 0
        self._misses = 0
        self._stores = 0
        self._errors = 0

        logger.info(
            "Semantic cache cleared: %d ChromaDB, %d Redis entries",
            chromadb_deleted,
            redis_deleted,
        )
        return {
            "chromadb_deleted": chromadb_deleted,
            "redis_deleted": redis_deleted,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return cache performance metrics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0

        return {
            "enabled": self._config.enabled,
            "initialized": self._initialized,
            "hits": self._hits,
            "misses": self._misses,
            "stores": self._stores,
            "errors": self._errors,
            "hit_rate": round(hit_rate, 2),
            "similarity_threshold": self._config.similarity_threshold,
            "max_collection_size": self._config.max_collection_size,
            "response_ttl": self._config.response_ttl,
        }

    def update_config(
        self,
        similarity_threshold: Optional[float] = None,
        max_collection_size: Optional[int] = None,
        response_ttl: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Update cache configuration at runtime."""
        if similarity_threshold is not None:
            if not 0.5 <= similarity_threshold <= 1.0:
                raise ValueError("similarity_threshold must be between 0.5 and 1.0")
            self._config.similarity_threshold = similarity_threshold
        if max_collection_size is not None:
            self._config.max_collection_size = max_collection_size
        if response_ttl is not None:
            self._config.response_ttl = response_ttl
        if enabled is not None:
            self._config.enabled = enabled

        logger.info("Semantic cache config updated: %s", self._config)
        return self.get_stats()


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_instance: Optional[SemanticQueryCache] = None
_instance_lock = asyncio.Lock()


async def get_semantic_query_cache() -> SemanticQueryCache:
    """Get or create the global SemanticQueryCache singleton."""
    global _instance
    if _instance is None:
        async with _instance_lock:
            if _instance is None:
                _instance = SemanticQueryCache()
                await _instance.initialize()
    return _instance
