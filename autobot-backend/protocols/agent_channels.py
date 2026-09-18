#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent peer channels: each delivers a message to its **recipient** (#16986).

Moved out of ``protocols/agent_communication.py``, which re-exports every name here.

Both channels used to deliver to their own owner. ``DirectCommunicationChannel.send``
queued a message on its own queue, and ``RedisCommunicationChannel`` pushed to and
popped from its own key. ``header.recipient`` was never read, so a request an agent
sent was answered by the sender itself.

A channel is now bound to the agent that owns it (``bind``). It is registered under
that agent's id as an inbound destination while it is open. ``send`` delivers to
``header.recipient`` and refuses a message with no recipient, or one addressed to an
agent this channel cannot reach. Broadcast is the protocol's job: it sends one
addressed copy to each id in ``recipients()``.

- **Direct:** in-process. A process-wide directory maps an agent id to its inbound
  queue.
- **Redis:** each owner reads its own inbox key. A sorted set holds each listening
  id with the time it last refreshed. The protocol's heartbeat refreshes it, so an
  agent that died without closing drops out after ``REGISTRATION_TTL_SECONDS``. A
  message to an agent nobody is listening for is refused rather than left in a list
  no one will read.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, Set

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from constants.threshold_constants import TimingConstants

if TYPE_CHECKING:
    from protocols.agent_communication import StandardMessage

logger = get_logger(__name__)

#: Prefix of each agent's Redis inbox list.
INBOX_KEY_PREFIX = "autobot:agent_comm:inbox:"
#: Redis sorted set: agent id -> when its Redis channel last refreshed.
REGISTERED_KEY = "autobot:agent_comm:registered"
#: How long an agent stays reachable over Redis after its last refresh. The protocol
#: refreshes on every heartbeat (``TimingConstants.SHORT_TIMEOUT``, 30 s), so the
#: default drops an agent after three missed beats.
REGISTRATION_TTL_SECONDS = env_int("AUTOBOT_AGENT_COMM_REGISTRATION_TTL_SECONDS", 90)


def inbox_key(agent_id: str) -> str:
    """The Redis list *agent_id*'s channel reads."""
    return f"{INBOX_KEY_PREFIX}{agent_id}"


class CommunicationChannel(ABC):
    """Abstract base class for communication channels"""

    def __init__(self, channel_id: str):
        """Initialize communication channel with ID and inactive state."""
        self.channel_id = channel_id
        self.is_active = False
        self.owner: str | None = None

    def bind(self, owner: str) -> None:
        """Make this channel *owner*'s: the destination for messages addressed to it."""
        self.owner = owner

    async def recipients(self) -> Set[str]:
        """The agent ids this channel can deliver to. None by default."""
        return set()

    async def refresh(self) -> None:
        """Re-advertise the owner as reachable. Nothing to renew by default."""

    @abstractmethod
    async def send(self, message: StandardMessage) -> bool:
        """Deliver *message* to ``message.header.recipient``. False if it cannot reach it."""

    @abstractmethod
    async def receive(self, timeout: float | None = None) -> StandardMessage | None:
        """Receive a message from the channel"""

    @abstractmethod
    async def close(self):
        """Close the communication channel"""


