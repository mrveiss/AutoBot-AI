# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tag Filtering Module

Issue #381: Extracted from search.py god class refactoring.
Contains tag-based filtering functionality.
"""

import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class TagFilter:
    """
    Handles tag-based filtering for search results.

    Supports both AND (match_all) and OR (match_any) logic
    for combining multiple tag filters.
    """

    def __init__(self, redis_client=None):
        """Initialize tag filter with Redis client."""
        self.redis_client = redis_client

    def decode_tag_results(self, tag_results: list) -> List[Set[str]]:
        """Decode tag results from Redis to sets of fact IDs. Issue #281: Extracted helper."""
        tag_fact_sets = []
        for fact_ids in tag_results:
            if fact_ids:
                decoded_ids = {
                    fid.decode("utf-8") if isinstance(fid, bytes) else fid
                    for fid in fact_ids
                }
                tag_fact_sets.append(decoded_ids)
            else:
                tag_fact_sets.append(set())
        return tag_fact_sets

    def combine_tag_fact_sets(
        self, tag_fact_sets: List[Set[str]], match_all: bool
    ) -> Set[str]:
        """Combine fact sets based on match_all flag. Issue #281: Extracted helper."""
        if not tag_fact_sets:
            return set()
        if match_all:
            result_ids = tag_fact_sets[0]
            for fact_set in tag_fact_sets[1:]:
                result_ids = result_ids.intersection(fact_set)
        else:
            result_ids = set()
            for fact_set in tag_fact_sets:
                result_ids = result_ids.union(fact_set)
        return result_ids

    async def get_fact_ids_by_tags(
        self, tags: List[str], match_all: bool = True
    ) -> Dict[str, Any]:
        """Get fact IDs matching specified tags (Issue #281 refactor)."""
        try:
            if not self.redis_client:
                return {
                    "success": False,
                    "fact_ids": set(),
                    "message": "Redis not initialized",
                }

            normalized_tags = [t.lower().strip() for t in tags if t.strip()]
            if not normalized_tags:
                return {
                    "success": False,
                    "fact_ids": set(),
                    "message": "No valid tags",
                }

            pipeline = self.redis_client.pipeline()
            for tag in normalized_tags:
                pipeline.smembers(f"tag:{tag}")
            tag_results = await pipeline.execute()

            tag_fact_sets = self.decode_tag_results(tag_results)
            result_ids = self.combine_tag_fact_sets(tag_fact_sets, match_all)

            return {"success": True, "fact_ids": result_ids}

        except Exception as e:
            logger.error("Failed to get fact IDs by tags: %s", e)
            return {"success": False, "fact_ids": set(), "error": str(e)}

    async def get_tag_filtered_ids(
        self,
        tags: Optional[List[str]],
        tags_match_any: bool,
        processed_query: str,
    ) -> tuple:
        """
        Get tag-filtered fact IDs.

        Returns:
            Tuple of (filtered_ids, early_return_response or None)
        """
        if not tags:
            return None, None

        tag_result = await self.get_fact_ids_by_tags(tags, match_all=not tags_match_any)
        if tag_result["success"]:
            tag_filtered_ids = tag_result["fact_ids"]
            if not tag_filtered_ids:
                return None, {
                    "success": True,
                    "results": [],
                    "total_count": 0,
                    "query_processed": processed_query,
                    "message": "No facts match the specified tags",
                }
            return tag_filtered_ids, None
        return None, None

    def apply_tag_filter(
        self, results: List[Dict[str, Any]], tag_filtered_ids: Optional[Set[str]]
    ) -> List[Dict[str, Any]]:
        """Apply tag filtering to results."""
        if tag_filtered_ids is None:
            return results
        return [
            r
            for r in results
            if r.get("metadata", {}).get("fact_id") in tag_filtered_ids
        ]
