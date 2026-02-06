# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Memory Graph - Modular Package

This package provides the AutoBotMemoryGraph system for entity-relationship tracking,
semantic search, and cross-conversation context management.

Issue #716: Refactored from monolithic autobot_memory_graph.py (2,104 lines) into
a modular package structure for improved maintainability.

Package Structure:
- core.py: Core graph operations and initialization
- entities.py: Entity management (create, get, update, delete)
- relations.py: Relationship management and traversal
- queries.py: Search and query operations
- user_session.py: User-centric session tracking (Issue #608)

Key Features:
- Entity management (conversations, bugs, features, decisions, tasks)
- Bidirectional relationship tracking
- Hybrid search (RedisSearch filters + Ollama semantic embeddings)
- Cross-conversation context and project continuity
- User-centric session tracking with activity logging
- Secret management with scoping (user, session, shared)

Backward Compatibility:
- All existing imports continue to work:
  `from src.autobot_memory_graph import AutoBotMemoryGraph`
"""

from .core import (  # noqa: F401 - re-exports for package API
    ENTITY_TYPES,
    INCOMING_DIRECTIONS,
    OUTGOING_DIRECTIONS,
    RELATION_TYPES,
    VALID_ACTIVITY_TYPES,
    AutoBotMemoryGraphCore,
    config,
)
from .entities import EntityOperationsMixin
from .queries import QueryOperationsMixin
from .relations import RelationOperationsMixin
from .secrets import SecretManagementMixin
from .user_session import UserSessionMixin


class AutoBotMemoryGraph(
    EntityOperationsMixin,
    RelationOperationsMixin,
    QueryOperationsMixin,
    UserSessionMixin,
    SecretManagementMixin,
    AutoBotMemoryGraphCore,
):
    """
    Enhanced memory system with graph-based relationship tracking
    and semantic search capabilities.

    This class combines all functionality from the modular package:
    - Core initialization and configuration (AutoBotMemoryGraphCore)
    - Entity operations (EntityOperationsMixin)
    - Relation operations (RelationOperationsMixin)
    - Query operations (QueryOperationsMixin)
    - User-centric session tracking (UserSessionMixin)

    Integrates with existing ChatHistoryManager to provide:
    - Entity extraction from conversations
    - Relationship tracking
    - Semantic search
    - Cross-conversation context
    - User session management (Issue #608)

    Usage:
        ```python
        from src.autobot_memory_graph import AutoBotMemoryGraph

        memory = AutoBotMemoryGraph()
        await memory.initialize()

        # Create entity
        entity = await memory.create_entity(
            entity_type="task",
            name="Implement feature X",
            observations=["Started implementation"]
        )

        # Search entities
        results = await memory.search_entities("feature")

        # Create relations
        await memory.create_relation(
            from_entity="Task A",
            to_entity="Task B",
            relation_type="depends_on"
        )

        # Close when done
        await memory.close()
        ```
    """

    # Expose class-level constants for backward compatibility
    ENTITY_TYPES = ENTITY_TYPES
    RELATION_TYPES = RELATION_TYPES


# Public API exports
__all__ = [
    # Main class
    "AutoBotMemoryGraph",
    # Core class (for advanced usage)
    "AutoBotMemoryGraphCore",
    # Constants
    "ENTITY_TYPES",
    "RELATION_TYPES",
    "VALID_ACTIVITY_TYPES",
    "OUTGOING_DIRECTIONS",
    "INCOMING_DIRECTIONS",
    # Mixins (for extension)
    "EntityOperationsMixin",
    "RelationOperationsMixin",
    "QueryOperationsMixin",
    "UserSessionMixin",
    "SecretManagementMixin",
]
