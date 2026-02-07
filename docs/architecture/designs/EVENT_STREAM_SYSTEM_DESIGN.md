# Event Stream System Design

**Issue**: #645 - Implement Industry-Standard Agent Architecture Patterns
**Author**: mrveiss
**Date**: 2025-12-28
**Status**: Draft

---

## 1. Overview

This document defines the design for an Event Stream System inspired by the Manus agent architecture. The system provides a typed, chronological event stream that enables:

- Clear task progression tracking
- Multi-step iteration control
- Audit trail for debugging
- Integration with Planner and Knowledge modules

---

## 2. Event Types

### 2.1 Core Event Enumeration

```python
from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import uuid

class EventType(Enum):
    """Typed events for the agent event stream (Manus-inspired)"""
    MESSAGE = auto()      # User inputs and agent responses
    ACTION = auto()       # Tool calls / function calling
    OBSERVATION = auto()  # Execution results from tools
    PLAN = auto()         # Task step planning from Planner module
    KNOWLEDGE = auto()    # Task-relevant knowledge from Knowledge module
    DATASOURCE = auto()   # API documentation and data sources
    SYSTEM = auto()       # System events (startup, shutdown, errors)
```

### 2.2 Event Data Structure

```python
@dataclass
class AgentEvent:
    """Standard event structure for the event stream"""

    # Identity
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.MESSAGE

    # Timing
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Content
    content: dict = field(default_factory=dict)

    # Source tracking
    source: str = "user"  # user, agent, planner, knowledge_module, tool, system
    agent_id: Optional[str] = None

    # Correlation for multi-turn conversations
    correlation_id: Optional[str] = None  # Links related events
    parent_event_id: Optional[str] = None  # For nested events (action → observation)

    # Task context
    task_id: Optional[str] = None  # Current task being executed
    step_number: Optional[int] = None  # Current step in plan

    # Metadata
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize for Redis storage"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.name,
            "timestamp": self.timestamp.isoformat(),
            "content": self.content,
            "source": self.source,
            "agent_id": self.agent_id,
            "correlation_id": self.correlation_id,
            "parent_event_id": self.parent_event_id,
            "task_id": self.task_id,
            "step_number": self.step_number,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentEvent":
        """Deserialize from Redis storage"""
        return cls(
            event_id=data["event_id"],
            event_type=EventType[data["event_type"]],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            content=data["content"],
            source=data["source"],
            agent_id=data.get("agent_id"),
            correlation_id=data.get("correlation_id"),
            parent_event_id=data.get("parent_event_id"),
            task_id=data.get("task_id"),
            step_number=data.get("step_number"),
            metadata=data.get("metadata", {}),
        )
```

---

## 3. Event Content Schemas

### 3.1 MESSAGE Event

```python
@dataclass
class MessageContent:
    """Content for MESSAGE events"""
    role: str  # "user" or "assistant"
    text: str
    attachments: list[dict] = field(default_factory=list)

    # For assistant messages
    tool_calls_made: list[str] = field(default_factory=list)
    confidence: Optional[float] = None
```

### 3.2 ACTION Event

```python
@dataclass
class ActionContent:
    """Content for ACTION events (tool calls)"""
    tool_name: str
    arguments: dict
    tool_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Execution context
    is_parallel: bool = False
    parallel_group_id: Optional[str] = None  # Groups parallel actions
    depends_on: list[str] = field(default_factory=list)  # Action IDs this depends on
```

### 3.3 OBSERVATION Event

```python
@dataclass
class ObservationContent:
    """Content for OBSERVATION events (tool results)"""
    action_id: str  # Links to parent ACTION event
    tool_name: str

    # Result
    success: bool
    result: Any
    error: Optional[str] = None

    # Performance
    execution_time_ms: float = 0.0
    device_used: Optional[str] = None  # For NPU/GPU operations
```

### 3.4 PLAN Event

```python
@dataclass
class PlanContent:
    """Content for PLAN events (from Planner module)"""
    task_description: str
    steps: list[dict]  # [{step_num, description, status, dependencies}]
    current_step: int
    total_steps: int

    # Status tracking
    status: str  # "planning", "in_progress", "completed", "blocked", "failed"
    reflection: Optional[str] = None  # Current state assessment

    # Updates
    is_update: bool = False  # True if updating existing plan
    changes_made: list[str] = field(default_factory=list)
```

