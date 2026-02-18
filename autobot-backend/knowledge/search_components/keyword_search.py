# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Keyword Search Module

Issue #381: Extracted from search.py god class refactoring.
Contains keyword-based search functionality using Redis.
"""

import logging
from typing import Any, Dict, List, Optional, Set

from .helpers import (
    build_search_result,
    decode_redis_hash,
    matches_category,
    score_fact_by_terms,
)

logger = logging.getLogger(__name__)


class KeywordSearcher:
    """
    Performs keyword-based search using Redis.

    Features:
    - Term matching against fact content
    - Category filtering
    - Batch processing with Redis pipelines
    - Efficient cursor-based scanning
    """

    def __init__(self, redis_client=None):
        """Initialize keyword searcher with Redis client."""
        self.redis_client = redis_client

    async def process_keyword_batch(
        self, keys: list, query_terms: Set[str], category: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Process a batch of Redis keys for keyword search. Issue #281: Extracted helper."""
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
            score = score_fact_by_terms(decoded, query_terms)
            if score > 0:
                results.append(build_search_result(decoded, key, score))
        return results

    async def search(
        self, query: str, limit: int, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Perform keyword-based search using Redis (Issue #281 refactor)."""
        try:
            if not self.redis_client:
                return []

            query_terms = set(query.lower().split())
            if not query_terms:
                return []

            results: List[Dict[str, Any]] = []
            cursor = b"0"
            scanned = 0
            max_scan = 10000

            while scanned < max_scan:
                cursor, keys = await self.redis_client.scan(
                    cursor=cursor, match="fact:*", count=100
                )
                scanned += len(keys)

                if keys:
                    batch_results = await self.process_keyword_batch(
                        keys, query_terms, category
                    )
                    results.extend(batch_results)

                if cursor == b"0":
                    break

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]

        except Exception as e:
            logger.error("Keyword search failed: %s", e)
            return []
