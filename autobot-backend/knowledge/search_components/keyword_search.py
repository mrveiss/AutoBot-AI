# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Keyword Search Module

Issue #381: Extracted from search.py god class refactoring.
Issue #1720: Upgraded keyword scoring to BM25 Okapi (IDF + length normalization).
Contains keyword-based search functionality using Redis.
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Set

from autobot_shared.env_utils import env_float_clamped, env_int_clamped
from autobot_shared.logging_manager import get_logger

from .bm25 import BM25Scorer
from .helpers import build_search_result, decode_redis_hash, matches_category

logger = get_logger(__name__)

_CORPUS_STATS_KEY = "bm25:corpus_stats"
_DEFAULT_TOTAL_DOCS = 1
_DEFAULT_AVG_LENGTH = 50.0
#: A recompute reads every fact, so writes in quick succession share one (#19726).
BM25_REFRESH_MIN_INTERVAL_S = env_float_clamped("AUTOBOT_KB_BM25_REFRESH_MIN_INTERVAL_S", 60.0, 1.0, 3600.0)
#: Facts one keyword search reads at most: without an index it reads them one by one (#19726).
KEYWORD_SEARCH_MAX_SCAN = env_int_clamped("AUTOBOT_KB_KEYWORD_SEARCH_MAX_SCAN", 10000, 100, 1000000)


