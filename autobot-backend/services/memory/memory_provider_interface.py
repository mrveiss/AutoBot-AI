# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Memory Provider Interface - Abstract Base Class

Defines the contract for all memory provider implementations.
Providers handle data storage, retrieval, and semantic search operations.

Issue #4344: Provider-based memory architecture with external provider support
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class MemoryProvider(ABC):
    """
    Abstract base class for memory providers.

    Providers implement the unified interface for memory operations,
    enabling pluggable backend support (PostgreSQL, Redis, Milvus, etc.).

    Methods:
    - prefetch(context): Pre-load relevant context for a given agent turn
    - sync(turn): Persist memory updates from an agent turn
    - search(query): Find similar memories by semantic similarity
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider connection and resources."""

    @abstractmethod
    async def close(self) -> None:
        """Clean up provider resources."""

    @abstractmethod
    async def prefetch(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-load relevant context for an agent turn.

        Args:
            context: Agent context containing conversation_id, user_id, session_id, etc.

        Returns:
            Dictionary of pre-loaded memories with relevance metadata
        """

    @abstractmethod
    async def sync(self, turn: Dict[str, Any]) -> None:
        """
        Persist memory updates from an agent turn.

        Args:
            turn: Agent turn data containing:
                - entity_updates: List of entity changes
                - relation_updates: List of relationship changes
                - timestamp: When the turn occurred
        """

    @abstractmethod
    async def search(self, query: str, limit: int = 10, filters: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        """
        Find similar memories by semantic similarity.

        Args:
            query: Search query string
            limit: Maximum number of results to return
            filters: Optional filters to narrow search scope

        Returns:
            List of matching memories with scores and metadata
        """

    @abstractmethod
    async def get_entity(self, entity_id: str) -> Dict[str, Any] | None:
        """Get a specific entity by ID."""

    @abstractmethod
    async def update_entity(self, entity_id: str, updates: Dict[str, Any]) -> None:
        """Update a specific entity."""

    @abstractmethod
    async def delete_entity(self, entity_id: str) -> None:
        """Delete a specific entity."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is healthy and accessible."""
