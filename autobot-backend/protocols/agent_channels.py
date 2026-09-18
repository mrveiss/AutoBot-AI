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

A channel is now bound to the agent that owns it (``bind``). While it is open, it is
registered under that agent's id as the agent's inbound destination. One live owner
per id: a second channel claiming a live id is refused, never silently swapped in
(#16946), and a channel only ever withdraws its own registration. ``send`` delivers to
``header.recipient`` and refuses a message with no recipient, or one addressed to an
agent this channel cannot reach. Broadcast is the protocol's job: it sends one
addressed copy to each id in ``recipients()``.

- **Direct:** in-process. A process-wide directory maps an agent id to its inbound
  queue.
- **Redis:** each owner reads its own inbox list. A sorted set holds each listening id
  with the time it last refreshed, and a hash names the channel instance that owns it.
  The protocol's heartbeat refreshes the registration, but only while the channel's
  listener is running. So an agent that died, or whose listener died, stops being a
  destination after ``REGISTRATION_TTL_SECONDS``. Times are the **Redis server's**
  (``TIME``), so clock skew between hosts cannot make a live agent look stale. An
  inbox is capped at ``INBOX_MAX_LENGTH`` (oldest dropped, logged) and expires
  ``INBOX_TTL_SECONDS`` after its last write, so no list grows without bound.

Until #16962 authenticates the envelope, anything with write access to Redis can push
to any inbox. The caps above bound what such a writer can cost a recipient; they do
not authenticate it.
"""

from __future__ import annotations

import asyncio
import uuid
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
#: Redis sorted set: agent id -> Redis server time of its channel's last refresh.
REGISTERED_KEY = "autobot:agent_comm:registered"
#: Redis hash: agent id -> the channel instance that owns its registration.
OWNERS_KEY = "autobot:agent_comm:owners"
#: How long an agent stays reachable over Redis after its last refresh. The protocol
#: refreshes on every heartbeat (``TimingConstants.SHORT_TIMEOUT``, 30 s), so the
#: default drops an agent after three missed beats.
REGISTRATION_TTL_SECONDS = env_int("AUTOBOT_AGENT_COMM_REGISTRATION_TTL_SECONDS", 90)
#: Most messages an inbox holds; beyond it the oldest are dropped.
INBOX_MAX_LENGTH = env_int("AUTOBOT_AGENT_COMM_INBOX_MAX_LENGTH", 1000)
#: Seconds an inbox survives after its last write, so an abandoned one is reclaimed.
INBOX_TTL_SECONDS = env_int("AUTOBOT_AGENT_COMM_INBOX_TTL_SECONDS", 3600)


class ChannelOwnerCollisionError(RuntimeError):
    """A second channel claimed an agent id that a live channel already owns."""


def inbox_key(agent_id: str) -> str:
    """The Redis list *agent_id*'s channel reads."""
    return f"{INBOX_KEY_PREFIX}{agent_id}"


def _text(value) -> str | None:
    return value.decode() if isinstance(value, bytes) else value


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
        self.instance = uuid.uuid4().hex

    @property
    def channel_key(self) -> str:
        """The inbox this channel reads: its owner's, once bound."""
        return inbox_key(self.owner or self.channel_id)

    async def _redis(self, command: str, *args):
        return await asyncio.to_thread(getattr(self.redis_client, command), *args)

    async def _now(self) -> float:
        """The Redis server's clock, which every host shares."""
        seconds, micros = await self._redis("time")
        return int(seconds) + int(micros) / 1_000_000

    async def _listening(self, agent_id: str | None) -> bool:
        """Whether *agent_id*'s channel refreshed within the TTL."""
        if not agent_id:
            return False
        score = await self._redis("zscore", REGISTERED_KEY, agent_id)
        return score is not None and float(score) >= await self._now() - REGISTRATION_TTL_SECONDS

    async def _owns_registration(self) -> bool:
        return self.owner is not None and _text(await self._redis("hget", OWNERS_KEY, self.owner)) == self.instance

    async def start(self):
        """Claim the owner's registration, then start listening. A live owner is never displaced."""
        if self.owner:
            holder = _text(await self._redis("hget", OWNERS_KEY, self.owner))
            if holder not in (None, self.instance) and await self._listening(self.owner):
                logger.warning("Refused a second Redis channel for live agent %r", self.owner)
                raise ChannelOwnerCollisionError(f"agent {self.owner!r} already has a live Redis channel")
            await self._redis("hset", OWNERS_KEY, self.owner, self.instance)
        self.is_active = True
        self.listener_task = asyncio.create_task(self._listen_for_messages())
        await self.refresh()
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
                    message = StandardMessage.from_json(_text(message_json) or "")
                    await self.message_queue.put(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error listening for messages: %s", e)
                await asyncio.sleep(TimingConstants.STANDARD_DELAY)

    async def refresh(self) -> None:
        """Renew the owner's registration, and prune every registration past its TTL.

        Only while this channel's listener runs and it still owns the registration: a
        refresh for a dead listener would keep an inbox nobody reads looking live.
        """
        if not self.owner:
            return
        if self.listener_task is None or self.listener_task.done():
            logger.error("Redis channel %s has no running listener; not renewing %r", self.channel_id, self.owner)
            return
        if not await self._owns_registration():
            logger.warning("Redis channel %s no longer owns %r; not renewing it", self.channel_id, self.owner)
            return
        now = await self._now()
        await self._redis("zadd", REGISTERED_KEY, {self.owner: now})
        await self._redis("zremrangebyscore", REGISTERED_KEY, "-inf", now - REGISTRATION_TTL_SECONDS)

    async def recipients(self) -> Set[str]:
        """Every agent id whose Redis channel refreshed within the TTL."""
        cutoff = await self._now() - REGISTRATION_TTL_SECONDS
        members = await self._redis("zrangebyscore", REGISTERED_KEY, cutoff, "+inf")
        return {_text(m) for m in members or ()}

    async def send(self, message: StandardMessage) -> bool:
        """Push *message* onto its recipient's inbox, if that recipient is listening."""
        recipient = message.header.recipient
        try:
            if not await self._listening(recipient):
                logger.debug("Redis channel %s cannot reach recipient %r", self.channel_id, recipient)
                return False
            key = inbox_key(recipient)
            length = await self._redis("rpush", key, message.to_json())
            if length > INBOX_MAX_LENGTH:
                await self._redis("ltrim", key, -INBOX_MAX_LENGTH, -1)
                dropped = length - INBOX_MAX_LENGTH
                logger.warning("Inbox of %r over %d: dropped the %d oldest", recipient, INBOX_MAX_LENGTH, dropped)
            await self._redis("expire", key, INBOX_TTL_SECONDS)
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
        """Close the Redis communication channel, and withdraw its owner's registration if it is ours."""
        self.is_active = False
        if await self._owns_registration():
            await self._redis("zrem", REGISTERED_KEY, self.owner)
            await self._redis("hdel", OWNERS_KEY, self.owner)
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
        """Register this channel's queue as *owner*'s in-process inbox. A live owner is never displaced."""
        held = _DIRECT_INBOXES.get(owner)
        if held is not None and held is not self.message_queue:
            logger.warning("Refused a second direct channel for live agent %r", owner)
            raise ChannelOwnerCollisionError(f"agent {owner!r} already has a live direct channel")
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
        """Close the direct communication channel, and withdraw its owner's inbox if it is ours"""
        self.is_active = False
        if self.owner and _DIRECT_INBOXES.get(self.owner) is self.message_queue:
            del _DIRECT_INBOXES[self.owner]
        # Clear remaining messages
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
