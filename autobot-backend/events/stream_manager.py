# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Event Stream Manager

Redis-based event stream implementation using Redis Streams and Pub/Sub.
Provides persistent storage, real-time subscription, and efficient querying.

Features:
- Redis Streams for persistent, ordered event storage
- Pub/Sub for real-time event notification
- Task-specific streams for isolated event history
- Automatic stream trimming to manage storage

Usage:
    from events import RedisEventStreamManager, AgentEvent, EventType

    manager = RedisEventStreamManager()

    # Publish event
    await manager.publish(AgentEvent(
        event_type=EventType.MESSAGE,
        content={"role": "user", "text": "Hello"},
        task_id="task-123",
    ))

    # Subscribe to live events
    async for event in manager.subscribe(task_id="task-123"):
        process_event(event)  # Handle the event

    # Get historical events
    events = await manager.get_task_events("task-123")
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Optional

from events.types import AgentEvent, EventType

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class EventStreamConfig:
    """Event stream configuration"""

    # Redis key patterns
    stream_key: str = "autobot:events:stream"
    task_stream_prefix: str = "autobot:events:task:"
    pubsub_channel: str = "autobot:events:live"
    event_hash_prefix: str = "autobot:events:data:"

    # Retention settings
    max_stream_length: int = 10000  # Maximum events in main stream
    task_stream_ttl: int = 86400  # 24 hours TTL for task streams
    event_data_ttl: int = 86400 * 7  # 7 days TTL for event data

    # Performance
    batch_size: int = 100  # Events per batch for queries


# =============================================================================
# Abstract Interface
# =============================================================================


class EventStreamManager(ABC):
    """Abstract interface for event stream management"""

    @abstractmethod
    async def publish(self, event: AgentEvent) -> None:
        """Publish an event to the stream"""

    @abstractmethod
    async def subscribe(
        self,
        event_types: Optional[list[EventType]] = None,
        task_id: Optional[str] = None,
    ) -> AsyncIterator[AgentEvent]:
        """Subscribe to events, optionally filtered by type or task"""

    @abstractmethod
    async def get_latest(
        self,
        count: int = 10,
        event_types: Optional[list[EventType]] = None,
        task_id: Optional[str] = None,
    ) -> list[AgentEvent]:
        """Get the most recent events"""

    @abstractmethod
    async def get_task_events(self, task_id: str) -> list[AgentEvent]:
        """Get all events for a specific task"""

    @abstractmethod
    async def get_event(self, event_id: str) -> Optional[AgentEvent]:
        """Get a specific event by ID"""

    @abstractmethod
    async def close(self) -> None:
        """Close connections and cleanup"""


# =============================================================================
# Redis Implementation
# =============================================================================


