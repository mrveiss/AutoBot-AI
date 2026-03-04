# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""ServiceMessageBus — Redis-backed cross-service audit trail (#1379).

Provides persistent, ordered storage and real-time pub/sub for
:class:`~autobot_shared.models.service_message.ServiceMessage` envelopes.

Storage strategy (mirrors ``RedisEventStreamManager``):

1. **Main stream** ``autobot:service:messages`` — ordered log, trimmed to 50k
2. **Message hash** ``autobot:service:msg:{msg_id}`` — full JSON, 14-day TTL
3. **Correlation set** ``autobot:service:corr:{corr_id}`` — set of msg_ids,
   7-day TTL
4. **Pub/Sub channel** ``autobot:service:live`` — real-time subscribers

Usage::

    from autobot_shared.message_bus import get_message_bus

    bus = get_message_bus()
    await bus.publish(msg)
    chain = await bus.get_correlation_chain(msg.correlation_id)
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from autobot_shared.models.service_message import ServiceMessage
from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class ServiceMessageBusConfig:
    """Configuration for ServiceMessageBus Redis keys and retention."""

    stream_key: str = "autobot:service:messages"
    message_hash_prefix: str = "autobot:service:msg:"
    correlation_prefix: str = "autobot:service:corr:"
    pubsub_channel: str = "autobot:service:live"
    max_stream_length: int = 50_000
    message_data_ttl: int = 86400 * 14  # 14 days
    correlation_ttl: int = 86400 * 7  # 7 days


