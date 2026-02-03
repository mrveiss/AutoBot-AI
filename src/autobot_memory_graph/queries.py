# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Memory Graph - Query Operations Module

This module contains search and query operations:
- search_entities with RediSearch
- Fallback search when RediSearch unavailable
- Query building helpers

Part of the modular autobot_memory_graph package (Issue #716).
"""

import logging
from typing import Any, Dict, List, Optional

from .core import AutoBotMemoryGraphCore

logger = logging.getLogger(__name__)


class QueryOperationsMixin:
    """
    Mixin class providing search and query operations.

    This mixin is designed to be used with AutoBotMemoryGraphCore
    and provides semantic search capabilities.
    """

    def _build_redis_search_query(
        self: AutoBotMemoryGraphCore,
        query: str,
        entity_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
    ) -> str:
        """Issue #665: Extracted from search_entities to reduce function length.

        Build a RediSearch query string from search parameters.

        Args:
            query: Text search query
            entity_type: Filter by entity type
            tags: Filter by tags (any match)
            status: Filter by status

        Returns:
            RediSearch query string
        """
        query_parts = []
        if entity_type:
            query_parts.append(f"@type:{{{entity_type}}}")
        if status:
            query_parts.append(f"@status:{{{status}}}")
        if tags:
            tag_filter = "|".join(tags)
            query_parts.append(f"@tags:{{{tag_filter}}}")
        if query and query != "*":
            query_parts.append(f"({query})")
        return " ".join(query_parts) if query_parts else "*"

    async def _execute_redis_search(
        self: AutoBotMemoryGraphCore,
        redis_query: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Issue #665: Extracted from search_entities to reduce function length.

        Execute RediSearch FT.SEARCH command and parse results.

        Args:
            redis_query: RediSearch query string
            limit: Maximum results to return

        Returns:
            List of matching entity dictionaries
        """
        results = await self.redis_client.execute_command(
            "FT.SEARCH", "memory_entity_idx", redis_query,
            "LIMIT", "0", str(limit),
            "RETURN", "3", "$.name", "$.type", "$.observations",
        )
        return await self._parse_search_results(results, limit)

    async def _parse_search_results(
        self: AutoBotMemoryGraphCore,
        results: list,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Parse RediSearch results and fetch full entities (Issue #315: extracted).

        Args:
            results: Raw RediSearch FT.SEARCH results
            limit: Maximum entities to return

        Returns:
            List of parsed entity dictionaries
        """
        entities = []
        if not results or len(results) <= 1:
            return entities

        for i in range(1, len(results), 2):
            if i + 1 >= len(results):
                continue

            entity_key = results[i]
            if isinstance(entity_key, bytes):
                entity_key = entity_key.decode()

            entity = await self.redis_client.json().get(entity_key)
            if entity:
                entities.append(entity)

        return entities[:limit]

    def _entity_matches_query(
        self: AutoBotMemoryGraphCore,
        entity: Dict[str, Any],
        query_lower: str,
        entity_type: Optional[str],
    ) -> bool:
        """Check if entity matches search criteria (Issue #315 - extracted helper)."""
        if entity_type and entity.get("type") != entity_type:
            return False

        if not query_lower or query_lower == "*":
            return True

        if query_lower in entity.get("name", "").lower():
            return True

        return any(
            query_lower in obs.lower() for obs in entity.get("observations", [])
        )

    async def _fallback_search(
        self: AutoBotMemoryGraphCore,
        query: str,
        entity_type: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Fallback search when RediSearch is unavailable (Issue #315 - refactored).

        Args:
            query: Search query string
            entity_type: Optional entity type filter
            limit: Maximum results to return

        Returns:
            List of matching entities
        """
        try:
            query_lower = query.lower() if query else ""

            # Issue #614: Fix N+1 pattern - collect keys first, then batch fetch
            keys = []
            async for key in self.redis_client.scan_iter(match="memory:entity:*"):
                keys.append(key)
                if len(keys) >= limit * 10:
                    break

            if not keys:
                return []

            batch_size = 50
            entities = []

            for i in range(0, len(keys), batch_size):
                batch_keys = keys[i:i + batch_size]

                pipe = self.redis_client.pipeline()
                for key in batch_keys:
                    pipe.json().get(key)
                batch_results = await pipe.execute()

                for entity in batch_results:
                    if entity and self._entity_matches_query(
                        entity, query_lower, entity_type
                    ):
                        entities.append(entity)
                        if len(entities) >= limit:
                            return entities

            return entities

        except Exception as e:
            logger.error("Fallback search failed: %s", e)
            return []

    async def search_entities(
        self: AutoBotMemoryGraphCore,
        query: str,
        entity_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Semantic search across all entities.

        Args:
            query: Search query (full-text search)
            entity_type: Filter by entity type
            tags: Filter by tags (any match)
            status: Filter by status
            limit: Maximum results to return

        Returns:
            List of matching entities sorted by relevance
        """
        self.ensure_initialized()

        try:
            redis_query = self._build_redis_search_query(
                query, entity_type, tags, status
            )
            try:
                entities = await self._execute_redis_search(redis_query, limit)
                logger.info(
                    "Search query '%s' returned %d results", query, len(entities)
                )
                return entities
            except Exception as search_error:
                logger.warning("RediSearch failed, using fallback: %s", search_error)
                return await self._fallback_search(query, entity_type, limit)
        except Exception as e:
            logger.error("Search failed: %s", e)
            return []