### 3.5 KNOWLEDGE Event

```python
@dataclass
class KnowledgeContent:
    """Content for KNOWLEDGE events (from Knowledge module)"""
    knowledge_items: list[dict]  # Retrieved knowledge
    query: str  # What triggered the retrieval

    # Relevance scoring
    scope: str  # "python", "frontend", "database", "general"
    relevance_score: float

    # Source tracking
    source_type: str  # "chromadb", "memory_mcp", "file_system"
    document_ids: list[str] = field(default_factory=list)
```

---

## 4. Event Stream Manager

### 4.1 Core Interface

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, Callable

class EventStreamManager(ABC):
    """Abstract interface for event stream management"""

    @abstractmethod
    async def publish(self, event: AgentEvent) -> None:
        """Publish an event to the stream"""
        pass

    @abstractmethod
    async def subscribe(
        self,
        event_types: list[EventType] | None = None,
        task_id: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Subscribe to events, optionally filtered by type or task"""
        pass

    @abstractmethod
    async def get_latest(
        self,
        count: int = 10,
        event_types: list[EventType] | None = None,
        task_id: str | None = None,
    ) -> list[AgentEvent]:
        """Get the most recent events"""
        pass

    @abstractmethod
    async def get_task_events(self, task_id: str) -> list[AgentEvent]:
        """Get all events for a specific task"""
        pass

    @abstractmethod
    async def get_event(self, event_id: str) -> AgentEvent | None:
        """Get a specific event by ID"""
        pass
```

### 4.2 Redis Implementation

```python
import asyncio
import json
import logging
from typing import AsyncIterator

import redis.asyncio as redis

from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)

class RedisEventStreamManager(EventStreamManager):
    """Redis-based event stream using Streams and Pub/Sub"""

    # Redis key patterns
    STREAM_KEY = "autobot:events:stream"
    TASK_STREAM_PREFIX = "autobot:events:task:"
    PUBSUB_CHANNEL = "autobot:events:live"
    EVENT_HASH_PREFIX = "autobot:events:data:"

    # Retention settings
    MAX_STREAM_LENGTH = 10000  # Maximum events in main stream
    TASK_STREAM_TTL = 86400  # 24 hours TTL for task streams

    def __init__(self):
        self._redis: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None
        self._listeners: dict[str, list[Callable]] = {}

    async def _get_redis(self) -> redis.Redis:
        """Get async Redis client"""
        if self._redis is None:
            self._redis = await get_redis_client(async_client=True, database="main")
        return self._redis

    async def publish(self, event: AgentEvent) -> None:
        """Publish event to Redis Stream and Pub/Sub"""
        redis_client = await self._get_redis()
        event_data = event.to_dict()
        event_json = json.dumps(event_data, ensure_ascii=False)

        # Store full event data in hash
        await redis_client.hset(
            f"{self.EVENT_HASH_PREFIX}{event.event_id}",
            mapping={"data": event_json}
        )

        # Add to main stream (with trimming)
        await redis_client.xadd(
            self.STREAM_KEY,
            {"event_id": event.event_id, "type": event.event_type.name},
            maxlen=self.MAX_STREAM_LENGTH,
            approximate=True,
        )

        # Add to task-specific stream if task_id present
        if event.task_id:
            task_stream = f"{self.TASK_STREAM_PREFIX}{event.task_id}"
            await redis_client.xadd(
                task_stream,
                {"event_id": event.event_id, "type": event.event_type.name},
            )
            await redis_client.expire(task_stream, self.TASK_STREAM_TTL)

        # Publish for real-time subscribers
        await redis_client.publish(self.PUBSUB_CHANNEL, event_json)

        logger.debug(
            "Published event: %s (type=%s, task=%s)",
            event.event_id, event.event_type.name, event.task_id
        )

    async def subscribe(
        self,
        event_types: list[EventType] | None = None,
        task_id: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Subscribe to live events via Pub/Sub"""
        redis_client = await self._get_redis()
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(self.PUBSUB_CHANNEL)

        type_filter = set(t.name for t in event_types) if event_types else None

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    event_data = json.loads(message["data"])
                    event = AgentEvent.from_dict(event_data)

                    # Apply filters
                    if type_filter and event.event_type.name not in type_filter:
                        continue
                    if task_id and event.task_id != task_id:
                        continue

                    yield event
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Failed to parse event: %s", e)
        finally:
            await pubsub.unsubscribe(self.PUBSUB_CHANNEL)

    async def get_latest(
        self,
        count: int = 10,
        event_types: list[EventType] | None = None,
        task_id: str | None = None,
    ) -> list[AgentEvent]:
        """Get most recent events from stream"""
        redis_client = await self._get_redis()

        # Choose stream based on task_id
        stream_key = (
            f"{self.TASK_STREAM_PREFIX}{task_id}"
            if task_id
            else self.STREAM_KEY
        )

        # Read from stream (newest first)
        # We fetch more than needed to allow for filtering
        fetch_count = count * 3 if event_types else count
        entries = await redis_client.xrevrange(stream_key, count=fetch_count)

        type_filter = set(t.name for t in event_types) if event_types else None
        events = []

        for entry_id, entry_data in entries:
            if len(events) >= count:
                break

            event_id = entry_data.get("event_id")
            if not event_id:
                continue

            # Filter by type if needed
            if type_filter and entry_data.get("type") not in type_filter:
                continue

            # Fetch full event data
            event_json = await redis_client.hget(
                f"{self.EVENT_HASH_PREFIX}{event_id}", "data"
            )
            if event_json:
                try:
                    event = AgentEvent.from_dict(json.loads(event_json))
                    events.append(event)
                except (json.JSONDecodeError, KeyError):
                    pass

        return events

    async def get_task_events(self, task_id: str) -> list[AgentEvent]:
        """Get all events for a task (chronological order)"""
        redis_client = await self._get_redis()
        task_stream = f"{self.TASK_STREAM_PREFIX}{task_id}"

        entries = await redis_client.xrange(task_stream)
        events = []

        for entry_id, entry_data in entries:
            event_id = entry_data.get("event_id")
            if not event_id:
                continue

            event_json = await redis_client.hget(
                f"{self.EVENT_HASH_PREFIX}{event_id}", "data"
            )
            if event_json:
                try:
                    event = AgentEvent.from_dict(json.loads(event_json))
                    events.append(event)
                except (json.JSONDecodeError, KeyError):
                    pass

        return events

    async def get_event(self, event_id: str) -> AgentEvent | None:
        """Get a specific event by ID"""
        redis_client = await self._get_redis()
        event_json = await redis_client.hget(
            f"{self.EVENT_HASH_PREFIX}{event_id}", "data"
        )

        if not event_json:
            return None

        try:
            return AgentEvent.from_dict(json.loads(event_json))
        except (json.JSONDecodeError, KeyError):
            return None
```

---

## 5. Integration Points

### 5.1 Agent Orchestrator Integration

```python
# In autobot-user-backend/agents/agent_orchestrator.py

class AgentOrchestrator:
    def __init__(self):
        self.event_stream = RedisEventStreamManager()

    async def process_request(self, user_message: str, task_id: str) -> str:
        # 1. Publish MESSAGE event (user input)
        await self.event_stream.publish(AgentEvent(
            event_type=EventType.MESSAGE,
            content=MessageContent(role="user", text=user_message).to_dict(),
            source="user",
            task_id=task_id,
        ))

        # 2. Get relevant knowledge (triggers KNOWLEDGE event)
        knowledge = await self._get_knowledge(user_message, task_id)

        # 3. Get plan from planner (triggers PLAN event)
        plan = await self._get_plan(user_message, knowledge, task_id)

        # 4. Execute tools (triggers ACTION + OBSERVATION events)
        result = await self._execute_plan(plan, task_id)

        # 5. Publish MESSAGE event (assistant response)
        await self.event_stream.publish(AgentEvent(
            event_type=EventType.MESSAGE,
            content=MessageContent(role="assistant", text=result).to_dict(),
            source="agent",
            task_id=task_id,
        ))

        return result
```

### 5.2 Tool Registry Integration

```python
# In autobot-user-backend/tools/tool_registry.py

class ToolRegistry:
    def __init__(self, event_stream: EventStreamManager):
        self.event_stream = event_stream

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict,
        task_id: str,
    ) -> Any:
        # Create ACTION event
        action_event = AgentEvent(
            event_type=EventType.ACTION,
            content=ActionContent(
                tool_name=tool_name,
                arguments=arguments,
            ).to_dict(),
            source="agent",
            task_id=task_id,
        )
        await self.event_stream.publish(action_event)

        # Execute tool
        start_time = time.monotonic()
        try:
            result = await self._dispatch_tool(tool_name, arguments)
            success = True
            error = None
        except Exception as e:
            result = None
            success = False
            error = str(e)

        execution_time = (time.monotonic() - start_time) * 1000

        # Create OBSERVATION event
        await self.event_stream.publish(AgentEvent(
            event_type=EventType.OBSERVATION,
            content=ObservationContent(
                action_id=action_event.event_id,
                tool_name=tool_name,
                success=success,
                result=result,
                error=error,
                execution_time_ms=execution_time,
            ).to_dict(),
            source="tool",
            task_id=task_id,
            parent_event_id=action_event.event_id,
        ))

        if not success:
            raise ToolExecutionError(error)

        return result
