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

from datetime import datetime, timezone
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

from .core import AutoBotMemoryGraphCore

logger = get_logger(__name__)


def _is_entity_valid(entity: Dict[str, Any]) -> bool:
    """Return True if entity is currently valid.

    An entity is valid when valid_to is absent (None) or is a future timestamp.
    Entities without valid_to in Redis (legacy) are treated as valid.
    """
    valid_to = (entity.get("metadata") or {}).get("valid_to")
    if valid_to is None:
        return True
    # valid_to is an ISO-8601 string; compare lexicographically (works for UTC ISO strings)
    return valid_to > datetime.now(tz=timezone.utc).isoformat()


def _is_entity_valid_at(entity: Dict[str, Any], as_of: str) -> bool:
    """Return True if entity was valid at the given ISO-8601 timestamp.

    Conditions: valid_from <= as_of AND (valid_to IS NULL OR valid_to >= as_of)
    """
    metadata = entity.get("metadata") or {}
    valid_from = metadata.get("valid_from")
    valid_to = metadata.get("valid_to")

    if valid_from and valid_from > as_of:
        return False
    if valid_to is not None and valid_to < as_of:
        return False
    return True


class QueryOperationsMixin:
    """
    Mixin class providing search and query operations.

    This mixin is designed to be used with AutoBotMemoryGraphCore
    and provides semantic search capabilities.
    """

    def _build_redis_search_query(
        self: AutoBotMemoryGraphCore,
        query: str,
        entity_type: str | None = None,
        tags: List[str] | None = None,
        status: str | None = None,
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
            "FT.SEARCH",
            "memory_entity_idx",
            redis_query,
            "LIMIT",
            "0",
            str(limit),
            "RETURN",
            "3",
            "$.name",
            "$.type",
            "$.observations",
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
        entity_type: str | None,
    ) -> bool:
        """Check if entity matches search criteria (Issue #315 - extracted helper)."""
        if entity_type and entity.get("type") != entity_type:
            return False

        if not query_lower or query_lower == "*":
            return True

        if query_lower in entity.get("name", "").lower():
            return True

        return any(query_lower in obs.lower() for obs in entity.get("observations", []))

    async def _collect_entity_keys(
        self: AutoBotMemoryGraphCore,
        limit: int,
    ) -> List[str]:
        """
        Collect entity keys from Redis for fallback search.

        Issue #620.

        Args:
            limit: Maximum entities to eventually return (collects limit*10 keys)

        Returns:
            List of Redis keys for entity documents
        """
        keys = []
        async for key in self.redis_client.scan_iter(match="memory:entity:*"):
            keys.append(key)
            if len(keys) >= limit * 10:
                break
        return keys

    async def _batch_fetch_and_filter_entities(
        self: AutoBotMemoryGraphCore,
        keys: List[str],
        query_lower: str,
        entity_type: str | None,
        limit: int,
        include_expired: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fetch entities in batches and filter by query criteria.

        Issue #620.
        Issue #3790: added include_expired filter.

        Args:
            keys: List of Redis keys to fetch
            query_lower: Lowercase search query
            entity_type: Optional entity type filter
            limit: Maximum entities to return
            include_expired: When False (default), exclude invalidated entities

        Returns:
            List of matching entity dictionaries
        """
        batch_size = 50
        entities = []

        for i in range(0, len(keys), batch_size):
            batch_keys = keys[i : i + batch_size]

            pipe = self.redis_client.pipeline()
            for key in batch_keys:
                pipe.json().get(key)
            batch_results = await pipe.execute()

            for entity in batch_results:
                if not entity:
                    continue
                if not include_expired and not _is_entity_valid(entity):
                    continue
                if self._entity_matches_query(entity, query_lower, entity_type):
                    entities.append(entity)
                    if len(entities) >= limit:
                        return entities

        return entities

    async def _fallback_search(
        self: AutoBotMemoryGraphCore,
        query: str,
        entity_type: str | None,
        limit: int,
        include_expired: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fallback search when RediSearch is unavailable.

        Issue #315: Original refactoring.
        Issue #620: Further refactored using Extract Method pattern.
        Issue #3790: added include_expired filter.

        Args:
            query: Search query string
            entity_type: Optional entity type filter
            limit: Maximum results to return
            include_expired: When False (default), exclude invalidated entities

        Returns:
            List of matching entities
        """
        try:
            query_lower = query.lower() if query else ""
            keys = await self._collect_entity_keys(limit)

            if not keys:
                return []

            return await self._batch_fetch_and_filter_entities(
                keys, query_lower, entity_type, limit, include_expired=include_expired
            )

        except Exception as e:
            logger.error("Fallback search failed: %s", e)
            return []

    async def search_entities(
        self: AutoBotMemoryGraphCore,
        query: str,
        entity_type: str | None = None,
        tags: List[str] | None = None,
        status: str | None = None,
        limit: int = 50,
        include_expired: bool = False,
    ) -> List[Dict[str, Any]]:
        """Semantic search across all entities.

        Args:
            query: Search query (full-text search)
            entity_type: Filter by entity type
            tags: Filter by tags (any match)
            status: Filter by status
            limit: Maximum results to return
            include_expired: When False (default), exclude invalidated entities

        Returns:
            List of matching entities sorted by relevance
        """
        self.ensure_initialized()

        try:
            redis_query = self._build_redis_search_query(query, entity_type, tags, status)
            try:
                entities = await self._execute_redis_search(redis_query, limit)
                if not include_expired:
                    entities = [e for e in entities if _is_entity_valid(e)]
                logger.info("Search query '%s' returned %d results", query, len(entities))
                return entities
            except Exception as search_error:
                logger.warning("RediSearch failed, using fallback: %s", search_error)
                return await self._fallback_search(query, entity_type, limit, include_expired=include_expired)
        except Exception as e:
            logger.error("Search failed: %s", e)
            return []

    async def get_entities_as_of(
        self: AutoBotMemoryGraphCore,
        entity_type: str,
        as_of: str,
    ) -> List[Dict[str, Any]]:
        """Return entities of a given type that were valid at a specific point in time.

        Condition: valid_from <= as_of AND (valid_to IS NULL OR valid_to >= as_of)
        Entities without valid_from are treated as always valid from the beginning.

        Args:
            entity_type: Entity type to filter by
            as_of: ISO-8601 timestamp representing the point in time

        Returns:
            List of entity dictionaries valid at the given timestamp
        """
        self.ensure_initialized()

        try:
            keys = await self._collect_entity_keys(limit=1000)
            if not keys:
                return []

            pipe = self.redis_client.pipeline()
            for key in keys:
                pipe.json().get(key)
            raw_results = await pipe.execute()

            return [e for e in raw_results if e and e.get("type") == entity_type and _is_entity_valid_at(e, as_of)]

        except Exception as e:
            logger.error("get_entities_as_of failed: %s", e)
            return []