class RedisEventStreamManager(EventStreamManager):
    """Redis-based event stream using Streams and Pub/Sub"""

    def __init__(self, config: Optional[EventStreamConfig] = None):
        self.config = config or EventStreamConfig()
        self._redis: Any = None
        self._pubsub: Any = None
        self._initialized = False
        self._listeners: dict[str, list[Callable]] = {}

    async def _get_redis(self) -> Any:
        """Get async Redis client with lazy initialization"""
        if self._redis is None:
            try:
                from autobot_shared.redis_client import get_redis_client

                self._redis = await get_redis_client(async_client=True, database="main")
                self._initialized = True
                logger.debug("Event stream Redis connection established")
            except Exception as e:
                logger.error("Failed to connect to Redis for event stream: %s", e)
                raise

        return self._redis

    async def publish(self, event: AgentEvent) -> None:
        """
        Publish event to Redis Stream and Pub/Sub.

        Events are stored in:
        1. Main stream (autobot:events:stream) - for global queries
        2. Task stream (autobot:events:task:{task_id}) - for task isolation
        3. Event hash (autobot:events:data:{event_id}) - full event data
        4. Pub/Sub channel - for real-time subscribers
        """
        redis_client = await self._get_redis()
        event_data = event.to_dict()
        event_json = json.dumps(event_data, ensure_ascii=False, default=str)

        try:
            # Store full event data in hash (with TTL)
            event_key = f"{self.config.event_hash_prefix}{event.event_id}"
            await redis_client.hset(event_key, mapping={"data": event_json})
            await redis_client.expire(event_key, self.config.event_data_ttl)

            # Add to main stream (with trimming)
            await redis_client.xadd(
                self.config.stream_key,
                {"event_id": event.event_id, "type": event.event_type.name},
                maxlen=self.config.max_stream_length,
                approximate=True,
            )

            # Add to task-specific stream if task_id present
            if event.task_id:
                task_stream = f"{self.config.task_stream_prefix}{event.task_id}"
                await redis_client.xadd(
                    task_stream,
                    {"event_id": event.event_id, "type": event.event_type.name},
                )
                await redis_client.expire(task_stream, self.config.task_stream_ttl)

            # Publish for real-time subscribers
            await redis_client.publish(self.config.pubsub_channel, event_json)

            logger.debug(
                "Published event: %s (type=%s, task=%s)",
                event.event_id[:8],
                event.event_type.name,
                event.task_id,
            )

        except Exception as e:
            logger.error("Failed to publish event %s: %s", event.event_id, e)
            raise

    async def subscribe(
        self,
        event_types: Optional[list[EventType]] = None,
        task_id: Optional[str] = None,
    ) -> AsyncIterator[AgentEvent]:
        """
        Subscribe to live events via Pub/Sub.

        Args:
            event_types: Filter to specific event types (None = all)
            task_id: Filter to specific task (None = all)

        Yields:
            AgentEvent objects matching the filters
        """
        redis_client = await self._get_redis()
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(self.config.pubsub_channel)

        type_filter = set(t.name for t in event_types) if event_types else None

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    # Handle both bytes and string data
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    event_data = json.loads(data)
                    event = AgentEvent.from_dict(event_data)

                    # Apply filters
                    if type_filter and event.event_type.name not in type_filter:
                        continue
                    if task_id and event.task_id != task_id:
                        continue

                    yield event

                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Failed to parse event from pubsub: %s", e)

        finally:
            await pubsub.unsubscribe(self.config.pubsub_channel)
            await pubsub.close()

    def _decode_entry_data(self, entry_data: dict) -> dict:
        """Decode bytes keys/values in stream entry data. Issue #620."""
        if not isinstance(entry_data, dict):
            return entry_data
        return {
            (k.decode("utf-8") if isinstance(k, bytes) else k): (
                v.decode("utf-8") if isinstance(v, bytes) else v
            )
            for k, v in entry_data.items()
        }

    def _get_stream_key(self, task_id: Optional[str]) -> str:
        """Get the appropriate stream key based on task_id. Issue #620."""
        if task_id:
            return f"{self.config.task_stream_prefix}{task_id}"
        return self.config.stream_key

    async def get_latest(
        self,
        count: int = 10,
        event_types: Optional[list[EventType]] = None,
        task_id: Optional[str] = None,
    ) -> list[AgentEvent]:
        """Get most recent events from stream.

        Args:
            count: Maximum number of events to return
            event_types: Filter to specific types (None = all)
            task_id: Get from task-specific stream (None = main stream)

        Returns:
            List of events (newest first)
        """
        redis_client = await self._get_redis()
        stream_key = self._get_stream_key(task_id)
        fetch_count = count * 3 if event_types else count
        entries = await redis_client.xrevrange(stream_key, count=fetch_count)

        type_filter = set(t.name for t in event_types) if event_types else None
        events = []

        for entry_id, entry_data in entries:
            if len(events) >= count:
                break

            entry_data = self._decode_entry_data(entry_data)
            event_id = entry_data.get("event_id")
            if not event_id:
                continue

            if type_filter and entry_data.get("type") not in type_filter:
                continue

            event = await self.get_event(event_id)
            if event:
                events.append(event)

        return events

    async def get_task_events(self, task_id: str) -> list[AgentEvent]:
        """
        Get all events for a task (chronological order).

        Args:
            task_id: Task identifier

        Returns:
            List of events for the task (oldest first)
        """
        redis_client = await self._get_redis()
        task_stream = f"{self.config.task_stream_prefix}{task_id}"

        # Check if stream exists
        exists = await redis_client.exists(task_stream)
        if not exists:
            return []

        entries = await redis_client.xrange(task_stream)
        events = []

        for entry_id, entry_data in entries:
            entry_data = self._decode_entry_data(entry_data)
            event_id = entry_data.get("event_id")
            if not event_id:
                continue

            event = await self.get_event(event_id)
            if event:
                events.append(event)

        return events

    async def get_event(self, event_id: str) -> Optional[AgentEvent]:
        """
        Get a specific event by ID.

        Args:
            event_id: Event identifier

        Returns:
            AgentEvent if found, None otherwise
        """
        redis_client = await self._get_redis()
        event_key = f"{self.config.event_hash_prefix}{event_id}"

        event_json = await redis_client.hget(event_key, "data")

        if not event_json:
            return None

        # Handle bytes
        if isinstance(event_json, bytes):
            event_json = event_json.decode("utf-8")

        try:
            return AgentEvent.from_dict(json.loads(event_json))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse event %s: %s", event_id, e)
            return None

    async def get_events_by_type(
        self,
        event_type: EventType,
        task_id: Optional[str] = None,
        count: int = 100,
    ) -> list[AgentEvent]:
        """
        Get events of a specific type.

        Args:
            event_type: Type of events to retrieve
            task_id: Optional task filter
            count: Maximum events to return

        Returns:
            List of matching events
        """
        return await self.get_latest(
            count=count,
            event_types=[event_type],
            task_id=task_id,
        )

    async def get_action_observation_pairs(
        self,
        task_id: str,
    ) -> list[tuple[AgentEvent, Optional[AgentEvent]]]:
        """
        Get ACTION events paired with their OBSERVATION events.

        Args:
            task_id: Task identifier

        Returns:
            List of (action, observation) tuples
        """
        events = await self.get_task_events(task_id)

        # Group by action_id
        actions: dict[str, AgentEvent] = {}
        observations: dict[str, AgentEvent] = {}

        for event in events:
            if event.event_type == EventType.ACTION:
                action_content = event.content
                tool_id = action_content.get("tool_id", event.event_id)
                actions[tool_id] = event
            elif event.event_type == EventType.OBSERVATION:
                action_id = event.content.get("action_id")
                if action_id:
                    observations[action_id] = event

        # Pair them up
        pairs = []
        for action_id, action in actions.items():
            observation = observations.get(action_id)
            pairs.append((action, observation))

        return pairs

    async def count_events(
        self,
        task_id: Optional[str] = None,
        event_types: Optional[list[EventType]] = None,
    ) -> int:
        """
        Count events matching criteria.

        Args:
            task_id: Optional task filter
            event_types: Optional type filter

        Returns:
            Count of matching events
        """
        redis_client = await self._get_redis()

        stream_key = (
            f"{self.config.task_stream_prefix}{task_id}"
            if task_id
            else self.config.stream_key
        )

        # Get stream length
        length = await redis_client.xlen(stream_key)

        # If no type filter, return total length
        if not event_types:
            return length

        # Otherwise, we need to count matching types
        # This is expensive, so limit the scan
        type_filter = set(t.name for t in event_types)
        count = 0

        entries = await redis_client.xrange(stream_key)
        for entry_id, entry_data in entries:
            entry_data = self._decode_entry_data(entry_data)
            if entry_data.get("type") in type_filter:
                count += 1

        return count

    async def delete_task_events(self, task_id: str) -> int:
        """
        Delete all events for a task.

        Args:
            task_id: Task identifier

        Returns:
            Number of events deleted
        """
        redis_client = await self._get_redis()
        task_stream = f"{self.config.task_stream_prefix}{task_id}"

        # Get all event IDs first
        entries = await redis_client.xrange(task_stream)
        event_ids = []

        for entry_id, entry_data in entries:
            entry_data = self._decode_entry_data(entry_data)
            event_id = entry_data.get("event_id")
            if event_id:
                event_ids.append(event_id)

        # Delete event data hashes
        for event_id in event_ids:
            event_key = f"{self.config.event_hash_prefix}{event_id}"
            await redis_client.delete(event_key)

        # Delete task stream
        await redis_client.delete(task_stream)

        logger.info("Deleted %d events for task %s", len(event_ids), task_id)
        return len(event_ids)

    async def close(self) -> None:
        """Close Redis connections"""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None

        if self._redis:
            await self._redis.close()
            self._redis = None

        self._initialized = False
        logger.debug("Event stream connections closed")


