# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""PostgreSQL Memory Provider (Issue #4344)"""

from typing import Any, Dict, List

from autobot_memory_graph import AutoBotMemoryGraph
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
            result = {}
            if conversation_id:
                conversation = await self.memory_graph.get_entity(f"conversation_{conversation_id}")
                if conversation:
                    result["conversation"] = conversation
                related = await self.memory_graph.search_entities(conversation_id)
                result["related_entities"] = related[:10]
            if user_id:
                user_entity = await self.memory_graph.get_entity(f"user_{user_id}")
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
                    )
                elif update.get("action") == "update":
                    await self.memory_graph.update_entity(
                        entity_id=update["entity_id"],
                        **update.get("changes", {}),
                    )
                elif update.get("action") == "delete":
                    await self.memory_graph.delete_entity(update["entity_id"])
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
                    )
            logger.info(f"Synced {len(entity_updates)} entity and " f"{len(relation_updates)} relation updates")
        except Exception as e:
            logger.error(f"Error syncing memory updates: {e}")
            raise

    async def search(self, query: str, limit: int = 10, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        if not self.memory_graph:
            logger.warning("Memory graph not initialized for search")
            return []
        try:
            results = await self.memory_graph.search_entities(query, limit=limit)
            return results
        except Exception as e:
            logger.error(f"Error searching memory: {e}")
            return []

    async def get_entity(self, entity_id: str) -> Dict[str, Any] | None:
        if not self.memory_graph:
            return None
        try:
            return await self.memory_graph.get_entity(entity_id)
        except Exception as e:
            logger.error(f"Error getting entity {entity_id}: {e}")
            return None

    async def update_entity(self, entity_id: str, updates: Dict[str, Any]) -> None:
        if not self.memory_graph:
            logger.warning("Memory graph not initialized for update")
            return
        try:
            await self.memory_graph.update_entity(entity_id, **updates)
        except Exception as e:
            logger.error(f"Error updating entity {entity_id}: {e}")
            raise

    async def delete_entity(self, entity_id: str) -> None:
        if not self.memory_graph:
            logger.warning("Memory graph not initialized for delete")
            return
        try:
            await self.memory_graph.delete_entity(entity_id)
        except Exception as e:
            logger.error(f"Error deleting entity {entity_id}: {e}")
            raise

    async def health_check(self) -> bool:
        if not self.memory_graph:
            return False
        try:
            await self.memory_graph.get_entity("_health_check")
            return True
        except Exception as e:
            logger.error(f"PostgreSQL memory provider health check failed: {e}")
            return False
