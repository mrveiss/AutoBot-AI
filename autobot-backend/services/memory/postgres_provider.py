# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PostgreSQL Memory Provider (Issue #4344)"""

from typing import Any, Dict, List

from autobot_memory_graph import AutoBotMemoryGraph
from autobot_memory_graph.owner_scope import UNSCOPED_ALL_USERS, OwnerScope, owner_from_source
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class PostgresMemoryProvider:
    """PostgreSQL-backed memory provider using AutoBotMemoryGraph."""

    def __init__(self) -> None:
        self.memory_graph: AutoBotMemoryGraph | None = None

    async def initialize(self) -> None:
        try:
            self.memory_graph = AutoBotMemoryGraph()
            await self.memory_graph.initialize()
            logger.info("PostgreSQL memory provider initialized")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL memory provider: {e}")
            raise

    async def close(self) -> None:
        if self.memory_graph:
            try:
                await self.memory_graph.close()
                logger.info("PostgreSQL memory provider closed")
            except Exception as e:
                logger.error(f"Error closing PostgreSQL memory provider: {e}")

    async def prefetch(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.memory_graph:
            logger.warning("Memory graph not initialized for prefetch")
            return {}
        try:
            conversation_id = context.get("conversation_id")
            user_id = context.get("user_id")
            owner = owner_from_source(context)
            if owner is None:
                logger.warning("Memory prefetch skipped: no user scope in context")
                return {}
            result = {}
            if conversation_id:
                conversation = await self.memory_graph.get_entity(
                    entity_name=f"conversation_{conversation_id}", owner=owner
                )
                if conversation:
                    result["conversation"] = conversation
                related = await self.memory_graph.search_entities(conversation_id, owner=owner)
                result["related_entities"] = related[:10]
            if user_id:
                user_entity = await self.memory_graph.get_entity(entity_name=f"user_{user_id}", owner=owner)
                if user_entity:
                    result["user"] = user_entity
            return result
        except Exception as e:
            logger.error(f"Error prefetching memory context: {e}")
            return {}

    async def sync(self, turn: Dict[str, Any]) -> None:
        if not self.memory_graph:
            logger.warning("Memory graph not initialized for sync")
            return
        try:
            entity_updates = turn.get("entity_updates", [])
            relation_updates = turn.get("relation_updates", [])
            for update in entity_updates:
                if update.get("action") == "create":
                    await self.memory_graph.create_entity(
                        entity_type=update["entity_type"],
                        name=update["name"],
                        observations=update.get("observations", []),
                        owner=owner_from_source(turn) or OwnerScope.system(),
                    )
                elif update.get("action") == "update":
                    await self._apply_entity_updates(update["entity_id"], update.get("changes", {}))
                elif update.get("action") == "delete":
                    await self._delete_entity_by_id(update["entity_id"])
            for rel in relation_updates:
                if rel.get("action") == "create":
                    await self.memory_graph.create_relation(
                        from_entity=rel["from_entity"],
                        to_entity=rel["to_entity"],
                        relation_type=rel["relation_type"],
                    )
                elif rel.get("action") == "delete":
                    await self.memory_graph.delete_relation(
                        from_entity=rel["from_entity"],
                        to_entity=rel["to_entity"],
                        relation_type=rel["relation_type"],
                    )
            logger.info(f"Synced {len(entity_updates)} entity and " f"{len(relation_updates)} relation updates")
        except Exception as e:
            logger.error(f"Error syncing memory updates: {e}")
            raise

    async def search(self, query: str, limit: int = 10, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        if not self.memory_graph:
            logger.warning("Memory graph not initialized for search")
            return []
        owner = owner_from_source(filters)
        if owner is None:
            logger.warning("Memory search refused: filters carry no user scope")
            return []
        try:
            results = await self.memory_graph.search_entities(query, limit=limit, owner=owner)
            return results
        except Exception as e:
            logger.error(f"Error searching memory: {e}")
            return []

    async def get_entity(self, entity_id: str, *, owner: OwnerScope | None = None) -> Dict[str, Any] | None:
        if not self.memory_graph:
            return None
        if owner is None:
            logger.warning("Entity read refused: no caller scope supplied (fail closed, #18825)")
            return None
        try:
            return await self.memory_graph.get_entity(entity_id=entity_id, owner=owner)
        except Exception as e:
            logger.error(f"Error getting entity {entity_id}: {e}")
            return None

    async def _name_for_id(self, entity_id: str) -> str:
        """Resolve an entity id to the name the graph's write API is keyed by (#18414)."""
        # Id -> name resolution for a by-name mutation; by-name mutations are not owner-scoped (#18876).
        entity = await self.memory_graph.get_entity(entity_id=entity_id, owner=UNSCOPED_ALL_USERS)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")
        return entity["name"]

    async def _apply_entity_updates(self, entity_id: str, updates: Dict[str, Any]) -> None:
        """Apply updates through the graph's one mutation, add_observations (#18414).

        The graph has no field-level update; observations are its only mutable
        content. Any other key is refused rather than silently dropped.
        """
        unsupported = set(updates) - {"observations"}
        if unsupported:
            raise ValueError(f"Unsupported entity update fields: {sorted(unsupported)}")
        observations = updates.get("observations")
        if not observations:
            raise ValueError("Entity update has no observations to apply")
        await self.memory_graph.add_observations(await self._name_for_id(entity_id), observations)

    async def _delete_entity_by_id(self, entity_id: str) -> None:
        """The graph deletes by name; resolve the id first (#18414)."""
        await self.memory_graph.delete_entity(await self._name_for_id(entity_id))

    async def update_entity(self, entity_id: str, updates: Dict[str, Any]) -> None:
        if not self.memory_graph:
            logger.warning("Memory graph not initialized for update")
            return
        try:
            await self._apply_entity_updates(entity_id, updates)
        except Exception as e:
            logger.error(f"Error updating entity {entity_id}: {e}")
            raise

    async def delete_entity(self, entity_id: str) -> None:
        if not self.memory_graph:
            logger.warning("Memory graph not initialized for delete")
            return
        try:
            await self._delete_entity_by_id(entity_id)
        except Exception as e:
            logger.error(f"Error deleting entity {entity_id}: {e}")
            raise

    async def health_check(self) -> bool:
        if not self.memory_graph:
            return False
        try:
            await self.memory_graph.get_entity(
                "_health_check", owner=UNSCOPED_ALL_USERS
            )  # liveness probe, reads no user data
            return True
        except Exception as e:
            logger.error(f"PostgreSQL memory provider health check failed: {e}")
            return False