class KeywordSearcher:
    """
    Performs keyword-based search using Redis with BM25 Okapi scoring.

    Features:
    - BM25 scoring: IDF + TF saturation + document length normalization (#1720)
    - Category filtering
    - Batch processing with Redis pipelines
    - Efficient cursor-based scanning
    - Corpus statistics cached at Redis key ``bm25:corpus_stats``
    """

    def __init__(self, redis_client=None):
        """Initialize keyword searcher with Redis client."""
        self.redis_client = redis_client
        self._bm25: BM25Scorer | None = None
        self._refresh_wanted = False
        self._refresh_task: asyncio.Task | None = None
        self._next_refresh = float("-inf")
        self._flush = asyncio.Event()

    # ------------------------------------------------------------------
    # Corpus statistics
    # ------------------------------------------------------------------

    async def _load_corpus_stats(self) -> BM25Scorer:
        """
        Load BM25 corpus statistics from Redis and return a scorer (#1720).

        Falls back to default stats when the key is absent so the searcher
        degrades gracefully before the first recompute_corpus_stats() call.
        """
        try:
            raw = await self.redis_client.get(_CORPUS_STATS_KEY)
            if raw:
                stats = json.loads(raw)
                return BM25Scorer(
                    total_docs=stats.get("total_docs", _DEFAULT_TOTAL_DOCS),
                    avg_doc_length=stats.get("avg_doc_length", _DEFAULT_AVG_LENGTH),
                    doc_frequencies=stats.get("doc_frequencies", {}),
                )
        except Exception as exc:
            logger.warning("Failed to load BM25 corpus stats: %s", exc)
        return BM25Scorer(_DEFAULT_TOTAL_DOCS, _DEFAULT_AVG_LENGTH, {})

    async def _get_bm25(self) -> BM25Scorer:
        """Return cached BM25Scorer, loading from Redis on first call (#1720).

        When the corpus stats key is absent (first run or after flush),
        triggers an initial ``recompute_corpus_stats()`` so BM25 uses
        real IDF values instead of falling back to defaults (#2033).
        Uses Redis EXISTS check instead of comparing total_docs to avoid
        false-positive recompute on single-document KBs (#2082).
        """
        if self._bm25 is None:
            stats_exist = False
            if self.redis_client:
                try:
                    stats_exist = await self.redis_client.exists(_CORPUS_STATS_KEY)
                except Exception:
                    pass
            self._bm25 = await self._load_corpus_stats()
            if not stats_exist:
                await self.recompute_corpus_stats()
                self._bm25 = await self._load_corpus_stats()
        return self._bm25

    def _invalidate_bm25_cache(self) -> None:
        """Discard cached BM25Scorer so the next search reloads from Redis."""
        self._bm25 = None

    async def recompute_corpus_stats(self) -> bool:
        """
        Scan all ``fact:*`` keys and persist BM25 corpus stats to Redis (#1720).

        Call this after facts are added or removed so IDF values stay current.
        Stats are stored as JSON at ``bm25:corpus_stats``. Returns whether they were.
        """
        if not self.redis_client:
            return False
        try:
            total_docs = 0
            total_length = 0
            doc_freq: Dict[str, int] = {}

            cursor = b"0"
            while True:
                cursor, keys = await self.redis_client.scan(cursor=cursor, match="fact:*", count=100)
                if keys:
                    pipeline = self.redis_client.pipeline()
                    for key in keys:
                        pipeline.hgetall(key)
                    facts_data = await pipeline.execute()

                    for fact_data in facts_data:
                        if not fact_data:
                            continue
                        content = fact_data.get(b"content", b"") or fact_data.get("content", "")
                        if isinstance(content, bytes):
                            content = content.decode("utf-8", errors="replace")
                        tokens = content.lower().split()
                        total_docs += 1
                        total_length += len(tokens)
                        for term in set(tokens):
                            doc_freq[term] = doc_freq.get(term, 0) + 1

                if cursor == b"0":
                    break

            avg_len = float(total_length) / max(total_docs, 1)
            stats = {
                "total_docs": total_docs,
                "avg_doc_length": avg_len,
                "doc_frequencies": doc_freq,
            }
            await self.redis_client.set(_CORPUS_STATS_KEY, json.dumps(stats, ensure_ascii=False))
            self._invalidate_bm25_cache()
            logger.info(
                "BM25 corpus stats recomputed: %d docs, avg_len=%.1f, vocab=%d",
                total_docs,
                avg_len,
                len(doc_freq),
            )
            return True
        except Exception as exc:
            logger.error("Failed to recompute BM25 corpus stats: %s", exc)
            return False

    def request_refresh(self) -> None:
        """Ask for a recompute after a write: one runs at a time, at most once per interval (#19726)."""
        self._refresh_wanted = True
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._run_refreshes())

    async def _wait_for_next_refresh(self) -> None:
        """Until the interval has passed, or a flush asks for it now."""
        delay = self._next_refresh - time.monotonic()
        if delay > 0:
            try:
                await asyncio.wait_for(self._flush.wait(), delay)
            except TimeoutError:
                pass

    async def _run_refreshes(self) -> None:
        while self._refresh_wanted:
            await self._wait_for_next_refresh()
            self._refresh_wanted = False
            succeeded = await self.recompute_corpus_stats()
            self._next_refresh = time.monotonic() + BM25_REFRESH_MIN_INTERVAL_S
            if not succeeded and not self._flush.is_set():  # tried again after the interval, unless exiting
                self._refresh_wanted = True

    async def flush_refresh(self) -> None:
        """Finish what's running and run what's waiting now, for a process whose loop would cancel it."""
        if self._refresh_task is None or self._refresh_task.done():
            return
        self._flush.set()
        await asyncio.gather(self._refresh_task, return_exceptions=True)
        self._flush.clear()

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    def _doc_length(self, decoded: Dict[str, str]) -> int:
        """Return token count for a decoded fact's content field."""
        return len(decoded.get("content", "").split())

    async def process_keyword_batch(
        self,
        keys: list,
        query_terms: Set[str],
        category: str | None,
        bm25: BM25Scorer,
    ) -> List[Dict[str, Any]]:
        """
        Process a batch of Redis keys for BM25 keyword search (#1720).

        Issue #281: Extracted helper. Replaces TF-only score_fact_by_terms().
        """
        results = []
        pipeline = self.redis_client.pipeline()
        for key in keys:
            pipeline.hgetall(key)
        facts_data = await pipeline.execute()

        for key, fact_data in zip(keys, facts_data):
            if not fact_data:
                continue
            decoded = decode_redis_hash(fact_data)
            if not matches_category(decoded, category):
                continue
            score = bm25.score(
                list(query_terms),
                decoded.get("content", ""),
                self._doc_length(decoded),
            )
            if score > 0:
                results.append(build_search_result(decoded, key, score))
        return results

    # ------------------------------------------------------------------
    # Search entry point
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int, category: str | None = None) -> List[Dict[str, Any]]:
        """Perform BM25 keyword search using Redis (Issue #1720 upgrade)."""
        try:
            if not self.redis_client:
                return []

            query_terms = set(query.lower().split())
            if not query_terms:
                return []

            bm25 = await self._get_bm25()
            results: List[Dict[str, Any]] = []
            cursor = b"0"
            scanned = 0

            while scanned < KEYWORD_SEARCH_MAX_SCAN:
                cursor, keys = await self.redis_client.scan(cursor=cursor, match="fact:*", count=100)
                scanned += len(keys)

                if keys:
                    batch_results = await self.process_keyword_batch(keys, query_terms, category, bm25)
                    results.extend(batch_results)

                if cursor == b"0":
                    break
            else:
                logger.warning("Keyword search stopped after %d facts; later facts weren't read", scanned)

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]

        except Exception as e:
            logger.error("Keyword search failed: %s", e)
            return []
