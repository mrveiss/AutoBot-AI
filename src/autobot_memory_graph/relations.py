# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .core import (
    INCOMING_DIRECTIONS,
    OUTGOING_DIRECTIONS,
    RELATION_TYPES,
    AutoBotMemoryGraphCore,
)

logger = logging.getLogger(__name__)


class RelationOperationsMixin:
    """
    Mixin class providing relationship management operations.

    This mixin is designed to be used with AutoBotMemoryGraphCore
    and provides CRUD operations for relations between entities.
    """

    async def create_relation(
        self: AutoBotMemoryGraphCore,
        from_entity: str,
        to_entity: str,
        relation_type: str,
        bidirectional: bool = False,
        strength: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create relationship between two entities.

        Issue #665: Refactored to use _store_outgoing_relation and
        _store_incoming_relation helpers for maintainability.

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

        if relation_type not in RELATION_TYPES:
            raise ValueError(f"Invalid relation_type: {relation_type}")

        try:
            # Get entity IDs in parallel
            from_entity_data, to_entity_data = await asyncio.gather(
                self.get_entity(entity_name=from_entity),
                self.get_entity(entity_name=to_entity),
            )

            if not from_entity_data or not to_entity_data:
                raise ValueError("Source or target entity not found")

            from_id = from_entity_data["id"]
            to_id = to_entity_data["id"]
            timestamp = int(datetime.now().timestamp() * 1000)

            relation = {
                "to": to_id,
                "type": relation_type,
                "created_at": timestamp,
                "metadata": {"strength": strength, **(metadata or {})},
            }
            reverse_rel = {
                "from": from_id,
                "type": relation_type,
                "created_at": timestamp,
            }

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
            raise RuntimeError(f"Relation creation failed: {str(e)}")

    async def create_relation_by_id(
        self: AutoBotMemoryGraphCore,
        from_entity_id: str,
        to_entity_id: str,
        relation_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Create relationship between two entities using their IDs directly.

        Issue #608: Helper for user-centric session tracking where we have
        entity IDs rather than names.

        Args:
            from_entity_id: Source entity ID (UUID)
            to_entity_id: Target entity ID (UUID)
            relation_type: Type of relationship
            metadata: Optional additional metadata

        Returns:
            True if relation created successfully
        """
        self.ensure_initialized()

        if relation_type not in RELATION_TYPES:
            raise ValueError(f"Invalid relation_type: {relation_type}")

        try:
            timestamp = int(datetime.now().timestamp() * 1000)

            relation = {
                "to": to_entity_id,
                "type": relation_type,
                "created_at": timestamp,
                "metadata": metadata or {},
            }
            reverse_rel = {
                "from": from_entity_id,
                "type": relation_type,
                "created_at": timestamp,
            }

            await self._store_outgoing_relation(from_entity_id, relation)
            await self._store_incoming_relation(to_entity_id, reverse_rel)

            logger.debug(
                "Created relation by ID: %s --[%s]--> %s",
                from_entity_id[:8],
                relation_type,
                to_entity_id[:8],
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
            await self.redis_client.json().set(
                out_key, "$", {"entity_id": from_id, "relations": []}
            )
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
            await self.redis_client.json().set(
                in_key, "$", {"entity_id": to_id, "relations": []}
            )
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
            logger.debug("Error getting incoming relations for %s: %s", entity_id, e)
            return []

    async def get_relations(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
        relation_types: Optional[List[str]] = None,
        direction: str = "both",
    ) -> Dict[str, Any]:
        """
        Get relations for an entity.

        Issue #608: Public method for retrieving entity relationships.

        Args:
            entity_id: Entity ID to get relations for
            relation_types: Optional filter by relation types
            direction: "outgoing", "incoming", or "both"

        Returns:
            Dict with "relations" key containing list of relations
        """
        self.ensure_initialized()

        try:
            relations = []

            if direction in OUTGOING_DIRECTIONS:
                outgoing = await self._get_outgoing_relations(entity_id)
                for rel in outgoing:
                    if relation_types is None or rel.get("type") in relation_types:
                        relations.append(
                            {
                                "from": entity_id,
                                "to": rel.get("to"),
                                "type": rel.get("type"),
                                "direction": "outgoing",
                                "metadata": rel.get("metadata", {}),
                            }
                        )

            if direction in INCOMING_DIRECTIONS:
                incoming = await self._get_incoming_relations(entity_id)
                for rel in incoming:
                    if relation_types is None or rel.get("type") in relation_types:
                        relations.append(
                            {
                                "from": rel.get("from"),
                                "to": entity_id,
                                "type": rel.get("type"),
                                "direction": "incoming",
                                "metadata": rel.get("metadata", {}),
                            }
                        )

            return {"relations": relations}

        except Exception as e:
            logger.error("Failed to get relations for %s: %s", entity_id, e)
            return {"relations": []}

    async def _fetch_and_process_relations(
        self: AutoBotMemoryGraphCore,
        current_id: str,
        direction: str,
        relation_type: Optional[str],
        depth: int,
        max_depth: int,
        queue: List,
    ) -> List[Dict[str, Any]]:
        """Issue #665: Extracted from get_related_entities to reduce function length.

        Fetch relations for a direction and process them.

        Args:
            current_id: Current entity ID in BFS traversal
            direction: "outgoing", "incoming", or "both"
            relation_type: Filter by relation type
            depth: Current traversal depth
            max_depth: Maximum traversal depth
            queue: BFS queue to append to

        Returns:
            List of related entity dicts with relation metadata
        """
        need_outgoing = direction in OUTGOING_DIRECTIONS
        need_incoming = direction in INCOMING_DIRECTIONS
        related = []

        if need_outgoing and need_incoming:
            outgoing, incoming = await asyncio.gather(
                self._get_outgoing_relations(current_id),
                self._get_incoming_relations(current_id),
            )
            related.extend(
                await self._process_direction_relations(
                    outgoing, relation_type, "outgoing", "to", depth, max_depth, queue
                )
            )
            related.extend(
                await self._process_direction_relations(
                    incoming, relation_type, "incoming", "from", depth, max_depth, queue
                )
            )
        elif need_outgoing:
            outgoing = await self._get_outgoing_relations(current_id)
            related.extend(
                await self._process_direction_relations(
                    outgoing, relation_type, "outgoing", "to", depth, max_depth, queue
                )
            )
        elif need_incoming:
            incoming = await self._get_incoming_relations(current_id)
            related.extend(
                await self._process_direction_relations(
                    incoming, relation_type, "incoming", "from", depth, max_depth, queue
                )
            )

        return related

    async def _process_direction_relations(
        self: AutoBotMemoryGraphCore,
        relations: List[Dict[str, Any]],
        relation_type: Optional[str],
        direction: str,
        id_field: str,
        depth: int,
        max_depth: int,
        queue: List,
    ) -> List[Dict[str, Any]]:
        """Process relations in a single direction (Issue #298 - extracted helper).

        Args:
            relations: Raw relations from Redis
            relation_type: Optional filter for relation type
            direction: "outgoing" or "incoming"
            id_field: Field name for entity ID ("to" or "from")
            depth: Current traversal depth
            max_depth: Maximum traversal depth
            queue: BFS queue to append to

        Returns:
            List of related entity dicts with relation metadata
        """
        filtered = [
            rel
            for rel in relations
            if relation_type is None or rel["type"] == relation_type
        ]
        if not filtered:
            return []

        entity_ids = [rel[id_field] for rel in filtered]
        entities = await asyncio.gather(
            *[self.get_entity(entity_id=eid) for eid in entity_ids],
            return_exceptions=True,
        )

        related = []
        for rel, related_entity in zip(filtered, entities):
            if related_entity and not isinstance(related_entity, Exception):
                related.append(
                    {
                        "entity": related_entity,
                        "relation": rel,
                        "direction": direction,
                    }
                )
                if depth + 1 <= max_depth:
                    queue.append((rel[id_field], depth + 1))

        return related

    async def get_related_entities(
        self: AutoBotMemoryGraphCore,
        entity_name: str,
        relation_type: Optional[str] = None,
        direction: str = "both",
        max_depth: int = 1,
    ) -> List[Dict[str, Any]]:
        """Get entities related to specified entity.

        Args:
            entity_name: Name of entity
            relation_type: Filter by relation type (None = all types)
            direction: "outgoing", "incoming", or "both"
            max_depth: Relationship traversal depth (1-3)

        Returns:
            List of related entities with relation metadata
        """
        self.ensure_initialized()

        try:
            entity = await self.get_entity(entity_name=entity_name)
            if not entity:
                return []

            entity_id = entity["id"]
            related = []
            visited = set()
            queue = [(entity_id, 0)]

            while queue:
                current_id, depth = queue.pop(0)
                if current_id in visited or depth > max_depth:
                    continue
                visited.add(current_id)

                direction_related = await self._fetch_and_process_relations(
                    current_id, direction, relation_type, depth, max_depth, queue
                )
                related.extend(direction_related)

            return related

        except Exception as e:
            logger.error("Failed to get related entities: %s", e)
            return []

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
                if not (rel["to"] == to_id and rel["type"] == relation_type)
            ]
            await self.redis_client.json().set(
                out_key, "$.relations", filtered_relations
            )

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
                if not (rel["from"] == from_id and rel["type"] == relation_type)
            ]
            await self.redis_client.json().set(
                in_key, "$.relations", filtered_relations
            )

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

        try:
            from_entity_data, to_entity_data = await asyncio.gather(
                self.get_entity(entity_name=from_entity),
                self.get_entity(entity_name=to_entity),
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
