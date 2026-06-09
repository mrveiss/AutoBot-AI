# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Memory Manager - Unified Access Layer (Issue #4344)"""

from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

from .external_provider_factory import ExternalProviderFactory
from .postgres_provider import PostgresMemoryProvider

logger = get_logger(__name__)


class MemoryManager:
    """
    Unified memory access layer that routes operations to appropriate providers.
    """

    def __init__(self) -> None:
        self.built_in: PostgresMemoryProvider = PostgresMemoryProvider()
        self.external: Any | None = None
        self.external_enabled: bool = False

    async def initialize(self) -> None:
        try:
            await self.built_in.initialize()
            logger.info("Built-in PostgreSQL memory provider initialized")
            try:
                self.external = await ExternalProviderFactory.get_provider()
                if self.external:
                    self.external_enabled = True
                    logger.info("External memory provider initialized")
            except Exception as e:
                logger.warning(f"External memory provider unavailable, " f"using built-in only: {e}")
                self.external = None
                self.external_enabled = False
        except Exception as e:
            logger.error(f"Failed to initialize memory manager: {e}")
            raise

    async def close(self) -> None:
        try:
            if self.built_in:
                await self.built_in.close()
            if self.external:
                await self.external.close()
            await ExternalProviderFactory.close()
            logger.info("Memory manager closed")
        except Exception as e:
            logger.error(f"Error closing memory manager: {e}")

    async def prefetch(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if self.external_enabled and self.external:
            try:
                result = await self.external.prefetch(context)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"External provider prefetch failed, " f"falling back to built-in: {e}")
        try:
            return await self.built_in.prefetch(context)
        except Exception as e:
            logger.error(f"Built-in provider prefetch failed: {e}")
            return {}

    async def sync(self, turn: Dict[str, Any]) -> None:
        try:
            await self.built_in.sync(turn)
        except Exception as e:
            logger.error(f"Built-in provider sync failed: {e}")
            raise

        if self.external_enabled and self.external:
            try:
                await self.external.sync(turn)
            except Exception as e:
                logger.warning(f"External provider sync failed, continuing: {e}")

    async def search(self, query: str, limit: int = 10, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        if self.external_enabled and self.external:
            try:
                results = await self.external.search(query, limit, filters)
                if results:
                    return results
            except Exception as e:
                logger.warning(f"External provider search failed, " f"falling back to built-in: {e}")
        try:
            return await self.built_in.search(query, limit, filters)
        except Exception as e:
            logger.error(f"Built-in provider search failed: {e}")
            return []

    async def get_entity(self, entity_id: str) -> Dict[str, Any] | None:
        try:
            return await self.built_in.get_entity(entity_id)
        except Exception as e:
            logger.error(f"Error getting entity: {e}")
            return None

    async def update_entity(self, entity_id: str, updates: Dict[str, Any]) -> None:
        try:
            await self.built_in.update_entity(entity_id, updates)
        except Exception as e:
            logger.error(f"Built-in provider update failed: {e}")
            raise

        if self.external_enabled and self.external:
            try:
                await self.external.update_entity(entity_id, updates)
            except Exception as e:
                logger.warning(f"External provider update failed: {e}")

    async def delete_entity(self, entity_id: str) -> None:
        try:
            await self.built_in.delete_entity(entity_id)
        except Exception as e:
            logger.error(f"Built-in provider delete failed: {e}")
            raise

        if self.external_enabled and self.external:
            try:
                await self.external.delete_entity(entity_id)
            except Exception as e:
                logger.warning(f"External provider delete failed: {e}")

    async def health_check(self) -> Dict[str, bool]:
        health = {}
        try:
            health["built_in"] = await self.built_in.health_check()
        except Exception as e:
            logger.error(f"Built-in health check failed: {e}")
            health["built_in"] = False

        if self.external_enabled and self.external:
            try:
                health["external"] = await self.external.health_check()
            except Exception as e:
                logger.warning(f"External health check failed: {e}")
                health["external"] = False

        return health