class ServiceMessageBus:
    """Redis-backed bus for cross-service ``ServiceMessage`` envelopes.

    Stores messages in a Redis Stream for ordering, individual hashes
    for random access, sorted sets for correlation chains, and pub/sub
    for real-time delivery.
    """

    def __init__(self, config: Optional[ServiceMessageBusConfig] = None) -> None:
        self.config = config or ServiceMessageBusConfig()
        self._redis: Any = None
        self._pubsub: Any = None

    # ------------------------------------------------------------------
    # Redis connection (lazy)
    # ------------------------------------------------------------------

    async def _get_redis(self) -> Any:
        """Return an async Redis client, creating on first use."""
        if self._redis is None:
            self._redis = await get_redis_client(async_client=True, database="logs")
            logger.debug("ServiceMessageBus Redis connection established")
        return self._redis

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(self, msg: ServiceMessage) -> None:
        """Persist *msg* and notify real-time subscribers.

        Steps:
        1. ``HSET`` full JSON into ``msg:{msg_id}`` with TTL.
        2. ``XADD`` to the main stream (trimmed to *max_stream_length*).
        3. ``SADD`` msg_id into ``corr:{correlation_id}`` with TTL.
        4. ``PUBLISH`` JSON on the live channel.
        """
        redis = await self._get_redis()
        msg_json = msg.model_dump_json()
        hash_key = f"{self.config.message_hash_prefix}{msg.msg_id}"
        corr_key = f"{self.config.correlation_prefix}{msg.correlation_id}"

        await self._store_message(redis, hash_key, msg_json)
        await self._append_stream(redis, msg)
        await self._add_correlation(redis, corr_key, msg.msg_id)
        await redis.publish(self.config.pubsub_channel, msg_json)

        logger.debug(
            "Published message %s (type=%s, %s->%s)",
            msg.msg_id[:8],
            msg.msg_type,
            msg.sender,
            msg.receiver,
        )

    async def _store_message(self, redis: Any, hash_key: str, msg_json: str) -> None:
        """HSET the full message and set TTL."""
        await redis.hset(hash_key, mapping={"data": msg_json})
        await redis.expire(hash_key, self.config.message_data_ttl)

    async def _append_stream(self, redis: Any, msg: ServiceMessage) -> None:
        """XADD a lightweight reference to the main stream."""
        await redis.xadd(
            self.config.stream_key,
            {
                "msg_id": msg.msg_id,
                "sender": msg.sender,
                "receiver": msg.receiver,
                "msg_type": msg.msg_type,
            },
            maxlen=self.config.max_stream_length,
            approximate=True,
        )

    async def _add_correlation(self, redis: Any, corr_key: str, msg_id: str) -> None:
        """SADD msg_id into the correlation set and refresh TTL."""
        await redis.sadd(corr_key, msg_id)
        await redis.expire(corr_key, self.config.correlation_ttl)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def get_message(self, msg_id: str) -> Optional[ServiceMessage]:
        """Retrieve a single message by ID from its hash key."""
        redis = await self._get_redis()
        hash_key = f"{self.config.message_hash_prefix}{msg_id}"
        raw = await redis.hget(hash_key, "data")
        if raw is None:
            return None
        return self._deserialize(raw)

    async def get_correlation_chain(self, correlation_id: str) -> list[ServiceMessage]:
        """Return all messages sharing *correlation_id*, sorted by ts."""
        redis = await self._get_redis()
        corr_key = f"{self.config.correlation_prefix}{correlation_id}"
        member_ids = await redis.smembers(corr_key)
        if not member_ids:
            return []

        messages: list[ServiceMessage] = []
        for raw_id in member_ids:
            msg_id = self._decode(raw_id)
            msg = await self.get_message(msg_id)
            if msg is not None:
                messages.append(msg)

        messages.sort(key=lambda m: m.ts)
        return messages

    async def get_latest(
        self,
        count: int = 50,
        sender: Optional[str] = None,
        receiver: Optional[str] = None,
        msg_type: Optional[str] = None,
    ) -> list[ServiceMessage]:
        """Return the *count* most recent messages, optionally filtered.

        Reads lightweight stream entries first, then hydrates matching
        messages from their hash keys.
        """
        redis = await self._get_redis()
        fetch_count = count * 3 if (sender or receiver or msg_type) else count
        entries = await redis.xrevrange(self.config.stream_key, count=fetch_count)

        messages: list[ServiceMessage] = []
        for _entry_id, entry_data in entries:
            if len(messages) >= count:
                break
            decoded = self._decode_entry(entry_data)
            if not self._matches_filter(decoded, sender, receiver, msg_type):
                continue
            msg = await self.get_message(decoded.get("msg_id", ""))
            if msg is not None:
                messages.append(msg)
        return messages

    # ------------------------------------------------------------------
    # Subscribe (real-time)
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        sender: Optional[str] = None,
        receiver: Optional[str] = None,
        msg_type: Optional[str] = None,
    ) -> AsyncIterator[ServiceMessage]:
        """Yield live messages via pub/sub, optionally filtered."""
        redis = await self._get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(self.config.pubsub_channel)

        try:
            async for raw_message in pubsub.listen():
                if raw_message["type"] != "message":
                    continue
                msg = self._parse_pubsub(raw_message)
                if msg is None:
                    continue
                if not self._matches_msg(msg, sender, receiver, msg_type):
                    continue
                yield msg
        finally:
            await pubsub.unsubscribe(self.config.pubsub_channel)
            await pubsub.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Release Redis connections."""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        if self._redis:
            await self._redis.close()
            self._redis = None
        logger.debug("ServiceMessageBus connections closed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decode(value: Any) -> str:
        """Decode bytes to str if necessary."""
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    @staticmethod
    def _deserialize(raw: Any) -> Optional[ServiceMessage]:
        """Parse raw Redis value into a ServiceMessage."""
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        try:
            return ServiceMessage.model_validate_json(text)
        except Exception as exc:
            logger.warning("Failed to deserialize message: %s", exc)
            return None

    @staticmethod
    def _decode_entry(entry_data: dict) -> dict:
        """Decode bytes keys/values in a stream entry."""
        return {
            (k.decode("utf-8") if isinstance(k, bytes) else k): (
                v.decode("utf-8") if isinstance(v, bytes) else v
            )
            for k, v in entry_data.items()
        }

    @staticmethod
    def _matches_filter(
        decoded: dict,
        sender: Optional[str],
        receiver: Optional[str],
        msg_type: Optional[str],
    ) -> bool:
        """Check whether a decoded stream entry matches filters."""
        if sender and decoded.get("sender") != sender:
            return False
        if receiver and decoded.get("receiver") != receiver:
            return False
        if msg_type and decoded.get("msg_type") != msg_type:
            return False
        return True

    @staticmethod
    def _matches_msg(
        msg: ServiceMessage,
        sender: Optional[str],
        receiver: Optional[str],
        msg_type: Optional[str],
    ) -> bool:
        """Check whether a ServiceMessage matches filters."""
        if sender and msg.sender != sender:
            return False
        if receiver and msg.receiver != receiver:
            return False
        if msg_type and msg.msg_type != msg_type:
            return False
        return True

    def _parse_pubsub(self, raw_message: dict) -> Optional[ServiceMessage]:
        """Parse a raw pub/sub message into a ServiceMessage."""
        data = raw_message.get("data")
        if data is None:
            return None
        text = data.decode("utf-8") if isinstance(data, bytes) else data
        try:
            return ServiceMessage.model_validate_json(text)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failed to parse pub/sub message: %s", exc)
            return None


# ------------------------------------------------------------------
# Singleton factory
# ------------------------------------------------------------------

_bus_instance: Optional[ServiceMessageBus] = None


def get_message_bus(
    config: Optional[ServiceMessageBusConfig] = None,
) -> ServiceMessageBus:
    """Return the singleton ``ServiceMessageBus`` instance.

    Creates the bus on first call. Pass *config* only on the first call
    to override defaults; subsequent calls ignore it.
    """
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = ServiceMessageBus(config=config)
    return _bus_instance
