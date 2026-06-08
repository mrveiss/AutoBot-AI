# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Event Stream System

Industry-standard event stream architecture inspired by Manus agent patterns.
Provides typed events for tracking agent operations, task progression, and debugging.

Components:
- types: Event type definitions and data structures
- stream_manager: Redis-based event stream management
- utils: Helper functions for event handling

Usage:
    from events import EventStreamManager, AgentEvent, EventType

    # Initialize manager
    manager = EventStreamManager()

    # Publish event
    await manager.publish(AgentEvent(
        event_type=EventType.MESSAGE,
        content={"role": "user", "text": "Hello"},
        task_id="task-123",
    ))

    # Get recent events
    events = await manager.get_latest(count=10)
"""

from events.stream_manager import EventStreamManager, RedisEventStreamManager
from events.types import (
    ActionContent,
    AgentEvent,
    ArtifactType,
    EventType,
    KnowledgeContent,
    MessageContent,
    ObservationContent,
    PlanContent,
    TaskArtifact,
    build_artifact,
    create_observation_event,
)

__all__ = [
    # Types
    "EventType",
    "AgentEvent",
    "MessageContent",
    "ActionContent",
    "ObservationContent",
    "PlanContent",
    "KnowledgeContent",
    # Artifact support (#4094)
    "ArtifactType",
    "TaskArtifact",
    "build_artifact",
    "create_observation_event",
    # Managers
    "EventStreamManager",
    "RedisEventStreamManager",
]
