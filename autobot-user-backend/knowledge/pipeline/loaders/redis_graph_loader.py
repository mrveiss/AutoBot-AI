# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Graph Loader - Load entities, relationships, and events to Redis.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import logging
from typing import List

from knowledge.pipeline.base import BaseLoader, PipelineContext
from knowledge.pipeline.models.entity import Entity
from knowledge.pipeline.models.event import TemporalEvent
from knowledge.pipeline.models.relationship import Relationship
from knowledge.pipeline.registry import TaskRegistry

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


@TaskRegistry.register_loader("redis_graph")
class RedisGraphLoader(BaseLoader):
    """Load graph data (entities, relationships, events) to Redis."""

    def __init__(self, database: str = "knowledge") -> None:
        """
        Initialize Redis graph loader.

        Args:
            database: Redis database name
        """
        self.database = database
        self.redis_client = None

    async def load(self, context: PipelineContext) -> None:
        """
        Load graph data to Redis.

        Args:
            context: Pipeline context with entities, relationships, events
        """
        self.redis_client = get_redis_client(async_client=False, database=self.database)

        entities: List[Entity] = context.entities
        relationships: List[Relationship] = context.relationships
        events: List[TemporalEvent] = context.events

        if entities:
            await self._load_entities(entities)

        if relationships:
            await self._load_relationships(relationships)

        if events:
            await self._load_events(events)

        logger.info(
            f"Loaded {len(entities)} entities, "
            f"{len(relationships)} relationships, "
            f"{len(events)} events to Redis"
        )

    async def _load_entities(self, entities: List[Entity]) -> None:
        """Load entities to Redis JSON."""
        try:
            for entity in entities:
                key = f"entity:{entity.id}"
                entity_data = entity.model_dump(mode="json")
                self.redis_client.json().set(key, "$", entity_data)

                # Index by name for lookup
                name_key = f"entity:name:{entity.canonical_name}"
                self.redis_client.set(name_key, str(entity.id))

            logger.info("Loaded %s entities to Redis", len(entities))
        except Exception as e:
            logger.error("Failed to load entities to Redis: %s", e)

    async def _load_relationships(self, relationships: List[Relationship]) -> None:
        """Load relationships to Redis."""
        try:
            for rel in relationships:
                key = f"relationship:{rel.id}"
                rel_data = rel.model_dump(mode="json")
                self.redis_client.json().set(key, "$", rel_data)

                # Index relationships by source and target
                source_key = f"entity:{rel.source_entity_id}:relationships"
                self.redis_client.sadd(source_key, str(rel.id))

                target_key = f"entity:{rel.target_entity_id}:relationships"
                self.redis_client.sadd(target_key, str(rel.id))

                # For bidirectional relationships, add reverse index
                if rel.bidirectional:
                    self._add_bidirectional_index(rel)

            logger.info("Loaded %s relationships to Redis", len(relationships))
        except Exception as e:
            logger.error("Failed to load relationships to Redis: %s", e)

    def _add_bidirectional_index(self, rel: Relationship) -> None:
        """Add reverse index for bidirectional relationship."""
        reverse_key = f"relationship:reverse:{rel.id}"
        reverse_data = {
            "source_entity_id": str(rel.target_entity_id),
            "target_entity_id": str(rel.source_entity_id),
            "relationship_type": rel.relationship_type,
            "original_id": str(rel.id),
        }
        self.redis_client.json().set(reverse_key, "$", reverse_data)

    async def _load_events(self, events: List[TemporalEvent]) -> None:
        """Load temporal events to Redis with timeline indexing."""
        try:
            for event in events:
                key = f"event:{event.id}"
                event_data = event.model_dump(mode="json")
                self.redis_client.json().set(key, "$", event_data)

                # Add to timeline sorted set (score = timestamp)
                if event.timestamp:
                    score = event.timestamp.timestamp()
                    self.redis_client.zadd("timeline:global", {str(event.id): score})

                # Index events by participants
                for participant_id in event.participants:
                    participant_key = f"entity:{participant_id}:events"
                    self.redis_client.sadd(participant_key, str(event.id))

            logger.info("Loaded %s events to Redis", len(events))
        except Exception as e:
            logger.error("Failed to load events to Redis: %s", e)
