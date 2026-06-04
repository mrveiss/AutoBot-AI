# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis Graph Loader - Load entities, relationships, and events to Redis.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
Issue #3230: Also writes into PropertyGraph for queryable typed-edge traversal.
"""

from typing import List

from autobot_memory_graph.property_graph import PropertyGraph
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from knowledge.pipeline.base import BaseLoader, PipelineContext
from knowledge.pipeline.models.entity import Entity
from knowledge.pipeline.models.event import TemporalEvent
from knowledge.pipeline.models.relationship import Relationship
from knowledge.pipeline.registry import TaskRegistry

logger = get_logger(__name__)


@TaskRegistry.register_loader("redis_graph")
class RedisGraphLoader(BaseLoader):
    """Load graph data (entities, relationships, events) to Redis.

    Writes to two stores in parallel:
    1. Legacy Redis JSON adjacency list (backward compat for existing callers).
    2. PropertyGraph (typed edges, multi-hop traversal, property filters).
    """

    def __init__(self, database: str = "knowledge") -> None:
        """
        Initialize Redis graph loader.

        Args:
            database: Redis database name
        """
        self.database = database
        self.redis_client = None
        self._property_graph: PropertyGraph = PropertyGraph(database=database)

    async def load(self, context: PipelineContext) -> None:
        """
        Load graph data to Redis.

        Args:
            context: Pipeline context with entities, relationships, events
        """
        self.redis_client = get_redis_client(async_client=True, database=self.database)
        # Wire PropertyGraph to the same Redis connection (no extra pool entry)
        self._property_graph._redis = self.redis_client

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
            "Loaded %s entities, %s relationships, %s events to Redis",
            len(entities),
            len(relationships),
            len(events),
        )

    async def _load_entities(self, entities: List[Entity]) -> None:
        """Load entities to Redis JSON and PropertyGraph."""
        try:
            for entity in entities:
                # Legacy adjacency-list store
                key = f"entity:{entity.id}"
                entity_data = entity.model_dump(mode="json")
                await self.redis_client.json().set(key, "$", entity_data)

                name_key = f"entity:name:{entity.canonical_name}"
                await self.redis_client.set(name_key, str(entity.id))

                # PropertyGraph node (#3230)
                node_props = {
                    "type": entity.entity_type if hasattr(entity, "entity_type") else "",
                    "name": entity.canonical_name,
                    "source": "ecl_pipeline",
                }
                await self._property_graph.add_node(str(entity.id), node_props)

            logger.info("Loaded %s entities to Redis", len(entities))
        except Exception as e:
            logger.error("Failed to load entities to Redis: %s", e)

    async def _load_relationships(self, relationships: List[Relationship]) -> None:
        """Load relationships to Redis legacy store and PropertyGraph."""
        try:
            for rel in relationships:
                # Legacy adjacency-list store
                key = f"relationship:{rel.id}"
                rel_data = rel.model_dump(mode="json")
                await self.redis_client.json().set(key, "$", rel_data)

                source_key = f"entity:{rel.source_entity_id}:relationships"
                await self.redis_client.sadd(source_key, str(rel.id))

                target_key = f"entity:{rel.target_entity_id}:relationships"
                await self.redis_client.sadd(target_key, str(rel.id))

                if rel.bidirectional:
                    await self._add_bidirectional_index(rel)

                # PropertyGraph edge (#3230)
                edge_props = {
                    "description": rel.description,
                    "confidence": str(rel.confidence),
                    "bidirectional": str(rel.bidirectional),
                }
                await self._property_graph.add_edge(
                    str(rel.source_entity_id),
                    str(rel.target_entity_id),
                    rel.relationship_type.upper(),
                    edge_props,
                )
                if rel.bidirectional:
                    await self._property_graph.add_edge(
                        str(rel.target_entity_id),
                        str(rel.source_entity_id),
                        rel.relationship_type.upper(),
                        edge_props,
                    )

            logger.info("Loaded %s relationships to Redis", len(relationships))
        except Exception as e:
            logger.error("Failed to load relationships to Redis: %s", e)

    async def _add_bidirectional_index(self, rel: Relationship) -> None:
        """Add reverse index for bidirectional relationship (legacy store)."""
        reverse_key = f"relationship:reverse:{rel.id}"
        reverse_data = {
            "source_entity_id": str(rel.target_entity_id),
            "target_entity_id": str(rel.source_entity_id),
            "relationship_type": rel.relationship_type,
            "original_id": str(rel.id),
        }
        await self.redis_client.json().set(reverse_key, "$", reverse_data)

    async def _load_events(self, events: List[TemporalEvent]) -> None:
        """Load temporal events to Redis with timeline indexing."""
        try:
            for event in events:
                key = f"event:{event.id}"
                event_data = event.model_dump(mode="json")
                await self.redis_client.json().set(key, "$", event_data)

                if event.timestamp:
                    score = event.timestamp.timestamp()
                    await self.redis_client.zadd("timeline:global", {str(event.id): score})

                for participant_id in event.participants:
                    participant_key = f"entity:{participant_id}:events"
                    await self.redis_client.sadd(participant_key, str(event.id))

            logger.info("Loaded %s events to Redis", len(events))
        except Exception as e:
            logger.error("Failed to load events to Redis: %s", e)