# =============================================================================
# In-Memory Implementation (for testing)
# =============================================================================


class InMemoryEventStreamManager(EventStreamManager):
    """In-memory event stream for testing and development"""

    def __init__(self):
        self._events: dict[str, AgentEvent] = {}
        self._task_events: dict[str, list[str]] = {}
        self._stream: list[str] = []
        self._subscribers: list[asyncio.Queue] = []

    async def publish(self, event: AgentEvent) -> None:
        """Store event in memory and notify subscribers"""
        self._events[event.event_id] = event
        self._stream.append(event.event_id)

        if event.task_id:
            if event.task_id not in self._task_events:
                self._task_events[event.task_id] = []
            self._task_events[event.task_id].append(event.event_id)

        # Notify subscribers
        for queue in self._subscribers:
            await queue.put(event)

    async def subscribe(
        self,
        event_types: Optional[list[EventType]] = None,
        task_id: Optional[str] = None,
    ) -> AsyncIterator[AgentEvent]:
        """Subscribe to events"""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)

        type_filter = set(event_types) if event_types else None

        try:
            while True:
                event = await queue.get()

                if type_filter and event.event_type not in type_filter:
                    continue
                if task_id and event.task_id != task_id:
                    continue

                yield event
        finally:
            self._subscribers.remove(queue)

    async def get_latest(
        self,
        count: int = 10,
        event_types: Optional[list[EventType]] = None,
        task_id: Optional[str] = None,
    ) -> list[AgentEvent]:
        """Get recent events"""
        if task_id:
            event_ids = self._task_events.get(task_id, [])
        else:
            event_ids = self._stream

        type_filter = set(event_types) if event_types else None
        events = []

        for event_id in reversed(event_ids):
            if len(events) >= count:
                break

            event = self._events.get(event_id)
            if not event:
                continue

            if type_filter and event.event_type not in type_filter:
                continue

            events.append(event)

        return events

    async def get_task_events(self, task_id: str) -> list[AgentEvent]:
        """Get all events for a task"""
        event_ids = self._task_events.get(task_id, [])
        return [self._events[eid] for eid in event_ids if eid in self._events]

    async def get_event(self, event_id: str) -> Optional[AgentEvent]:
        """Get event by ID"""
        return self._events.get(event_id)

    async def close(self) -> None:
        """Clear subscribers"""
        self._subscribers.clear()
