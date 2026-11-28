# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AutoBot Memory Graph - Conversation entity creation.

Split out of ``entities.py`` (#18825) to keep it under the file-size ceiling.
"""

from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

from .core import AutoBotMemoryGraphCore
from .owner_scope import OwnerScope

logger = get_logger(__name__)


class ConversationEntityMixin:
    """Mixin that mirrors a chat session into a ``conversation`` entity."""

    def _prepare_conversation_data(
        self: AutoBotMemoryGraphCore,
        session_id: str,
        metadata: Dict[str, Any] | None,
        observations: List[str] | None,
    ) -> tuple[List[str], List[str], Dict[str, Any]]:
        """
        Prepare observations, tags, and metadata for conversation entity.

        Issue #620.

        Returns:
            Tuple of (entity_observations, tags, conv_metadata)
        """
        entity_observations = []
        tags = []

        if observations:
            entity_observations = observations
        elif self.chat_history_manager:
            entity_observations = [f"Conversation session: {session_id}"]
            tags = ["conversation"]

        conv_metadata = metadata or {}
        conv_metadata.update(
            {
                "session_id": session_id,
                "priority": "low",
                "status": "active",
            }
        )
        return entity_observations, tags, conv_metadata

    async def create_conversation_entity(
        self: AutoBotMemoryGraphCore,
        session_id: str,
        metadata: Dict[str, Any] | None = None,
        observations: List[str] | None = None,
        *,
        owner: OwnerScope,
    ) -> Dict[str, Any]:
        """
        Automatically create entity from chat session.

        Args:
            session_id: Chat session identifier
            metadata: Optional additional metadata
            observations: Optional list of observations to add immediately
            owner: REQUIRED (#18825) -- the session owner

        Returns:
            Created conversation entity
        """
        self.ensure_initialized()

        try:
            entity_observations, tags, conv_metadata = self._prepare_conversation_data(
                session_id, metadata, observations
            )

            entity = await self.create_entity(
                entity_type="conversation",
                name=f"Conversation {session_id[:8]}",
                observations=entity_observations,
                metadata=conv_metadata,
                tags=tags,
                owner=owner,
            )

            logger.info("Created conversation entity for session %s", session_id)
            return entity

        except Exception as e:
            logger.error("Failed to create conversation entity: %s", e)
            raise
