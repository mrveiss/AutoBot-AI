# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Memory Graph - Entity Operations Module

This module contains entity management operations:
- create_entity, get_entity, add_observations, delete_entity
- Entity embedding generation

Part of the modular autobot_memory_graph package (Issue #716).
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .core import AutoBotMemoryGraphCore, ENTITY_TYPES

logger = logging.getLogger(__name__)


class EntityOperationsMixin:
    """
    Mixin class providing entity management operations.

    This mixin is designed to be used with AutoBotMemoryGraphCore
    and provides CRUD operations for entities.
    """

    def _prepare_entity_metadata(
        self: AutoBotMemoryGraphCore,
        metadata: Optional[Dict[str, Any]],
        tags: Optional[List[str]],
    ) -> Dict[str, Any]:
        """
        Prepare enriched metadata for a new entity.

        (Issue #398: extracted helper)

        Args:
            metadata: Optional base metadata dictionary
            tags: Optional list of tags

        Returns:
            Enriched metadata dictionary
        """
        entity_metadata = metadata or {}
        entity_metadata.update({
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "created_by": "autobot",
            "tags": tags or [],
            "priority": entity_metadata.get("priority", "medium"),
            "status": entity_metadata.get("status", "active"),
            "version": 1,
        })
        return entity_metadata

    def _build_entity_document(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
        entity_type: str,
        name: str,
        observations: List[str],
        entity_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build the complete entity document for storage.

        (Issue #398: extracted helper)

        Args:
            entity_id: UUID for the entity
            entity_type: Type of entity
            name: Human-readable name
            observations: List of observation strings
            entity_metadata: Enriched metadata

        Returns:
            Complete entity document dictionary
        """
        return {
            "id": entity_id,
            "type": entity_type,
            "name": name,
            "created_at": int(datetime.now().timestamp() * 1000),
            "updated_at": int(datetime.now().timestamp() * 1000),
            "observations": observations,
            "metadata": entity_metadata,
        }

    async def create_entity(
        self: AutoBotMemoryGraphCore,
        entity_type: str,
        name: str,
        observations: List[str],
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new entity in the memory graph.

        (Issue #398: refactored to use extracted helpers)

        Args:
            entity_type: Type of entity (conversation, bug_fix, feature, etc.)
            name: Human-readable entity name
            observations: List of observation strings
            metadata: Optional additional metadata
            tags: Optional classification tags

        Returns:
            Created entity with entity_id and metadata

        Raises:
            ValueError: Invalid entity_type or empty name
            RuntimeError: Memory Graph not initialized
        """
        self.ensure_initialized()

        if entity_type not in ENTITY_TYPES:
            raise ValueError(
                f"Invalid entity_type: {entity_type}. Must be one of {ENTITY_TYPES}"
            )

        if not name or not name.strip():
            raise ValueError("Entity name cannot be empty")

        try:
            entity_id = str(uuid.uuid4())
            entity_metadata = self._prepare_entity_metadata(metadata, tags)
            entity = self._build_entity_document(
                entity_id, entity_type, name, observations, entity_metadata
            )

            # Store in Redis
            entity_key = f"memory:entity:{entity_id}"
            await self.redis_client.json().set(entity_key, "$", entity)

            # Generate and cache embedding for semantic search
            if self.knowledge_base:
                await self._generate_entity_embedding(entity_id, entity)

            logger.info(
                "Created entity: %s (%s) with ID %s", name, entity_type, entity_id
            )

            return entity

        except Exception as e:
            logger.error("Failed to create entity: %s", e)
            raise RuntimeError(f"Entity creation failed: {str(e)}")

    async def get_entity(
        self: AutoBotMemoryGraphCore,
        entity_id: Optional[str] = None,
        entity_name: Optional[str] = None,
        include_relations: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve entity by ID or name.

        Args:
            entity_id: UUID of entity to retrieve
            entity_name: Name of entity to retrieve (alternative to ID)
            include_relations: Include related entities in response

        Returns:
            Entity data or None if not found
        """
        self.ensure_initialized()

        try:
            # Find entity by ID or name
            if entity_id:
                entity_key = f"memory:entity:{entity_id}"
                entity = await self.redis_client.json().get(entity_key)
            elif entity_name:
                # Search by name
                results = await self.search_entities(query=entity_name, limit=1)
                if not results:
                    return None
                entity = results[0]
                entity_id = entity["id"]
            else:
                raise ValueError("Either entity_id or entity_name must be provided")

            if not entity:
                return None

            # Include relations if requested - fetch in parallel
            if include_relations and entity_id:
                outgoing, incoming = await asyncio.gather(
                    self._get_outgoing_relations(entity_id),
                    self._get_incoming_relations(entity_id),
                )
                entity["relations"] = {"outgoing": outgoing, "incoming": incoming}

            return entity

        except Exception as e:
            logger.error("Failed to get entity: %s", e)
            return None

    async def add_observations(
        self: AutoBotMemoryGraphCore,
        entity_name: str,
        observations: List[str],
    ) -> Dict[str, Any]:
        """
        Add new observations to an existing entity.

        Args:
            entity_name: Name of entity to update
            observations: List of new observations to add

        Returns:
            Updated entity data

        Raises:
            ValueError: Entity not found
        """
        self.ensure_initialized()

        try:
            entity = await self.get_entity(entity_name=entity_name)
            if not entity:
                raise ValueError(f"Entity not found: {entity_name}")

            entity_id = entity["id"]
            entity_key = f"memory:entity:{entity_id}"

            # Append all observations in parallel
            await asyncio.gather(*[
                self.redis_client.json().arrappend(entity_key, "$.observations", obs)
                for obs in observations
            ])

            # Update timestamp
            await self.redis_client.json().set(
                entity_key, "$.updated_at", int(datetime.now().timestamp() * 1000)
            )

            # Update embedding
            if self.knowledge_base:
                updated_entity = await self.redis_client.json().get(entity_key)
                await self._generate_entity_embedding(entity_id, updated_entity)

            # Invalidate cache
            self.search_cache.clear()

            logger.info(
                "Added %d observations to entity: %s", len(observations), entity_name
            )

            return await self.redis_client.json().get(entity_key)

        except Exception as e:
            logger.error("Failed to add observations: %s", e)
            raise RuntimeError(f"Add observations failed: {str(e)}")

    async def delete_entity(
        self: AutoBotMemoryGraphCore,
        entity_name: str,
        cascade_relations: bool = True,
    ) -> bool:
        """
        Delete entity and optionally its relations.

        Args:
            entity_name: Name of entity to delete
            cascade_relations: Delete all relations to/from this entity

        Returns:
            True if deleted, False if not found
        """
        self.ensure_initialized()

        try:
            entity = await self.get_entity(entity_name=entity_name)
            if not entity:
                return False

            entity_id = entity["id"]

            # Delete relations if cascade
            if cascade_relations:
                out_key = f"memory:relations:out:{entity_id}"
                await self.redis_client.delete(out_key)

                in_key = f"memory:relations:in:{entity_id}"
                await self.redis_client.delete(in_key)

            # Delete entity
            entity_key = f"memory:entity:{entity_id}"
            deleted = await self.redis_client.delete(entity_key)

            # Clear cache
            self.search_cache.clear()
            if entity_id in self.embedding_cache:
                del self.embedding_cache[entity_id]

            logger.info("Deleted entity: %s", entity_name)

            return deleted > 0

        except Exception as e:
            logger.error("Failed to delete entity: %s", e)
            return False

    async def _generate_entity_embedding(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
        entity: Dict[str, Any],
    ) -> None:
        """Generate and cache embedding for entity."""
        try:
            if not self.knowledge_base:
                return

            name = entity.get("name", "")
            entity_type = entity.get("type", "")
            observations = entity.get("observations", [])

            # Weighted text (name: 0.3, type: 0.1, observations: 0.6)
            embedding_text = (
                f"{name} {name} {name} {entity_type} {' '.join(observations * 6)}"
            )

            self.embedding_cache[entity_id] = embedding_text

        except Exception as e:
            logger.warning(
                "Failed to generate embedding for entity %s: %s", entity_id, e
            )

    async def create_conversation_entity(
        self: AutoBotMemoryGraphCore,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        observations: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Automatically create entity from chat session.

        Args:
            session_id: Chat session identifier
            metadata: Optional additional metadata
            observations: Optional list of observations to add immediately

        Returns:
            Created conversation entity
        """
        self.ensure_initialized()

        try:
            entity_observations = []
            tags = []

            if observations:
                entity_observations = observations
            elif self.chat_history_manager:
                entity_observations = [f"Conversation session: {session_id}"]
                tags = ["conversation"]

            conv_metadata = metadata or {}
            conv_metadata.update({
                "session_id": session_id,
                "priority": "low",
                "status": "active",
            })

            entity = await self.create_entity(
                entity_type="conversation",
                name=f"Conversation {session_id[:8]}",
                observations=entity_observations,
                metadata=conv_metadata,
                tags=tags,
            )

            logger.info("Created conversation entity for session %s", session_id)

            return entity

        except Exception as e:
            logger.error("Failed to create conversation entity: %s", e)
            raise
