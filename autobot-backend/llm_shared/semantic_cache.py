# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Semantic LLM Cache — Tier-3 similarity layer on top of LLMResponseCache.

Extends the L1/L2 exact-hash cache with a cosine-similarity lookup so that
semantically equivalent prompts (e.g. "What is Docker?" vs "Tell me about
Docker") share cached responses without a full LLM round-trip.

Implementation notes:
- Uses numpy brute-force cosine similarity (fits the ≤1 000-entry cap well)
- No new dependencies: numpy is already present in requirements.txt
- Embeddings generated via services.npu_client.generate_embedding_with_fallback
  (same pipeline as vector search — no extra LLM cost)
- Only applied to short prompts (< 2 000 chars) for classification / routing
- Issue: #8168
"""

import asyncio
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Maximum number of prompt embeddings held in the in-process HNSW-lite index.
_SEMANTIC_CACHE_MAX_ENTRIES = 1_000
# Cosine-distance threshold: distance < (1 - threshold) → semantic hit.
_SEMANTIC_CACHE_THRESHOLD = 0.95
# Only attempt semantic lookup for prompts shorter than this.
_SEMANTIC_CACHE_MAX_PROMPT_CHARS = 2_000


class SemanticLLMCache:
    """
    Thin semantic similarity layer wrapping an LLMResponseCache.

    Lookup order:
      1. Delegate to the wrapped exact cache (L1 memory + L2 Redis).
      2. On miss, if the prompt is short enough, compute an embedding and
         scan the in-memory index for a cosine-similar entry (threshold 0.95).
      3. On a semantic hit, return the previously cached response and
         insert the new prompt→response mapping into both caches.

    All public methods are thread-safe via asyncio.Lock.
    """

    def __init__(
        self,
        exact_cache: Any,
        max_entries: int = _SEMANTIC_CACHE_MAX_ENTRIES,
        threshold: float = _SEMANTIC_CACHE_THRESHOLD,
        max_prompt_chars: int = _SEMANTIC_CACHE_MAX_PROMPT_CHARS,
    ) -> None:
        self._exact = exact_cache
        self._threshold = threshold
        self._max_entries = max_entries
        self._max_prompt_chars = max_prompt_chars

        # Parallel arrays: embeddings matrix + (cache_key, response) pairs.
        self._embeddings: list[np.ndarray] = []
        self._entries: list[tuple[str, Any]] = []  # (cache_key, CachedResponse)
        self._entry_keys: set[str] = set()
        self._lock = asyncio.Lock()

        self._stats = {"semantic_hits": 0, "semantic_misses": 0, "entries": 0}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_cache_key(self, messages, model, temperature, top_k=40, top_p=0.9):
        """Delegate key generation to the wrapped exact cache."""
        return self._exact.generate_cache_key(messages, model, temperature, top_k, top_p)

    async def get(self, cache_key: str, prompt: str | None = None) -> Any | None:
        """
        Two-tier lookup: exact first, then semantic if prompt provided.

        Args:
            cache_key: Hash key from generate_cache_key().
            prompt:    Raw prompt text used to generate cache_key.  Required
                       for semantic fallback; pass None to skip tier-2.

        Returns:
            CachedResponse on hit, None on miss.
        """
        # Tier 1 — exact
        result = await self._exact.get(cache_key)
        if result is not None:
            return result

        # Tier 2 — semantic
        if prompt is None or len(prompt) > self._max_prompt_chars:
            self._stats["semantic_misses"] += 1
            return None

        try:
            embedding = await self._embed(prompt)
        except Exception as exc:
            logger.debug("SemanticLLMCache: embedding failed (non-critical): %s", exc)
            self._stats["semantic_misses"] += 1
            return None

        async with self._lock:
            hit_key, hit_response = self._cosine_lookup(embedding)

        if hit_response is not None:
            self._stats["semantic_hits"] += 1
            logger.debug("SemanticLLMCache: semantic hit for cache_key=%s...", cache_key[:16])
            # Backfill exact caches so the next identical prompt skips tier-2.
            await self._exact.set(cache_key, hit_response)
            # Also register this new embedding so future similar prompts match it.
            async with self._lock:
                self._add_entry(embedding, cache_key, hit_response)
            return hit_response

        self._stats["semantic_misses"] += 1
        return None

    async def set(self, cache_key: str, response: Any, prompt: str | None = None, skip_redis: bool = False) -> None:
        """
        Store in exact cache and, when prompt is provided, register the
        embedding in the semantic index.

        Args:
            cache_key:  Hash key.
            response:   CachedResponse to store.
            prompt:     Raw prompt text (optional; required for semantic index).
            skip_redis: Passed through to the underlying exact cache.
        """
        await self._exact.set(cache_key, response, skip_redis=skip_redis)

        if prompt is None or len(prompt) > self._max_prompt_chars:
            return

        try:
            embedding = await self._embed(prompt)
        except Exception as exc:
            logger.debug("SemanticLLMCache: embedding for set failed (non-critical): %s", exc)
            return

        async with self._lock:
            self._add_entry(embedding, cache_key, response)

    def get_stats(self) -> dict:
        """Return combined stats from both cache tiers."""
        base = self._exact.get_stats()
        base["semantic_hits"] = self._stats["semantic_hits"]
        base["semantic_misses"] = self._stats["semantic_misses"]
        base["semantic_entries"] = self._stats["entries"]
        return base

    # Delegate remaining protocol methods to exact cache.
    def evict(self, count: int) -> int:
        return self._exact.evict(count)

    async def clear(self) -> None:
        self._exact.clear()
        async with self._lock:
            self._embeddings.clear()
            self._entries.clear()
            self._entry_keys.clear()
            self._stats["entries"] = 0

    async def clear_all(self) -> dict:
        result = await self._exact.clear_all()
        async with self._lock:
            self._embeddings.clear()
            self._entries.clear()
            self._entry_keys.clear()
            self._stats["entries"] = 0
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _embed(self, text: str) -> np.ndarray:
        """Generate a unit-normalised embedding for *text*."""
        from services.npu_client import generate_embedding_with_fallback

        raw = await generate_embedding_with_fallback(text)
        vec = np.asarray(raw, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def _cosine_lookup(self, query_vec: np.ndarray) -> tuple[str | None, Any | None]:
        """
        Brute-force cosine similarity scan over the in-memory index.

        Cosine distance for unit vectors = 1 - dot(a, b).
        Returns (cache_key, response) on hit, (None, None) on miss.
        Must be called inside self._lock.
        """
        if not self._embeddings:
            return None, None

        matrix = np.stack(self._embeddings)  # (N, D)
        scores = matrix @ query_vec  # cosine similarities
        best_idx = int(np.argmax(scores))
        best_score = float(scores[best_idx])

        if best_score >= self._threshold:
            key, response = self._entries[best_idx]
            return key, response

        return None, None

    def _add_entry(self, embedding: np.ndarray, cache_key: str, response: Any) -> None:
        """Insert a new embedding+entry pair. Deduplicates by cache_key. Evicts oldest when full.
        Must be called inside self._lock."""
        if cache_key in self._entry_keys:
            return
        if len(self._entries) >= self._max_entries:
            self._embeddings.pop(0)
            evicted_key, _ = self._entries.pop(0)
            self._entry_keys.discard(evicted_key)
            self._stats["entries"] = max(0, self._stats["entries"] - 1)
        self._embeddings.append(embedding)
        self._entries.append((cache_key, response))
        self._entry_keys.add(cache_key)
        self._stats["entries"] += 1