class RedisCommunicationChannel(CommunicationChannel):
    """Redis-based communication channel: reads its owner's inbox, writes to the recipient's."""

    def __init__(self, channel_id: str):
        """Initialize Redis channel with client connection and message queue."""
        super().__init__(channel_id)
        self.redis_client = get_redis_client()
        self.message_queue = asyncio.Queue()
        self.listener_task = None

    @property
    def channel_key(self) -> str:
        """The inbox this channel reads: its owner's, once bound."""
        return inbox_key(self.owner or self.channel_id)

    async def start(self):
        """Start the communication channel, and register its owner as reachable."""
        self.is_active = True
        await self.refresh()
        self.listener_task = asyncio.create_task(self._listen_for_messages())
        logger.info("Redis communication channel %s started", self.channel_id)

    async def _listen_for_messages(self):
        """Background task to listen for incoming messages"""
        from protocols.agent_communication import StandardMessage

        while self.is_active:
            try:
                # Use Redis BLPOP for blocking message retrieval (sync call in thread)
                result = await asyncio.to_thread(self.redis_client.blpop, self.channel_key, 1)
                if result:
                    _, message_json = result
                    if isinstance(message_json, bytes):
                        message_data = message_json.decode()
                    else:
                        message_data = str(message_json)
                    message = StandardMessage.from_json(message_data)
                    await self.message_queue.put(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error listening for messages: %s", e)
                await asyncio.sleep(TimingConstants.STANDARD_DELAY)

    async def refresh(self) -> None:
        """Renew the owner's registration, and prune every registration past its TTL."""
        if self.owner:
            now = time.time()
            await asyncio.to_thread(self.redis_client.zadd, REGISTERED_KEY, {self.owner: now})
            await asyncio.to_thread(
                self.redis_client.zremrangebyscore, REGISTERED_KEY, "-inf", now - REGISTRATION_TTL_SECONDS
            )

    async def recipients(self) -> Set[str]:
        """Every agent id whose Redis channel refreshed within the TTL."""
        cutoff = time.time() - REGISTRATION_TTL_SECONDS
        members = await asyncio.to_thread(self.redis_client.zrangebyscore, REGISTERED_KEY, cutoff, "+inf")
        return {m.decode() if isinstance(m, bytes) else str(m) for m in members or ()}

    async def _listening(self, recipient: str | None) -> bool:
        if not recipient:
            return False
        score = await asyncio.to_thread(self.redis_client.zscore, REGISTERED_KEY, recipient)
        return score is not None and score >= time.time() - REGISTRATION_TTL_SECONDS

    async def send(self, message: StandardMessage) -> bool:
        """Push *message* onto its recipient's inbox, if that recipient is listening."""
        recipient = message.header.recipient
        try:
            if not await self._listening(recipient):
                logger.debug("Redis channel %s cannot reach recipient %r", self.channel_id, recipient)
                return False
            key = inbox_key(recipient)
            await asyncio.to_thread(self.redis_client.rpush, key, message.to_json())
            # Set TTL for automatic cleanup
            if message.header.expires_at:
                ttl = int(message.header.expires_at - time.time())
                if ttl > 0:
                    await asyncio.to_thread(self.redis_client.expire, key, ttl)
            logger.debug("Message sent to %s: %s", recipient, message.header.message_id)
            return True
        except Exception as e:
            logger.error("Failed to send Redis message: %s", e)
            return False

    async def receive(self, timeout: float | None = None) -> StandardMessage | None:
        """Receive a message from the channel"""
        try:
            if timeout:
                message = await asyncio.wait_for(self.message_queue.get(), timeout=timeout)
            else:
                message = await self.message_queue.get()
            return message
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error("Error receiving message: %s", e)
            return None

    async def close(self):
        """Close the Redis communication channel, and stop advertising its owner."""
        self.is_active = False
        if self.owner:
            await asyncio.to_thread(self.redis_client.zrem, REGISTERED_KEY, self.owner)
        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                logger.debug("Listener task cancelled for channel %s", self.channel_id)
        logger.info("Redis communication channel %s closed", self.channel_id)


#: In-process inbound queues of every open direct channel, by owner agent id.
_DIRECT_INBOXES: Dict[str, asyncio.Queue] = {}


class DirectCommunicationChannel(CommunicationChannel):
    """Direct in-memory communication channel for same-process agents"""

    def __init__(self, channel_id: str):
        """Initialize direct in-memory channel with message queue."""
        super().__init__(channel_id)
        self.message_queue = asyncio.Queue()
        self.is_active = True

    def bind(self, owner: str) -> None:
        """Register this channel's queue as *owner*'s in-process inbox."""
        super().bind(owner)
        _DIRECT_INBOXES[owner] = self.message_queue

    async def recipients(self) -> Set[str]:
        """Every agent id with an open direct channel in this process."""
        return set(_DIRECT_INBOXES)

    async def send(self, message: StandardMessage) -> bool:
        """Put *message* on its recipient's in-process queue, if the recipient is here."""
        try:
            inbox = _DIRECT_INBOXES.get(message.header.recipient or "")
            if not self.is_active or inbox is None:
                return False
            await inbox.put(message)
            logger.debug("Message sent directly to %s: %s", message.header.recipient, message.header.message_id)
            return True
        except Exception as e:
            logger.error("Failed to send direct message: %s", e)
            return False

    async def receive(self, timeout: float | None = None) -> StandardMessage | None:
        """Receive a message from the direct queue"""
        try:
            if timeout:
                message = await asyncio.wait_for(self.message_queue.get(), timeout=timeout)
            else:
                message = await self.message_queue.get()
            return message
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error("Error receiving direct message: %s", e)
            return None

    async def close(self):
        """Close the direct communication channel, and withdraw its owner's inbox"""
        self.is_active = False
        if self.owner and _DIRECT_INBOXES.get(self.owner) is self.message_queue:
            del _DIRECT_INBOXES[self.owner]
        # Clear remaining messages
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
