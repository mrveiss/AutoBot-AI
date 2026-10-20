# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Memory Graph - Relation traversal (BFS) operations.

Split out of ``relations.py`` (#18825) so the owner-scoped traversal fits the file-size
ceiling. Every hop is read through an OwnerScope: an entity the caller may not read is
neither returned nor traversed through.
"""

import asyncio
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

from .core import (
    INCOMING_DIRECTIONS,
    OUTGOING_DIRECTIONS,
    AutoBotMemoryGraphCore,
    canonical_relation_type,
    relation_type_matches,
)
from .owner_scope import require_scope

logger = get_logger(__name__)


class RelationTraversalMixin:
    """Mixin providing owner-scoped relation traversal (``get_related_entities``)."""

    async def _process_outgoing(
        self: AutoBotMemoryGraphCore,
        current_id: str,
        relation_type: str | None,
        depth: int,
        max_depth: int,
        queue: List,
        owner: Any,
    ) -> List[Dict[str, Any]]:
        """Process outgoing relations for BFS traversal. Issue #620."""
        outgoing = await self._get_outgoing_relations(current_id)
        return await self._process_direction_relations(
            outgoing, relation_type, "outgoing", "to", depth, max_depth, queue, owner
        )

    async def _process_incoming(
        self: AutoBotMemoryGraphCore,
        current_id: str,
        relation_type: str | None,
        depth: int,
        max_depth: int,
        queue: List,
        owner: Any,
    ) -> List[Dict[str, Any]]:
        """Process incoming relations for BFS traversal. Issue #620."""
        incoming = await self._get_incoming_relations(current_id)
        return await self._process_direction_relations(
            incoming, relation_type, "incoming", "from", depth, max_depth, queue, owner
        )

    async def _fetch_and_process_relations(
        self: AutoBotMemoryGraphCore,
        current_id: str,
        direction: str,
        relation_type: str | None,
        depth: int,
        max_depth: int,
        queue: List,
        owner: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch and process relations for BFS traversal. Issue #620."""
        need_outgoing = direction in OUTGOING_DIRECTIONS
        need_incoming = direction in INCOMING_DIRECTIONS

        if need_outgoing and need_incoming:
            return await self._process_both_directions(current_id, relation_type, depth, max_depth, queue, owner)
        if need_outgoing:
            return await self._process_outgoing(current_id, relation_type, depth, max_depth, queue, owner)
        if need_incoming:
            return await self._process_incoming(current_id, relation_type, depth, max_depth, queue, owner)
        return []

    async def _process_both_directions(
        self: AutoBotMemoryGraphCore,
        current_id: str,
        relation_type: str | None,
        depth: int,
        max_depth: int,
        queue: List,
        owner: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch both edge lists in parallel, then process outgoing before incoming."""
        outgoing, incoming = await asyncio.gather(
            self._get_outgoing_relations(current_id),
            self._get_incoming_relations(current_id),
        )
        related = await self._process_direction_relations(
            outgoing, relation_type, "outgoing", "to", depth, max_depth, queue, owner
        )
        related.extend(
            await self._process_direction_relations(
                incoming, relation_type, "incoming", "from", depth, max_depth, queue, owner
            )
        )
        return related

    def _build_related_entry(
        self: AutoBotMemoryGraphCore,
        rel: Dict[str, Any],
        entity: Dict[str, Any],
        direction: str,
    ) -> Dict[str, Any]:
        """Build a related entity entry for BFS results. Issue #620."""
        return {"entity": entity, "relation": rel, "direction": direction}

    async def _process_direction_relations(
        self: AutoBotMemoryGraphCore,
        relations: List[Dict[str, Any]],
        relation_type: str | None,
        direction: str,
        id_field: str,
        depth: int,
        max_depth: int,
        queue: List,
        owner: Any,
    ) -> List[Dict[str, Any]]:
        """Process relations in a single direction. Issue #620."""
        # #13452: alias-aware so legacy-spelled stored edges still match.
        filtered = [rel for rel in relations if relation_type_matches(rel["type"], relation_type)]
        if not filtered:
            return []

        entity_ids = [rel[id_field] for rel in filtered]
        entities = await asyncio.gather(
            *[self.get_entity(entity_id=eid, owner=owner) for eid in entity_ids],  # None when not readable (#18825)
            return_exceptions=True,
        )

        related = []
        for rel, related_entity in zip(filtered, entities):
            if related_entity and not isinstance(related_entity, Exception):
                related.append(self._build_related_entry(rel, related_entity, direction))
                if depth + 1 <= max_depth:
                    queue.append((rel[id_field], depth + 1))

        return related

    async def get_related_entities(
        self: AutoBotMemoryGraphCore,
        entity_name: str,
        relation_type: str | None = None,
        direction: str = "both",
        max_depth: int = 1,
        *,
        owner: Any,
    ) -> List[Dict[str, Any]]:
        """Entities related to ``entity_name``, each with relation metadata.

        ``relation_type`` filters (None = all); ``direction`` is "outgoing", "incoming" or "both";
        ``max_depth`` is the traversal depth (1-3). ``owner`` is REQUIRED (#18825): the start entity
        is resolved within it, and neighbours it may not read are dropped and not traversed through.
        """
        self.ensure_initialized()
        require_scope(owner)
        relation_type = canonical_relation_type(relation_type) if relation_type else relation_type  # #13452

        try:
            entity = await self.get_entity(entity_name=entity_name, owner=owner)
            if not entity:
                return []
            return await self._traverse_related(entity["id"], direction, relation_type, max_depth, owner)
        except Exception as e:
            logger.error("Failed to get related entities: %s", e)
            return []

    async def _traverse_related(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
        direction: str,
        relation_type: str | None,
        max_depth: int,
        owner: Any,
    ) -> List[Dict[str, Any]]:
        """Breadth-first walk from ``entity_id`` collecting readable neighbours up to ``max_depth``."""
        related: List[Dict[str, Any]] = []
        visited: set = set()
        queue = [(entity_id, 0)]
        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)
            related.extend(
                await self._fetch_and_process_relations(
                    current_id, direction, relation_type, depth, max_depth, queue, owner
                )
            )
        return related
