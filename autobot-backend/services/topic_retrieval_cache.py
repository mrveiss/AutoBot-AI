#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Topic-Level Retrieval Context Cache — cross-query chunk reuse by topic.

Caches retrieved ChromaDB chunks keyed by topic centroid embedding so
that related queries about the same topic can share chunks without
repeating the vector search.

Issue: #1376

Architecture:
  ChromaDB collection ``topic_retrieval_cache``
    ├─ id: topic uuid
    ├─ embedding: centroid of chunk embeddings
    └─ metadata: {redis_key, chunk_count, created_at}

  Redis L2 (database "cache")
    └─ topic_cache:<uuid> → JSON list of serialised chunks
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_COLLECTION_NAME = "topic_retrieval_cache"
_REDIS_KEY_PREFIX = "topic_cache:"
_REDIS_DATABASE = "cache"
_DEFAULT_SIMILARITY_THRESHOLD = 0.70
_DEFAULT_MAX_TOPICS = 500
_DEFAULT_TTL = 1800  # 30 minutes (shorter than LLM cache)


@dataclass
class TopicCacheConfig:
    """Runtime-tunable knobs for the topic retrieval cache."""

    similarity_threshold: float = _DEFAULT_SIMILARITY_THRESHOLD
    max_topics: int = _DEFAULT_MAX_TOPICS
    ttl: int = _DEFAULT_TTL
    enabled: bool = True


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CachedChunk:
    """A single cached retrieval chunk."""

    content: str
    metadata: Dict[str, Any]
    score: float


# ---------------------------------------------------------------------------
# Centroid computation
# ---------------------------------------------------------------------------


