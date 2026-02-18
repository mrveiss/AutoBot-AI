# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Temporal Search Service - Search and traverse temporal events.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import logging
from datetime import datetime
from typing import List, Optional, Set
from uuid import UUID

logger = logging.getLogger(__name__)


class TemporalSearchService:
    """Search and analyze temporal events in the knowledge graph."""

    def __init__(self, redis_client) -> None:
        """
        Initialize temporal search service.

        Args:
            redis_client: Redis client instance
        """
        self.redis = redis_client

    async def search_events_in_range(
        self,
        start_date: datetime,
        end_date: datetime,
        event_types: Optional[List[str]] = None,
        participants: Optional[List[UUID]] = None,
        limit: int = 100,
    ) -> List[dict]:
        """
        Search events within a date range.

        Args:
            start_date: Range start datetime
            end_date: Range end datetime
            event_types: Filter by event types (action, decision, etc.)
            participants: Filter by participant entity IDs
            limit: Maximum results

        Returns:
            List of event dictionaries
        """
        try:
            start_score = start_date.timestamp()
            end_score = end_date.timestamp()

            event_ids = self.redis.zrangebyscore(
                "timeline:global", start_score, end_score, start=0, num=limit
            )

            events = []
            for event_id in event_ids:
                event = await self._get_event(event_id)
                if not event:
                    continue

                if event_types and event.get("event_type") not in event_types:
                    continue

                if participants:
                    event_participants = set(event.get("participants", []))
                    if not event_participants.intersection(
                        {str(p) for p in participants}
                    ):
                        continue

                events.append(event)

            logger.info(
                "Found %s events in range %s to %s",
                len(events),
                start_date,
                end_date,
            )
            return events

        except Exception as e:
            logger.error("Event range search failed: %s", e)
            return []

    async def get_event_timeline(self, entity_name: str, limit: int = 50) -> List[dict]:
        """
        Get chronological timeline of events for an entity.

        Args:
            entity_name: Entity name or canonical name
            limit: Maximum events to return

        Returns:
            List of events ordered by timestamp
        """
        try:
            # Lookup entity ID by name
            entity_id = self._get_entity_id_by_name(entity_name)
            if not entity_id:
                logger.warning("Entity not found: %s", entity_name)
                return []

            # Get event IDs for this entity
            event_key = f"entity:{entity_id}:events"
            event_ids = self.redis.smembers(event_key)

            # Fetch and sort events by timestamp
            events = []
            for event_id in event_ids:
                event = await self._get_event(event_id)
                if event and event.get("timestamp"):
                    events.append(event)

            events.sort(key=lambda e: datetime.fromisoformat(e["timestamp"]))

            logger.info(
                "Retrieved %s events for %s",
                len(events[:limit]),
                entity_name,
            )
            return events[:limit]

        except Exception as e:
            logger.error("Timeline retrieval failed: %s", e)
            return []

    async def find_causal_chain(
        self, event_id: UUID, direction: str = "forward", max_depth: int = 5
    ) -> List[dict]:
        """
        Find causal chain of events (causes or effects).

        Args:
            event_id: Starting event ID
            direction: "forward" (effects) or "backward" (causes)
            max_depth: Maximum chain depth to traverse

        Returns:
            List of causally connected events
        """
        try:
            chain = []
            visited: Set[str] = set()

            await self._traverse_causal_chain(
                str(event_id), direction, max_depth, 0, chain, visited
            )

            logger.info(
                "Found causal chain of %s events (%s from %s)",
                len(chain),
                direction,
                event_id,
            )
            return chain

        except Exception as e:
            logger.error("Causal chain traversal failed: %s", e)
            return []

    async def _traverse_causal_chain(
        self,
        event_id: str,
        direction: str,
        max_depth: int,
        current_depth: int,
        chain: List[dict],
        visited: Set[str],
    ) -> None:
        """Recursively traverse causal relationships."""
        if current_depth >= max_depth or event_id in visited:
            return

        visited.add(event_id)
        event = await self._get_event(event_id)
        if not event:
            return

        chain.append(event)

        # Get causal links
        if direction == "forward":
            link_key = f"event:{event_id}:effects"
        else:
            link_key = f"event:{event_id}:causes"

        linked_ids = self.redis.smembers(link_key)

        for linked_id in linked_ids:
            await self._traverse_causal_chain(
                linked_id, direction, max_depth, current_depth + 1, chain, visited
            )

    def _get_entity_id_by_name(self, entity_name: str) -> Optional[str]:
        """Lookup entity ID by canonical name."""
        canonical_name = entity_name.lower().strip()
        name_key = f"entity:name:{canonical_name}"
        entity_id = self.redis.get(name_key)
        return entity_id.decode() if entity_id else None

    async def _get_event(self, event_id: str) -> Optional[dict]:
        """Retrieve event data from Redis JSON."""
        try:
            key = f"event:{event_id}"
            event_data = self.redis.json().get(key)
            return event_data
        except Exception as e:
            logger.warning("Failed to get event %s: %s", event_id, e)
            return None
