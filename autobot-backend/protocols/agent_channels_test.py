# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A peer message reaches its recipient, over the real direct and Redis channels (#16986).

Both channels used to deliver to the sender: a request an agent sent was handled by
the sender's own handler, which then answered itself. Every test here runs three
agents registered through the real ``AgentCommunicationManager``, once over the
direct channel and once over the Redis channel (on fakeredis), with only that one
channel kind, so delivery has to go through it.
"""

import asyncio
import time
from unittest.mock import patch

import fakeredis
import pytest

from protocols import agent_channels
from protocols.agent_channels import REGISTERED_KEY, REGISTRATION_TTL_SECONDS, RedisCommunicationChannel
from protocols.agent_communication import (
    AgentCommunicationManager,
    AgentIdentity,
    MessageHeader,
    MessagePayload,
    MessageType,
    StandardMessage,
)

KINDS = ["direct", "redis"]
AGENTS = ("agent_a", "agent_b", "agent_c")


@pytest.fixture
def redis_server():
    """Every Redis channel in the test talks to one fake server, as agents share one Redis."""
    server = fakeredis.FakeServer()
    with patch.object(agent_channels, "get_redis_client", lambda: fakeredis.FakeRedis(server=server)):
        yield fakeredis.FakeRedis(server=server)


def _to(recipient: str, message_type: MessageType = MessageType.REQUEST, **content) -> StandardMessage:
    return StandardMessage(
        header=MessageHeader(message_type=message_type, recipient=recipient), payload=MessagePayload(content=content)
    )


class _Mesh:
    """Three registered agents. B answers a request by forwarding it to C. Records who handled what."""

    def __init__(self, kind: str) -> None:
        self.kind, self.manager, self.handled = kind, AgentCommunicationManager(), []

    async def __aenter__(self) -> "_Mesh":
        for agent_id in AGENTS:
            identity = AgentIdentity(agent_id=agent_id, agent_type="t")
            protocol = await self.manager.register_agent(
                identity, [{"type": self.kind, "id": f"{agent_id}_{self.kind}"}]
            )
            protocol.register_message_handler(MessageType.REQUEST, self._on_request(agent_id))
            protocol.register_message_handler(MessageType.BROADCAST, self._on_broadcast(agent_id))
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.manager.shutdown_all()

    def protocol(self, agent_id: str):
        return self.manager.get_protocol(agent_id)

    def _on_request(self, agent_id: str):
        async def handle(message: StandardMessage) -> StandardMessage:
            self.handled.append(("request", agent_id))
            content = {"handled_by": agent_id}
            if agent_id == "agent_b":
                reply = await self.protocol("agent_b").send_request(_to("agent_c"), timeout=5)
                content["onward"] = reply.payload.content if reply else None
            return _to("", MessageType.RESPONSE, **content)

        return handle

    def _on_broadcast(self, agent_id: str):
        async def handle(message: StandardMessage) -> None:
            self.handled.append(("broadcast", agent_id))

        return handle

    async def settle(self, count: int, kind: str) -> list:
        """Wait until *count* messages of *kind* were handled, then a little longer for any extra."""
        for _ in range(300):
            if sum(1 for k, _a in self.handled if k == kind) >= count:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.2)
        return sorted(a for k, a in self.handled if k == kind)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
async def test_a_request_reaches_its_recipient_and_a_forwarded_request_gets_its_reply(kind, redis_server):
    """A asks B; B, while handling it, asks C. Both replies come back, and A never handles its own request."""
    async with _Mesh(kind) as mesh:
        reply = await mesh.protocol("agent_a").send_request(_to("agent_b"), timeout=5)

        assert reply is not None, "A's request never came back"
        assert reply.payload.content == {"handled_by": "agent_b", "onward": {"handled_by": "agent_c"}}
        assert [a for k, a in mesh.handled if k == "request"] == ["agent_b", "agent_c"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
async def test_a_broadcast_reaches_every_other_agent_and_never_the_sender(kind, redis_server):
    async with _Mesh(kind) as mesh:
        sent = await mesh.protocol("agent_a").broadcast(_to("", MessageType.BROADCAST, note="hello"))

        assert sent == 2
        assert await mesh.settle(2, "broadcast") == ["agent_b", "agent_c"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
async def test_a_message_to_an_agent_nobody_listens_for_is_refused(kind, redis_server):
    """Neither an unknown id nor an agent that has left is delivered to."""
    async with _Mesh(kind) as mesh:
        assert await mesh.protocol("agent_a").send_message(_to("agent_ghost")) is False

        await mesh.manager.unregister_agent("agent_c")

        assert await mesh.protocol("agent_a").send_message(_to("agent_c")) is False
        assert await mesh.protocol("agent_a").broadcast(_to("", MessageType.BROADCAST)) == 1


@pytest.mark.asyncio
async def test_an_agent_drops_a_message_addressed_to_someone_else(redis_server):
    """The receiving end holds the line too: a misdelivered message is never handled."""
    async with _Mesh("direct") as mesh:
        await mesh.protocol("agent_c")._handle_message(_to("agent_b"), "agent_c_direct")

        assert mesh.handled == []


@pytest.mark.asyncio
async def test_a_redis_registration_past_its_ttl_is_unreachable_and_pruned(redis_server):
    """An agent that died without closing its channel stops being a destination."""
    redis_server.zadd(REGISTERED_KEY, {"agent_stale": time.time() - REGISTRATION_TTL_SECONDS - 1})
    channel = RedisCommunicationChannel("probe")
    channel.bind("agent_probe")

    assert await channel.send(_to("agent_stale")) is False
    assert "agent_stale" not in await channel.recipients()

    await channel.refresh()

    assert redis_server.zscore(REGISTERED_KEY, "agent_stale") is None
    assert redis_server.zscore(REGISTERED_KEY, "agent_probe") is not None
