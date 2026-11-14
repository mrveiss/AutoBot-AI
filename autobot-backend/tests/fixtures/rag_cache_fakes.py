# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""In-memory stand-ins for the semantic and topic retrieval caches' ChromaDB and Redis (#16664).

The real cache classes run unchanged over a fake collection that honours the ``where`` they send,
so a lookup that forgot its scope would hit another scope's entry here.
"""

from unittest.mock import AsyncMock

from services.semantic_query_cache import SemanticQueryCache
from services.topic_retrieval_cache import CachedChunk, TopicRetrievalCache


class FakeCollection:
    """The slice of a ChromaDB collection both caches use; every embedding is identical (distance 0)."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, dict]] = []
        self.where_seen: list[dict | None] = []

    async def add(self, ids, embeddings, metadatas):
        self.rows.extend(zip(ids, metadatas))

    async def query(self, query_embeddings, n_results, where=None, include=None):
        self.where_seen.append(where)
        rows = [r for r in self.rows if all(r[1].get(k) == v for k, v in (where or {}).items())]
        if not rows:
            return {"ids": [[]], "distances": [[]], "metadatas": [[]]}
        entry_id, meta = rows[0]
        return {"ids": [[entry_id]], "distances": [[0.0]], "metadatas": [[meta]]}

    async def count(self):
        return len(self.rows)

    async def delete(self, ids):
        self.rows = [r for r in self.rows if r[0] not in ids]


def make_semantic_cache() -> SemanticQueryCache:
    """A SemanticQueryCache over a FakeCollection and a dict standing in for Redis."""
    cache, redis = SemanticQueryCache(), {}
    cache._collection, cache._initialized = FakeCollection(), True
    cache._store_response = AsyncMock(side_effect=lambda key, payload: redis.update({key: payload}) or True)
    cache._fetch_response = AsyncMock(side_effect=lambda key: redis.get(key))
    return cache


def make_topic_cache() -> TopicRetrievalCache:
    """A TopicRetrievalCache over a FakeCollection and a dict standing in for Redis."""
    cache, redis = TopicRetrievalCache(), {}
    cache._collection, cache._initialized = FakeCollection(), True
    cache._store_chunks = AsyncMock(side_effect=lambda key, payload: redis.update({key: payload}) or True)
    cache._fetch_chunks = AsyncMock(
        side_effect=lambda key: [CachedChunk(c["content"], c["metadata"], c["score"]) for c in redis[key]]
    )
    return cache
