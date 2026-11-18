# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Memory Graph - Relation Operations Module

This module contains relationship management operations:
- create_relation, get_related_entities, delete_relation
- Bidirectional relationship tracking
- Relation traversal with BFS

Part of the modular autobot_memory_graph package (Issue #716).
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

from .core import (
    INCOMING_DIRECTIONS,
    OUTGOING_DIRECTIONS,
    RELATION_TYPES,
    AutoBotMemoryGraphCore,
    canonical_relation_filter,
    canonical_relation_type,
    relation_type_matches,
)
from .owner_scope import UNSCOPED_ALL_USERS, require_scope

logger = get_logger(__name__)


def _visible_of_type(
    rels: List[Dict[str, Any]], end: str, readable: set[str] | None, wanted: set[str] | None
) -> List[Dict[str, Any]]:
    """Edges whose ``end`` id is readable (``None`` = unfiltered) and whose type is wanted (#18825, #13452)."""
    return [
        rel
        for rel in rels
        if (readable is None or rel.get(end) in readable)
        and (wanted is None or canonical_relation_type(rel.get("type", "")) in wanted)
    ]


class RelationOperationsMixin:
    """
    Mixin class providing relationship management operations.

    This mixin is designed to be used with AutoBotMemoryGraphCore
    and provides CRUD operations for relations between entities.
    """

    def _build_relation_objects(
        self: AutoBotMemoryGraphCore,
        from_id: str,
        to_id: str,
        relation_type: str,
        strength: float,
        metadata: Dict[str, Any] | None,
    ) -> tuple:
        """
        Build outgoing and reverse relation dictionaries.

        Issue #620.

        Args:
            from_id: Source entity ID
            to_id: Target entity ID
            relation_type: Type of relationship
            strength: Relationship strength
            metadata: Optional additional metadata

        Returns:
            Tuple of (outgoing_relation, reverse_relation)
        """
        timestamp = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

        valid_from = datetime.now(tz=timezone.utc).isoformat()
        relation = {
            "to": to_id,
            "type": relation_type,
            "created_at": timestamp,
            "valid_from": valid_from,
            "valid_to": None,
            "metadata": {"strength": strength, **(metadata or {})},
        }
        reverse_rel = {
            "from": from_id,
            "type": relation_type,
            "created_at": timestamp,
            "valid_from": valid_from,
            "valid_to": None,
        }

        return relation, reverse_rel

    async def _resolve_entity_ids(
        self: AutoBotMemoryGraphCore,
        from_entity: str,
        to_entity: str,
    ) -> tuple:
        """Resolve entity names to IDs, raising if not found. Issue #620."""
        from_entity_data, to_entity_data = await asyncio.gather(
            # Relation writes resolve names globally; #18825 scopes reads and stamps ownership, and
            # mutation-by-name scoping is a separate follow-up, so the sentinel is explicit here.
            self.get_entity(entity_name=from_entity, owner=UNSCOPED_ALL_USERS),
            self.get_entity(entity_name=to_entity, owner=UNSCOPED_ALL_USERS),
        )
        if not from_entity_data or not to_entity_data:
            raise ValueError("Source or target entity not found")
        return from_entity_data["id"], to_entity_data["id"]

    async def create_relation(
        self: AutoBotMemoryGraphCore,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        bidirectional: bool = False,
        strength: float = 1.0,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Create relationship between two entities.

        Args:
            from_entity: Source entity name
            to_entity: Target entity name
            relation_type: Type of relationship
            bidirectional: Create reverse relation as well
            strength: Relationship strength (0.0-1.0)
            metadata: Optional additional metadata

        Returns:
            Created relation data
        """
        self.ensure_initialized()
        # #13452: fold legacy spellings (e.g. "relates_to") onto the canonical
        # name before validating, so a caller using the knowledge-base spelling
        # writes a real edge instead of raising into a swallowing except block.
        relation_type = canonical_relation_type(relation_type)
        if relation_type not in RELATION_TYPES:
            raise ValueError(f"Invalid relation_type: {relation_type}")

        try:
            from_id, to_id = await self._resolve_entity_ids(from_entity, to_entity)
            relation, reverse_rel = self._build_relation_objects(from_id, to_id, relation_type, strength, metadata)
            await self._store_outgoing_relation(from_id, relation)
            await self._store_incoming_relation(to_id, reverse_rel)

            logger.info(
                "Created relation: %s --[%s]--> %s",
                from_entity,
                relation_type,
                to_entity,
            )
            return relation

        except Exception as e:
            logger.error("Failed to create relation: %s", e)
            raise RuntimeError("Relation creation failed") from e

    def _build_relation_by_id_objects(
        self: AutoBotMemoryGraphCore,
        from_entity_id: str,
        to_entity_id: str,
        relation_type: str,
        metadata: Dict[str, Any] | None,
    ) -> tuple:
        """Build relation objects for create_relation_by_id. Issue #620."""
        timestamp = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        valid_from = datetime.now(tz=timezone.utc).isoformat()
        relation = {
            "to": to_entity_id,
            "type": relation_type,
            "created_at": timestamp,
            "valid_from": valid_from,
            "valid_to": None,
            "metadata": metadata or {},
        }
        reverse_rel = {
            "from": from_entity_id,
            "type": relation_type,
            "created_at": timestamp,
            "valid_from": valid_from,
            "valid_to": None,
        }
        return relation, reverse_rel

    async def create_relation_by_id(
        self: AutoBotMemoryGraphCore,
        from_entity_id: str,
        to_entity_id: str,
        relation_type: str,
        metadata: Dict[str, Any] | None = None,
    ) -> bool:
        """Create relationship between entities using IDs. Issue #620."""
        self.ensure_initialized()

        relation_type = canonical_relation_type(relation_type)  # #13452
        if relation_type not in RELATION_TYPES:
            raise ValueError(f"Invalid relation_type: {relation_type}")

        try:
            relation, reverse_rel = self._build_relation_by_id_objects(
                from_entity_id, to_entity_id, relation_type, metadata
            )
            await self._store_outgoing_relation(from_entity_id, relation)
            await self._store_incoming_relation(to_entity_id, reverse_rel)
            logger.debug(
                "Created relation by ID: [%s] --[%s]--> [%s]",
                from_entity_id[:8] if from_entity_id else "?",
                relation_type,
                to_entity_id[:8] if to_entity_id else "?",
            )
            return True
        except Exception as e:
            logger.error("Failed to create relation by ID: %s", e)
            return False

    async def _store_outgoing_relation(
        self: AutoBotMemoryGraphCore,
        from_id: str,
        relation: Dict[str, Any],
    ) -> None:
        """Store outgoing relation for an entity (Issue #665: extracted helper).

        Args:
            from_id: Source entity ID
            relation: Relation data to store
        """
        out_key = f"memory:relations:out:{from_id}"
        if not await self.redis_client.exists(out_key):
            await self.redis_client.json().set(out_key, "$", {"entity_id": from_id, "relations": []})
        await self.redis_client.json().arrappend(out_key, "$.relations", relation)

    async def _store_incoming_relation(
        self: AutoBotMemoryGraphCore,
        to_id: str,
        reverse_rel: Dict[str, Any],
    ) -> None:
        """Store incoming relation for an entity (Issue #665: extracted helper).

        Args:
            to_id: Target entity ID
            reverse_rel: Reverse relation data to store
        """
        in_key = f"memory:relations:in:{to_id}"
        if not await self.redis_client.exists(in_key):
            await self.redis_client.json().set(in_key, "$", {"entity_id": to_id, "relations": []})
        await self.redis_client.json().arrappend(in_key, "$.relations", reverse_rel)

    async def _get_outgoing_relations(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all outgoing relations for an entity."""
        try:
            out_key = f"memory:relations:out:{entity_id}"
            data = await self.redis_client.json().get(out_key)
            return data.get("relations", []) if data else []
        except Exception as e:
            # CodeQL: false positive — entity_id is a UUID, not sensitive data
            logger.debug("Error getting outgoing relations for %s: %s", entity_id, e)
            return []

    async def _get_incoming_relations(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all incoming relations for an entity."""
        try:
            in_key = f"memory:relations:in:{entity_id}"
            data = await self.redis_client.json().get(in_key)
            return data.get("relations", []) if data else []
        except Exception as e:
            # CodeQL: false positive — entity_id is a UUID, not sensitive data
            logger.debug("Error getting incoming relations for %s: %s", entity_id, e)
            return []

    def _format_outgoing_relation(self: AutoBotMemoryGraphCore, entity_id: str, rel: Dict[str, Any]) -> Dict[str, Any]:
        """Format an outgoing relation for response. Issue #620."""
        return {
            "from": entity_id,
            "to": rel.get("to"),
            "type": rel.get("type"),
            "direction": "outgoing",
            "metadata": rel.get("metadata", {}),
        }

    def _format_incoming_relation(self: AutoBotMemoryGraphCore, entity_id: str, rel: Dict[str, Any]) -> Dict[str, Any]:
        """Format an incoming relation for response. Issue #620."""
        return {
            "from": rel.get("from"),
            "to": entity_id,
            "type": rel.get("type"),
            "direction": "incoming",
            "metadata": rel.get("metadata", {}),
        }

    async def _visible_relations(
        self: AutoBotMemoryGraphCore, entity_id: str, side: str, wanted: set[str] | None, owner: Any
    ) -> List[Dict[str, Any]]:
        """Formatted ``side`` ("outgoing"/"incoming") relations of the right type whose other end ``owner`` may read."""
        outgoing = side == "outgoing"
        end = "to" if outgoing else "from"
        raw = await (self._get_outgoing_relations(entity_id) if outgoing else self._get_incoming_relations(entity_id))
        readable = await self._readable_relation_ends(entity_id, raw, end, owner)
        fmt = self._format_outgoing_relation if outgoing else self._format_incoming_relation
        return [fmt(entity_id, rel) for rel in _visible_of_type(raw, end, readable, wanted)]

    async def get_relations(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
        relation_types: List[str] | None = None,
        direction: str = "both",
        *,
        owner: Any,
    ) -> Dict[str, Any]:
        """Get the relations of an entity that ``owner`` may see. Issue #620.

        ``owner`` (#18825) is REQUIRED: an OwnerScope or UNSCOPED_ALL_USERS. A relation is returned only if
        ``owner`` can read BOTH endpoints, so neither another user's entity id nor the relation type
        to it leaves the owner's scope.
        """
        self.ensure_initialized()
        require_scope(owner)  # before the try: a missing scope must raise, not read as "no relations"

        # #13452: reads must canonicalise both sides, exactly as writes do, or a
        # relation created as "relates_to" (stored "related_to") is unreachable.
        wanted = canonical_relation_filter(relation_types)

        try:
            relations = []
            if direction in OUTGOING_DIRECTIONS:
                relations += await self._visible_relations(entity_id, "outgoing", wanted, owner)
            if direction in INCOMING_DIRECTIONS:
                relations += await self._visible_relations(entity_id, "incoming", wanted, owner)

            return {"relations": relations}
        except Exception as e:
            logger.error("Failed to get relations for %s: %s", entity_id, e)
            return {"relations": []}

    async def _filter_outgoing_relations(
        self: AutoBotMemoryGraphCore,
        from_id: str,
        to_id: str,
        relation_type: str,
    ) -> None:
        """
        Filter out a specific relation from outgoing relations.

        Issue #620.

        Args:
            from_id: Source entity ID
            to_id: Target entity ID
            relation_type: Type of relation to remove
        """
        out_key = f"memory:relations:out:{from_id}"
        out_data = await self.redis_client.json().get(out_key)

        if out_data and "relations" in out_data:
            filtered_relations = [
                rel
                for rel in out_data["relations"]
                if not (rel["to"] == to_id and relation_type_matches(rel["type"], relation_type))
            ]
            await self.redis_client.json().set(out_key, "$.relations", filtered_relations)

    async def _filter_incoming_relations(
        self: AutoBotMemoryGraphCore,
        from_id: str,
        to_id: str,
        relation_type: str,
    ) -> None:
        """
        Filter out a specific relation from incoming relations.

        Issue #620.

        Args:
            from_id: Source entity ID
            to_id: Target entity ID
            relation_type: Type of relation to remove
        """
        in_key = f"memory:relations:in:{to_id}"
        in_data = await self.redis_client.json().get(in_key)

        if in_data and "relations" in in_data:
            filtered_relations = [
                rel
                for rel in in_data["relations"]
                if not (rel["from"] == from_id and relation_type_matches(rel["type"], relation_type))
            ]
            await self.redis_client.json().set(in_key, "$.relations", filtered_relations)

    async def _set_valid_to_on_relations(
        self: AutoBotMemoryGraphCore,
        key: str,
        id_field: str,
        match_id: str,
        relation_type: str,
        valid_to: str,
    ) -> bool:
        """Set valid_to on matching relations in a Redis JSON list. Issue #3790."""
        data = await self.redis_client.json().get(key)
        if not data or "relations" not in data:
            return False

        updated = False
        for rel in data["relations"]:
            if rel.get(id_field) == match_id and relation_type_matches(rel.get("type", ""), relation_type):
                rel["valid_to"] = valid_to
                updated = True

        if updated:
            await self.redis_client.json().set(key, "$.relations", data["relations"])
        return updated

    async def invalidate_relation(
        self: AutoBotMemoryGraphCore,
        from_id: str,
        relation_type: str,
        to_id: str,
        ended_at: str | None = None,
    ) -> bool:
        """Mark a specific relation as no longer valid by setting valid_to.

        Does NOT delete — history is preserved.
        Returns True if at least one matching relation was updated.

        Args:
            from_id: Source entity ID
            relation_type: Type of the relation
            to_id: Target entity ID
            ended_at: ISO-8601 timestamp for valid_to (default: now)
        """
        self.ensure_initialized()
        relation_type = canonical_relation_type(relation_type)  # #13452

        try:
            valid_to = ended_at or datetime.now(tz=timezone.utc).isoformat()
            out_key = f"memory:relations:out:{from_id}"
            in_key = f"memory:relations:in:{to_id}"

            out_updated, in_updated = await asyncio.gather(
                self._set_valid_to_on_relations(out_key, "to", to_id, relation_type, valid_to),
                self._set_valid_to_on_relations(in_key, "from", from_id, relation_type, valid_to),
            )
            updated = out_updated or in_updated
            if updated:
                logger.info(
                    "Invalidated relation %s -[%s]-> %s at %s",
                    from_id[:8],
                    relation_type,
                    to_id[:8],
                    valid_to,
                )
            return updated

        except Exception as e:
            logger.error("Failed to invalidate relation: %s", e)
            return False

    async def delete_relation(
        self: AutoBotMemoryGraphCore,
        from_entity: str,
        to_entity: str,
        relation_type: str,
    ) -> bool:
        """
        Delete specific relation between entities.

        Issue #620: Refactored using Extract Method pattern.

        Args:
            from_entity: Source entity name
            to_entity: Target entity name
            relation_type: Type of relation to delete

        Returns:
            True if deleted, False if not found
        """
        self.ensure_initialized()
        relation_type = canonical_relation_type(relation_type)  # #13452

        try:
            from_entity_data, to_entity_data = await asyncio.gather(
                self.get_entity(entity_name=from_entity, owner=UNSCOPED_ALL_USERS),  # see _resolve_entity_ids
                self.get_entity(entity_name=to_entity, owner=UNSCOPED_ALL_USERS),
            )

            if not from_entity_data or not to_entity_data:
                return False

            from_id = from_entity_data["id"]
            to_id = to_entity_data["id"]

            await self._filter_outgoing_relations(from_id, to_id, relation_type)
            await self._filter_incoming_relations(from_id, to_id, relation_type)

            logger.info(
                "Deleted relation: %s --[%s]--> %s",
                from_entity,
                relation_type,
                to_entity,
            )

            return True

        except Exception as e:
            logger.error("Failed to delete relation: %s", e)
            return False
