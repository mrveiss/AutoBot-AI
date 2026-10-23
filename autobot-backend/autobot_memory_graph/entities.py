# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Memory Graph - Entity Operations Module

This module contains entity management operations:
- create_entity, get_entity, add_observations, delete_entity
- Entity embedding generation

Part of the modular autobot_memory_graph package (Issue #716).
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

from . import entity_upsert
from .core import ENTITY_TYPES, AutoBotMemoryGraphCore
from .owner_scope import (
    UNSCOPED_ALL_USERS,
    OwnerScope,
    entity_visible,
    owner_fields,
    require_scope,
    require_writer,
)

logger = get_logger(__name__)


class EntityOperationsMixin:
    """
    Mixin class providing entity management operations.

    This mixin is designed to be used with AutoBotMemoryGraphCore
    and provides CRUD operations for entities.
    """

    def _prepare_entity_metadata(
        self: AutoBotMemoryGraphCore,
        metadata: Dict[str, Any] | None,
        tags: List[str] | None,
        owner: OwnerScope,
    ) -> Dict[str, Any]:
        """
        Prepare enriched metadata for a new entity.

        (Issue #398: extracted helper)

        Args:
            metadata: Optional base metadata dictionary
            tags: Optional list of tags
            owner: Who the entity belongs to (#18825); recorded as ``created_by``

        Returns:
            Enriched metadata dictionary
        """
        entity_metadata = metadata or {}
        entity_metadata.update(
            {
                "created_at": datetime.now(tz=timezone.utc).isoformat(),
                "updated_at": datetime.now(tz=timezone.utc).isoformat(),
                "created_by": owner.user_id,
                "tags": tags or [],
                "priority": entity_metadata.get("priority", "medium"),
                "status": entity_metadata.get("status", "active"),
                "version": 1,
                "valid_from": datetime.now(tz=timezone.utc).isoformat(),
                "valid_to": None,
            }
        )
        return entity_metadata

    def _build_entity_document(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
        entity_type: str,
        name: str,
        observations: List[str],
        entity_metadata: Dict[str, Any],
        owner: OwnerScope,
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
            owner: Required owner stamp (#18825), written as top-level
                ``owner_user_id`` / ``owner_org_id`` (indexed as TAGs)

        Returns:
            Complete entity document dictionary
        """
        return {
            "id": entity_id,
            "type": entity_type,
            "name": name,
            "created_at": int(datetime.now(tz=timezone.utc).timestamp() * 1000),
            "updated_at": int(datetime.now(tz=timezone.utc).timestamp() * 1000),
            "observations": observations,
            "metadata": entity_metadata,
            **owner_fields(owner),
        }

    async def _store_entity_in_redis(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
        entity: Dict[str, Any],
    ) -> None:
        """
        Store entity in Redis and generate embedding if knowledge base available.

        Issue #620.
        """
        entity_key = f"memory:entity:{entity_id}"
        await self.redis_client.json().set(entity_key, "$", entity)

        if self.knowledge_base:
            await self._generate_entity_embedding(entity_id, entity)

    def _validate_entity_inputs(
        self: AutoBotMemoryGraphCore,
        entity_type: str,
        name: str,
    ) -> None:
        """
        Validate entity type and name inputs.

        Issue #620.
        """
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"Invalid entity_type: {entity_type}. Must be one of {ENTITY_TYPES}")

        if not name or not name.strip():
            raise ValueError("Entity name cannot be empty")

    async def create_entity(
        self: AutoBotMemoryGraphCore,
        entity_type: str,
        name: str,
        observations: List[str],
        metadata: Dict[str, Any] | None = None,
        tags: List[str] | None = None,
        *,
        owner: OwnerScope,
    ) -> Dict[str, Any]:
        """
        Create a new entity in the memory graph.

        Issue #620: Refactored to use extracted helpers for validation and storage.

        Args:
            entity_type: Type of entity (conversation, bug_fix, feature, etc.)
            name: Human-readable entity name
            observations: List of observation strings
            metadata: Optional additional metadata
            tags: Optional classification tags
            owner: REQUIRED (#18825) -- the principal's OwnerScope, or
                ``OwnerScope.shared()`` / ``OwnerScope.system()`` for platform data

        Returns:
            Created entity with entity_id and metadata

        Raises:
            OwnerScopeRequired: No concrete owner supplied
            ValueError: Invalid entity_type or empty name
            RuntimeError: Memory Graph not initialized
        """
        self.ensure_initialized()
        require_writer(owner)
        self._validate_entity_inputs(entity_type, name)

        try:
            return await self._write_new_entity(
                str(uuid.uuid4()), entity_type, name, observations, metadata, tags, owner
            )
        except Exception as e:
            logger.error("Failed to create entity: %s", e)
            raise RuntimeError("Entity creation failed") from e

    async def _write_new_entity(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
        entity_type: str,
        name: str,
        observations: List[str],
        metadata: Dict[str, Any] | None,
        tags: List[str] | None,
        owner: OwnerScope,
    ) -> Dict[str, Any]:
        """Build and store one entity document under a caller-chosen id (#18417)."""
        entity_metadata = self._prepare_entity_metadata(metadata, tags, owner)
        entity = self._build_entity_document(entity_id, entity_type, name, observations, entity_metadata, owner)
        await self._store_entity_in_redis(entity_id, entity)
        # The name can be anything a caller stored, a credential included; the type and id identify the row.
        logger.info("Created entity of type %s with ID %s", entity_type, entity_id[:8] + "...")
        return entity

    async def get_or_create_entity(
        self: AutoBotMemoryGraphCore,
        entity_type: str,
        name: str,
        observations: List[str],
        metadata: Dict[str, Any] | None = None,
        tags: List[str] | None = None,
        *,
        owner: OwnerScope,
    ) -> tuple[Dict[str, Any], bool]:
        """Atomically return the entity called ``name``, creating it if absent (#18417).

        Claiming the name and writing the document are one Lua script
        (``entity_upsert``), so concurrent callers cannot both create and no claim
        is visible without its document. Redis errors propagate; an unreadable
        lookup is never 'not found'. Entities that predate the name index are
        adopted into it. Returns ``(entity, created)``.
        """
        self.ensure_initialized()
        require_writer(owner)
        return await entity_upsert.get_or_create(self, entity_type, name, observations, metadata, tags, owner)

    # How many relevance hits to scan for an exact name before giving up (#13761).
    # The query *is* the name, so an exact match ranks at or near the top; this is
    # a ceiling for near-duplicate clusters ("Incident 7", "Incident 71", …), not
    # a page size.
    _NAME_RESOLUTION_CANDIDATES = 25

    async def _resolve_entity_by_name(
        self: AutoBotMemoryGraphCore,
        entity_name: str,
        strict: bool = False,
        *,
        owner: Any,
    ) -> Dict[str, Any] | None:
        """Resolve a name to an entity, preferring an exact match (#13761).

        This used to be ``search_entities(query=name, limit=1)`` — a
        relevance-ranked search whose top hit was returned unconditionally, so a
        name that does not exist still resolved, to whatever ranked first. Asking
        how "Redis Config" connects to "Incident 7" would return a real, correct
        path to "Incident 71": a confident answer to a question nobody asked.

        Exact match wins. A case-insensitive match is accepted next, because
        entity names are display strings and a case difference is not a different
        entity. Only when neither exists does the relevance hit stand, and the
        result carries ``_resolution`` so callers can tell the difference and warn
        rather than render it silently.
        """
        if strict:
            results = await entity_upsert.strict_search_by_name(
                self, entity_name, self._NAME_RESOLUTION_CANDIDATES, owner=owner
            )
        else:
            results = await self.search_entities(query=entity_name, limit=self._NAME_RESOLUTION_CANDIDATES, owner=owner)
        if not results:
            return None

        for candidate in results:
            if candidate.get("name") == entity_name:
                return {**candidate, "_resolution": "exact"}

        folded = entity_name.casefold()
        for candidate in results:
            if str(candidate.get("name", "")).casefold() == folded:
                return {**candidate, "_resolution": "exact"}

        logger.info(
            "Entity name %r has no exact match; falling back to the top relevance hit %r",
            entity_name,
            results[0].get("name"),
        )
        return {**results[0], "_resolution": "fuzzy"}

    async def get_entity(
        self: AutoBotMemoryGraphCore,
        entity_id: str | None = None,
        entity_name: str | None = None,
        include_relations: bool = False,
        strict: bool = False,
        *,
        owner: Any,
    ) -> Dict[str, Any] | None:
        """Retrieve an entity by ID or name, as ``owner``.

        ``owner`` (#18825) is REQUIRED, keyword-only, for id and name lookups alike: an OwnerScope or
        UNSCOPED_ALL_USERS; omitting it raises OwnerScopeRequired. An entity it may not read is absent.
        ``strict`` raises on a read error (#18417). A name lookup carries ``_resolution`` (#13761).
        """
        self.ensure_initialized()
        require_scope(owner)  # before the try: a missing scope must raise, not read as "not found"

        try:
            entity = await self._load_entity(entity_id, entity_name, strict, owner)
            if not entity:
                return None
            if include_relations:
                await self._attach_relations(entity, entity_id or entity["id"], owner)
            return entity
        except Exception as e:
            logger.error("Failed to get entity: %s", e)
            if strict:
                raise
            return None

    async def _load_entity(
        self: AutoBotMemoryGraphCore,
        entity_id: str | None,
        entity_name: str | None,
        strict: bool,
        owner: Any,
    ) -> Dict[str, Any] | None:
        """The entity ``owner`` may read for an id or a name; None when absent or not visible."""
        if entity_id:
            entity = await self.redis_client.json().get(f"memory:entity:{entity_id}")
            return entity if entity_visible(entity, owner) else None
        if entity_name:
            return await self._resolve_entity_by_name(entity_name, strict=strict, owner=owner)
        raise ValueError("Either entity_id or entity_name must be provided")

    async def _attach_relations(
        self: AutoBotMemoryGraphCore, entity: Dict[str, Any], entity_id: str, owner: Any
    ) -> None:
        """Fetch outgoing and incoming relations in parallel onto ``entity``, as ``owner`` (#18825).

        A relation whose OTHER endpoint ``owner`` cannot read is dropped (id and type both).
        """
        outgoing, incoming = await asyncio.gather(
            self._get_outgoing_relations(entity_id),
            self._get_incoming_relations(entity_id),
        )
        out_ok = await self._readable_relation_ends(entity_id, outgoing, "to", owner)
        in_ok = await self._readable_relation_ends(entity_id, incoming, "from", owner)
        entity["relations"] = {
            "outgoing": [r for r in outgoing if out_ok is None or r.get("to") in out_ok],
            "incoming": [r for r in incoming if in_ok is None or r.get("from") in in_ok],
        }

    async def _append_observations_to_entity(
        self: AutoBotMemoryGraphCore,
        entity_key: str,
        observations: List[str],
    ) -> None:
        """
        Append observations to entity and update timestamp in Redis.

        Uses asyncio.gather for parallel appends. Issue #620.
        """
        await asyncio.gather(
            *[self.redis_client.json().arrappend(entity_key, "$.observations", obs) for obs in observations]
        )
        await self.redis_client.json().set(
            entity_key, "$.updated_at", int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        )

    async def _refresh_entity_embedding(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
        entity_key: str,
    ) -> None:
        """
        Regenerate embedding for entity if knowledge base is available.

        Issue #620.
        """
        if self.knowledge_base:
            updated_entity = await self.redis_client.json().get(entity_key)
            await self._generate_entity_embedding(entity_id, updated_entity)

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
            # Mutation-by-name is not owner-scoped by #18825 (reads and ownership stamping are);
            # it resolves globally, so the sentinel is explicit here.
            entity = await self.get_entity(entity_name=entity_name, owner=UNSCOPED_ALL_USERS)
            if not entity:
                raise ValueError(f"Entity not found: {entity_name}")
            if entity.get("_resolution") == "fuzzy":
                # #13761: writing observations into a near-miss puts one entity's
                # facts on another. A read can be qualified; a write cannot.
                raise ValueError(f"Entity not found: {entity_name}")

            entity_id = entity["id"]
            entity_key = f"memory:entity:{entity_id}"

            await self._append_observations_to_entity(entity_key, observations)
            await self._refresh_entity_embedding(entity_id, entity_key)

            self.search_cache.clear()
            logger.info("Added %d observations to entity: %s", len(observations), entity_name)
            return await self.redis_client.json().get(entity_key)

        except Exception as e:
            logger.error("Failed to add observations: %s", e)
            raise RuntimeError("Add observations failed") from e

    async def invalidate_entity(
        self: AutoBotMemoryGraphCore,
        entity_id: str,
        ended_at: str | None = None,
    ) -> bool:
        """Mark entity as no longer valid by setting valid_to.

        Does NOT delete the entity — history is preserved.
        Returns True if found and updated, False if not found.

        Args:
            entity_id: UUID of the entity to invalidate
            ended_at: ISO-8601 timestamp for valid_to (default: now)
        """
        self.ensure_initialized()

        try:
            entity_key = f"memory:entity:{entity_id}"
            entity = await self.redis_client.json().get(entity_key)
            if not entity:
                return False

            valid_to = ended_at or datetime.now(tz=timezone.utc).isoformat()
            await self.redis_client.json().set(entity_key, "$.metadata.valid_to", valid_to)
            await self.redis_client.json().set(
                entity_key,
                "$.updated_at",
                int(datetime.now(tz=timezone.utc).timestamp() * 1000),
            )
            self.search_cache.clear()
            logger.info("Invalidated entity %s at %s", entity_id[:8] + "...", valid_to)
            return True

        except Exception as e:
            logger.error("Failed to invalidate entity %s: %s", entity_id, e)
            return False

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
            # Mutation-by-name is not owner-scoped by #18825; sentinel is explicit (see add_observations).
            entity = await self.get_entity(entity_name=entity_name, owner=UNSCOPED_ALL_USERS)
            if not entity:
                return False
            if entity.get("_resolution") == "fuzzy":
                # #13761: "delete Incident 7" must never delete "Incident 71".
                # Destructive by name requires the name to actually exist.
                logger.warning("Refusing to delete %r — no entity by that exact name", entity_name)
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
            await entity_upsert.release_name(self, entity["name"], entity_id)

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
            embedding_text = f"{name} {name} {name} {entity_type} {' '.join(observations * 6)}"

            self.embedding_cache[entity_id] = embedding_text

        except Exception as e:
            # CodeQL: false positive — entity_id is a UUID, not sensitive
            logger.warning("Failed to generate embedding for entity %s: %s", entity_id, e)
