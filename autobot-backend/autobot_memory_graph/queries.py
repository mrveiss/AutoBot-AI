# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Memory Graph - Query Operations Module

This module contains search and query operations:
- search_entities with RediSearch
- Fallback search when RediSearch unavailable
- Query building helpers

Part of the modular autobot_memory_graph package (Issue #716).
"""

from dataclasses import dataclass
from typing import Any, Dict, List

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.security.input_sanitizer import escape_redisearch, escape_redisearch_tag
from knowledge.serving import is_servable

from .core import AutoBotMemoryGraphCore
from .owner_scope import UNSCOPED_ALL_USERS, entity_visible, redis_owner_clause, require_scope

logger = get_logger(__name__)

_FETCH_BATCH_SIZE = 50

#: Most ``memory:entity:*`` keys one scan-fallback call may examine (#18825). The scan filters by owner while
#: it walks, so without a ceiling one request could walk every owner's keyspace.
_SCAN_KEY_BUDGET = env_int_clamped("AUTOBOT_MEMORY_GRAPH_SCAN_KEY_BUDGET", 20000, min_v=1, max_v=1_000_000)


@dataclass
class _ScanStats:
    """What one scan examined and whether the budget cut it short."""

    examined: int = 0
    truncated: bool = False


def _owner_kind(owner: Any) -> str:
    """Log-safe owner kind: never an id."""
    return "unscoped_all_users" if owner is UNSCOPED_ALL_USERS else "user"


def _is_entity_valid(entity: Dict[str, Any]) -> bool:
    """Return True if entity is currently valid, by the one serving predicate (#18829).

    Timestamps are parsed, never compared as strings, and an unparseable
    ``valid_from`` / ``valid_to`` fails closed. Entities without ``valid_to``
    (legacy, or still open) stay valid.
    """
    return is_servable(entity)


def _is_entity_valid_at(entity: Dict[str, Any], as_of: str) -> bool:
    """Return True if entity was valid at the given ISO-8601 timestamp (#18829).

    Conditions: valid_from <= as_of AND (valid_to IS NULL OR valid_to >= as_of),
    judged on parsed instants; an unparseable bound fails closed. An unparseable
    *as_of* raises ``ValueError`` -- that is the caller's input, not the entity's.
    """
    return is_servable(entity, as_of=as_of)


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
        owner: Any = None,
    ) -> str:
        """Issue #665: Extracted from search_entities to reduce function length.

        Build a RediSearch query string from search parameters.

        Args:
            query: Text search query
            entity_type: Filter by entity type
            tags: Filter by tags (any match)
            status: Filter by status
            owner: Required OwnerScope / UNSCOPED_ALL_USERS (#18825); raises if omitted

        Returns:
            RediSearch query string
        """
        # #13762: every value here is caller-supplied. Unescaped, punctuation is
        # read as query syntax — a term stops being a term and becomes a field
        # selector, a wildcard, or a boolean operator. The MCP surface reaches
        # this without the Pydantic bounds the REST surface applies, so the
        # escaping lives here rather than depending on every caller validating.
        query_parts = []
        owner_clause = redis_owner_clause(owner)  # raises OwnerScopeRequired when omitted
        if owner_clause:
            query_parts.append(owner_clause)
        if entity_type:
            query_parts.append(f"@type:{{{escape_redisearch_tag(entity_type)}}}")
        if status:
            query_parts.append(f"@status:{{{escape_redisearch_tag(status)}}}")
        if tags:
            tag_filter = "|".join(escape_redisearch_tag(tag) for tag in tags)
            query_parts.append(f"@tags:{{{tag_filter}}}")
        if query and query != "*":
            query_parts.append(f"({escape_redisearch(query)})")
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
        tags: List[str] | None = None,
        status: str | None = None,
    ) -> bool:
        """Check if entity matches search criteria (Issue #315 - extracted helper).

        #18825: ``tags`` / ``status`` are honoured here too, so the scan fallback
        applies the same filters RediSearch does.
        """
        if entity_type and entity.get("type") != entity_type:
            return False
        metadata = entity.get("metadata") or {}
        if status and metadata.get("status") != status:
            return False
        if tags and not set(tags) & set(metadata.get("tags") or []):
            return False

        if not query_lower or query_lower == "*":
            return True

        if query_lower in entity.get("name", "").lower():
            return True

        return any(query_lower in obs.lower() for obs in entity.get("observations", []))

    async def _scan_entity_key_batches(self: AutoBotMemoryGraphCore, owner: Any, stats: _ScanStats):
        """Yield entity keys in ``_FETCH_BATCH_SIZE`` batches, examining at most ``_SCAN_KEY_BUDGET`` keys.

        Callers filter per batch and stop at their own result limit, so other owners' keys cannot
        starve a scoped caller within the budget (#18825, #620). Past the budget the scan stops, sets
        ``stats.truncated`` and logs a warning (budget, keys examined, owner kind; no ids): the caller
        returns what it has, and a per-owner index is the real fix.
        """
        batch: List[str] = []
        async for key in self.redis_client.scan_iter(match="memory:entity:*"):
            if stats.examined >= _SCAN_KEY_BUDGET:
                stats.truncated = True
                logger.warning(
                    "memory-graph scan budget exhausted: budget=%d examined=%d owner_kind=%s; results incomplete",
                    _SCAN_KEY_BUDGET,
                    stats.examined,
                    _owner_kind(owner),
                )
                break
            stats.examined += 1
            batch.append(key)
            if len(batch) >= _FETCH_BATCH_SIZE:
                yield batch
                batch = []
        if batch:
            yield batch

    async def _iter_entity_batches(self: AutoBotMemoryGraphCore, keys: List[str]):
        """Yield the document under each key (None when absent), pipelined 50 keys per round trip."""
        for i in range(0, len(keys), _FETCH_BATCH_SIZE):
            pipe = self.redis_client.pipeline()
            for key in keys[i : i + _FETCH_BATCH_SIZE]:
                pipe.json().get(key)
            for entity in await pipe.execute():
                yield entity

    async def readable_entity_ids(self: AutoBotMemoryGraphCore, entity_ids: List[str], *, owner: Any) -> set[str]:
        """The subset of ``entity_ids`` that exist and ``owner`` may read: batched, not one get per id (#18825)."""
        require_scope(owner)
        unique = list(dict.fromkeys(i for i in entity_ids if i))
        docs = [d async for d in self._iter_entity_batches([f"memory:entity:{i}" for i in unique])]
        return {i for i, doc in zip(unique, docs) if entity_visible(doc, owner)}

    async def _readable_relation_ends(
        self: AutoBotMemoryGraphCore, entity_id: str, relations: List[Dict[str, Any]], end: str, owner: Any
    ) -> set[str] | None:
        """Ids at the ``end`` ("to"/"from") of ``relations`` that ``owner`` may read.

        Empty when ``entity_id`` itself is not readable.

        ``None`` means "do not filter" (UNSCOPED_ALL_USERS). One batched check for every distinct
        endpoint, never one get per edge (#18825).
        """
        if require_scope(owner) is UNSCOPED_ALL_USERS:
            return None
        readable = await self.readable_entity_ids([entity_id] + [r.get(end) for r in relations], owner=owner)
        return readable if entity_id in readable else set()  # an unreadable anchor exposes none of its edges

    async def _batch_fetch_and_filter_entities(
        self: AutoBotMemoryGraphCore,
        keys: List[str],
        query_lower: str,
        entity_type: str | None,
        limit: int,
        include_expired: bool = False,
        *,
        owner: Any,
        tags: List[str] | None = None,
        status: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Fetch entities in batches, keep up to ``limit`` that match the query and ``owner`` may read.

        Issue #620, #3790 (``include_expired``), #18825 (``owner`` is required).
        """
        require_scope(owner)
        entities: List[Dict[str, Any]] = []
        async for entity in self._iter_entity_batches(keys):
            if not entity or (not include_expired and not _is_entity_valid(entity)):
                continue
            if entity_visible(entity, owner) and self._entity_matches_query(
                entity, query_lower, entity_type, tags, status
            ):
                entities.append(entity)
                if len(entities) >= limit:
                    break
        return entities

    async def _fallback_search(
        self: AutoBotMemoryGraphCore,
        query: str,
        entity_type: str | None,
        limit: int,
        include_expired: bool = False,
        *,
        owner: Any,
        tags: List[str] | None = None,
        status: str | None = None,
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
            owner: Required OwnerScope / UNSCOPED_ALL_USERS (#18825)
            tags: Tag filter (any match) -- kept on this path (#18825)
            status: Status filter -- kept on this path (#18825)

        Returns:
            List of matching entities
        """
        require_scope(owner)
        try:
            query_lower = query.lower() if query else ""
            matches: List[Dict[str, Any]] = []
            async for keys in self._scan_entity_key_batches(owner, _ScanStats()):
                matches.extend(
                    await self._batch_fetch_and_filter_entities(
                        keys,
                        query_lower,
                        entity_type,
                        limit - len(matches),
                        include_expired=include_expired,
                        owner=owner,
                        tags=tags,
                        status=status,
                    )
                )
                if len(matches) >= limit:
                    break
            return matches

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
        *,
        owner: Any,
    ) -> List[Dict[str, Any]]:
        """Semantic search across the entities ``owner`` may read.

        Args:
            query: Search query (full-text search)
            entity_type: Filter by entity type
            tags: Filter by tags (any match)
            status: Filter by status
            limit: Maximum results to return
            include_expired: When False (default), exclude invalidated entities
            owner: REQUIRED (#18825) -- an OwnerScope, or UNSCOPED_ALL_USERS for
                system callers. Omitting it raises OwnerScopeRequired (fails closed).

        Returns:
            List of matching entities sorted by relevance
        """
        self.ensure_initialized()
        require_scope(owner)

        try:
            redis_query = self._build_redis_search_query(query, entity_type, tags, status, owner)
            try:
                entities = await self._execute_redis_search(redis_query, limit)
                entities = [
                    e for e in entities if entity_visible(e, owner)
                ]  # backstop: the query already carries the owner/org clause
                if not include_expired:
                    entities = [e for e in entities if _is_entity_valid(e)]
                logger.info("Search query '%s' returned %d results", query, len(entities))
                return entities
            except Exception as search_error:
                logger.warning("RediSearch failed, using fallback: %s", search_error)
                return await self._fallback_search(
                    query, entity_type, limit, include_expired=include_expired, owner=owner, tags=tags, status=status
                )
        except Exception as e:
            logger.error("Search failed: %s", e)
            return []

    async def get_entities_as_of(
        self: AutoBotMemoryGraphCore,
        entity_type: str,
        as_of: str,
        *,
        owner: Any,
    ) -> List[Dict[str, Any]]:
        """Return entities of a given type that were valid at a specific point in time.

        Condition: valid_from <= as_of AND (valid_to IS NULL OR valid_to >= as_of)
        Entities without valid_from are treated as always valid from the beginning.

        Args:
            entity_type: Entity type to filter by
            as_of: ISO-8601 timestamp representing the point in time
            owner: REQUIRED OwnerScope / UNSCOPED_ALL_USERS (#18825)

        Returns:
            List of entity dictionaries valid at the given timestamp
        """
        self.ensure_initialized()
        require_scope(owner)

        try:
            found: List[Dict[str, Any]] = []
            async for keys in self._scan_entity_key_batches(
                owner, _ScanStats()
            ):  # owner filter applies while scanning (#18825)
                async for e in self._iter_entity_batches(keys):
                    if (
                        e
                        and e.get("type") == entity_type
                        and entity_visible(e, owner)
                        and _is_entity_valid_at(e, as_of)
                    ):
                        found.append(e)
            return found

        except Exception as e:
            logger.error("get_entities_as_of failed: %s", e)
            return []