```

---

## 6. WebSocket Integration

### 6.1 Real-time Event Streaming to Frontend

```python
# In autobot-user-backend/api/websocket.py

from fastapi import WebSocket
from src.events.event_stream import RedisEventStreamManager, EventType

async def stream_events(websocket: WebSocket, task_id: str | None = None):
    """Stream events to frontend via WebSocket"""
    event_stream = RedisEventStreamManager()

    await websocket.accept()

    try:
        async for event in event_stream.subscribe(task_id=task_id):
            await websocket.send_json({
                "type": "event",
                "data": event.to_dict(),
            })
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        await websocket.close()
```

---

## 7. Configuration

### 7.1 Environment Variables

```bash
# Event Stream Configuration
AUTOBOT_EVENT_STREAM_MAX_LENGTH=10000
AUTOBOT_EVENT_STREAM_TASK_TTL=86400
AUTOBOT_EVENT_STREAM_REDIS_DB=main
```

### 7.2 SSOT Config Integration

```python
# In src/config/ssot_config.py

@dataclass
class EventStreamConfig:
    max_stream_length: int = 10000
    task_stream_ttl: int = 86400
    redis_database: str = "main"
    pubsub_channel: str = "autobot:events:live"
```

---

## 8. Migration Strategy

### 8.1 Phase 1: Add Event Stream (Non-Breaking)

1. Add new `src/events/` module with event types and stream manager
2. Initialize event stream in orchestrator (no changes to existing flow)
3. Begin publishing events alongside existing execution

### 8.2 Phase 2: Integrate with Existing Systems

1. Update tool registry to publish ACTION/OBSERVATION events
2. Update knowledge retrieval to publish KNOWLEDGE events
3. Add WebSocket endpoint for frontend streaming

### 8.3 Phase 3: Full Agent Loop Integration

1. Modify agent orchestrator to use event stream for context
2. Implement Planner module with PLAN events
3. Enable event-driven iteration control

---

## 9. Testing Strategy

### 9.1 Unit Tests

```python
# tests/unit/test_event_stream.py