def compute_centroid(embeddings: List[List[float]]) -> List[float]:
    """Compute the centroid (mean) of a list of embeddings. Ref: #1376."""
    if not embeddings:
        return []
    arr = np.array(embeddings, dtype=np.float32)
    centroid = arr.mean(axis=0)
    # Normalize to unit vector for cosine similarity
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm
    return centroid.tolist()


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class TopicRetrievalCache:
    """Topic-centroid cache for cross-query chunk reuse.

    Usage::

        cache = TopicRetrievalCache()
        await cache.initialize()
        chunks = await cache.lookup(query_embedding)
        if chunks is None:
            chunks = <run ChromaDB search>
            await cache.store(chunk_embeddings, chunks)
    """

    def __init__(self, cache_config: Optional[TopicCacheConfig] = None):
        self._config = cache_config or TopicCacheConfig()
        self._collection = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
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
                    "TopicRetrievalCache initialised "
                    "(threshold=%.2f, max_topics=%d)",
                    self._config.similarity_threshold,
                    self._config.max_topics,
                )
                return True
            except Exception as exc:
                logger.error("TopicRetrievalCache init failed: %s", exc)
                self._errors += 1
                return False

    async def _get_or_create_collection(self):
        """Open or create the ChromaDB collection."""
        from utils.async_chromadb_client import get_async_chromadb_client

        client = await get_async_chromadb_client()
        if client is None:
            logger.warning("ChromaDB async client unavailable")
            return None
        return await client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    async def lookup(self, query_embedding: List[float]) -> Optional[List[CachedChunk]]:
        """Search for a cached topic cluster matching the query.

        Args:
            query_embedding: The query's embedding vector.

        Returns:
            List of cached chunks on hit, None on miss.
        """
        if not self._config.enabled or not self._initialized:
            return None
        try:
            results = await self._collection.query(
                query_embeddings=[query_embedding],
                n_results=1,
                include=["metadatas", "distances"],
            )
            return await self._evaluate_topic_match(results)
        except Exception as exc:
            self._errors += 1
            logger.warning("Topic cache lookup error: %s", exc)
            return None

    async def _evaluate_topic_match(self, results: Dict) -> Optional[List[CachedChunk]]:
        """Evaluate ChromaDB result for topic match. Ref: #1376."""
        if not results or not results.get("ids") or not results["ids"][0]:
            self._misses += 1
            return None

        distance = results["distances"][0][0]
        similarity = 1.0 - distance

        if similarity < self._config.similarity_threshold:
            self._misses += 1
            return None

        meta = results["metadatas"][0][0]
        redis_key = meta.get("redis_key", "")
        if not redis_key:
            self._misses += 1
            return None

        chunks = await self._fetch_chunks(redis_key)
        if chunks is None:
            # Redis expired — clean up stale ChromaDB entry
            entry_id = results["ids"][0][0]
            await self._delete_entry(entry_id)
            self._misses += 1
            return None

        self._hits += 1
        logger.info("Topic cache HIT (sim=%.3f)", similarity)
        return chunks

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    async def store(
        self,
        chunk_embeddings: List[List[float]],
        chunks: List[CachedChunk],
    ) -> bool:
        """Cache retrieved chunks under their topic centroid.

        Args:
            chunk_embeddings: Embedding vectors for each chunk.
            chunks: The retrieved chunks to cache.

        Returns:
            True on success, False otherwise.
        """
        if not self._config.enabled or not self._initialized:
            return False
        if not chunks or not chunk_embeddings:
            return False
        try:
            centroid = compute_centroid(chunk_embeddings)
            if not centroid:
                return False
            return await self._persist_topic(centroid, chunks)
        except Exception as exc:
            self._errors += 1
            logger.warning("Topic cache store error: %s", exc)
            return False

    async def _persist_topic(
        self,
        centroid: List[float],
        chunks: List[CachedChunk],
    ) -> bool:
        """Write topic entry to Redis + ChromaDB. Ref: #1376."""
        topic_id = str(uuid.uuid4())
        redis_key = f"{_REDIS_KEY_PREFIX}{topic_id}"

        payload = [
            {"content": c.content, "metadata": c.metadata, "score": c.score}
            for c in chunks
        ]
        if not await self._store_chunks(redis_key, payload):
            return False

        await self._collection.add(
            ids=[topic_id],
            embeddings=[centroid],
            metadatas=[
                {
                    "redis_key": redis_key,
                    "chunk_count": len(chunks),
                    "created_at": time.time(),
                }
            ],
        )
        self._stores += 1
        await self._maybe_evict()
        return True

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    async def _fetch_chunks(self, key: str) -> Optional[List[CachedChunk]]:
        """Fetch cached chunks from Redis."""
        try:
            client = await get_redis_client(async_client=True, database=_REDIS_DATABASE)
            if client is None:
                return None
            raw = await client.get(key)
            if raw is None:
                return None
            data = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
            return [
                CachedChunk(
                    content=c["content"],
                    metadata=c.get("metadata", {}),
                    score=c.get("score", 0.0),
                )
                for c in data
            ]
        except Exception as exc:
            logger.debug("Redis fetch failed for %s: %s", key, exc)
            return None

    async def _store_chunks(self, key: str, payload: List[Dict]) -> bool:
        """Persist chunk list in Redis with TTL."""
        try:
            client = await get_redis_client(async_client=True, database=_REDIS_DATABASE)
            if client is None:
                return False
            await client.set(
                key,
                json.dumps(payload, default=str),
                ex=self._config.ttl,
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
            if count <= self._config.max_topics:
                return
            excess = count - self._config.max_topics + 50
            results = await self._collection.get(limit=excess, include=["metadatas"])
            if results and results.get("ids"):
                ids_to_delete = results["ids"]
                client = await get_redis_client(
                    async_client=True, database=_REDIS_DATABASE
                )
                if client:
                    for meta in results.get("metadatas", []):
                        rkey = meta.get("redis_key", "")
                        if rkey:
                            try:
                                await client.delete(rkey)
                            except Exception:
                                pass
                await self._collection.delete(ids=ids_to_delete)
                logger.info(
                    "Topic cache evicted %d entries (was %d)",
                    len(ids_to_delete),
                    count,
                )
        except Exception as exc:
            logger.debug("Topic cache eviction error: %s", exc)

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

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
            "max_topics": self._config.max_topics,
            "ttl": self._config.ttl,
        }

    def update_config(self, **kwargs) -> Dict[str, Any]:
        """Update cache configuration at runtime."""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
        logger.info("Topic cache config updated: %s", kwargs)
        return self.get_stats()


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_instance: Optional[TopicRetrievalCache] = None
_instance_lock = asyncio.Lock()


async def get_topic_retrieval_cache() -> TopicRetrievalCache:
    """Get or create the global TopicRetrievalCache singleton."""
    global _instance
    if _instance is None:
        async with _instance_lock:
            if _instance is None:
                _instance = TopicRetrievalCache()
                await _instance.initialize()
    return _instance