async def test_publish_and_get_event():
    """Test event publishing and retrieval"""
    manager = RedisEventStreamManager()

    event = AgentEvent(
        event_type=EventType.MESSAGE,
        content={"role": "user", "text": "Hello"},
        task_id="test-task-123",
    )

    await manager.publish(event)

    retrieved = await manager.get_event(event.event_id)
    assert retrieved is not None
    assert retrieved.event_type == EventType.MESSAGE
    assert retrieved.content["text"] == "Hello"

async def test_task_events_chronological():
    """Test that task events are returned in order"""
    manager = RedisEventStreamManager()
    task_id = "test-task-order"

    for i in range(5):
        await manager.publish(AgentEvent(
            event_type=EventType.ACTION,
            content={"step": i},
            task_id=task_id,
        ))

    events = await manager.get_task_events(task_id)
    assert len(events) == 5
    for i, event in enumerate(events):
        assert event.content["step"] == i
```

---

## 10. File Structure

```
src/events/
├── __init__.py
├── types.py           # EventType enum, AgentEvent dataclass
├── content_schemas.py # MessageContent, ActionContent, etc.
├── stream_manager.py  # EventStreamManager interface
├── redis_stream.py    # RedisEventStreamManager implementation
└── utils.py           # Helper functions
```

---

## 11. References

- Manus Agent Loop: `docs/external_apps/.../Manus Agent Tools & Prompt/Agent loop.txt`
- Redis Streams: https://redis.io/docs/data-types/streams/
- Current event manager: `src/event_manager.py`
- Current Redis integration: `autobot-user-backend/utils/redis_management/`
