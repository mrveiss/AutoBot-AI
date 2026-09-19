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
import sys
from types import ModuleType
from unittest.mock import patch

import fakeredis
import pytest

from autobot_shared.eventually import eventually
from protocols import agent_channels, agent_communication
from protocols.agent_channels import (
    _DIRECT_INBOXES,
    OWNERS_KEY,
    REGISTERED_KEY,
    REGISTRATION_TTL_SECONDS,
    ChannelOwnerCollisionError,
    DirectCommunicationChannel,
    RedisCommunicationChannel,
    inbox_key,
)
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
    client = lambda: fakeredis.FakeRedis(server=server, decode_responses=True)  # noqa: E731 -- as production's client
    with patch.object(agent_channels, "get_redis_client", client):
        yield client()


def _server_now(redis) -> float:
    seconds, micros = redis.time()
    return int(seconds) + int(micros) / 1_000_000


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
    redis_server.zadd(REGISTERED_KEY, {"agent_stale": _server_now(redis_server) - REGISTRATION_TTL_SECONDS - 1})
    channel = RedisCommunicationChannel("probe")
    channel.bind("agent_probe")

    assert await channel.send(_to("agent_stale")) is False
    assert "agent_stale" not in await channel.recipients()

    await channel.start()

    assert redis_server.zscore(REGISTERED_KEY, "agent_stale") is None
    assert redis_server.zscore(REGISTERED_KEY, "agent_probe") is not None
    await channel.close()


@pytest.mark.asyncio
async def test_a_flood_never_runs_more_handlers_than_the_bound_and_a_reply_is_never_held(redis_server, monkeypatch):
    """66's review of #17001: one task per message had no cap. It has one now, and a reply still gets through.

    B's handler blocks, so a flood of six requests saturates B's two slots. While B is
    saturated, B's own request to C must still get its reply: replies never wait for a slot.
    """
    monkeypatch.setattr(agent_communication, "MAX_INFLIGHT_HANDLERS", 2)
    manager, release, running, peak, done = AgentCommunicationManager(), asyncio.Event(), [0], [0], []

    async def slow(message):
        running[0] += 1
        peak[0] = max(peak[0], running[0])
        await release.wait()
        running[0] -= 1
        done.append(message.header.message_id)

    async def answer(message):
        return _to("", MessageType.RESPONSE, ok=True)

    protocols = {}
    for agent_id, handler in (("agent_a", None), ("agent_b", slow), ("agent_c", answer)):
        protocols[agent_id] = await manager.register_agent(
            AgentIdentity(agent_id=agent_id, agent_type="t"), [{"type": "direct"}]
        )
        if handler:
            protocols[agent_id].register_message_handler(MessageType.REQUEST, handler)
    try:
        for _ in range(6):
            assert await protocols["agent_a"].send_message(_to("agent_b"))
        await eventually(lambda: running[0] == 2)

        reply = await protocols["agent_b"].send_request(_to("agent_c"), timeout=5)

        assert reply is not None and reply.payload.content == {"ok": True}
        assert (running[0], peak[0]) == (2, 2)
        release.set()
        await eventually(lambda: len(done) == 6)
        assert (len(done), peak[0]) == (6, 2)
    finally:
        release.set()
        await manager.shutdown_all()


@pytest.mark.asyncio
async def test_an_inbox_is_capped_dropping_the_oldest_and_expires(redis_server, monkeypatch):
    """66's review of #17001: rpush had no LTRIM, and the expire branch never ran."""
    monkeypatch.setattr(agent_channels, "INBOX_MAX_LENGTH", 3)
    redis_server.zadd(REGISTERED_KEY, {"agent_x": _server_now(redis_server)})
    sender = RedisCommunicationChannel("sender")
    sender.bind("agent_s")

    for n in range(5):
        assert await sender.send(_to("agent_x", n=n))

    kept = [
        StandardMessage.from_json(raw).payload.content["n"] for raw in redis_server.lrange(inbox_key("agent_x"), 0, -1)
    ]
    assert kept == [2, 3, 4]
    assert redis_server.ttl(inbox_key("agent_x")) > 0


@pytest.mark.asyncio
async def test_a_second_live_redis_owner_is_refused_and_a_stale_one_cannot_withdraw_its_successor(redis_server):
    first, second, third = (RedisCommunicationChannel(f"c{n}") for n in range(3))
    for channel in (first, second, third):
        channel.bind("agent_x")
    await first.start()

    with pytest.raises(ChannelOwnerCollisionError):
        await second.start()

    redis_server.zadd(REGISTERED_KEY, {"agent_x": _server_now(redis_server) - REGISTRATION_TTL_SECONDS - 1})
    await third.start()  # the first has gone stale: the id can be taken over
    await first.close()

    assert redis_server.hget(OWNERS_KEY, "agent_x") == third.instance
    assert redis_server.zscore(REGISTERED_KEY, "agent_x") is not None
    await third.close()


def test_a_second_live_direct_owner_is_refused():
    first, second = DirectCommunicationChannel("d1"), DirectCommunicationChannel("d2")
    first.bind("agent_dup")
    try:
        with pytest.raises(ChannelOwnerCollisionError):
            second.bind("agent_dup")
        assert _DIRECT_INBOXES["agent_dup"] is first.message_queue
    finally:
        asyncio.run(first.close())


@pytest.mark.asyncio
async def test_a_refused_channel_leaves_nothing_bound(redis_server):
    """An agent whose Redis channel is refused must not keep a direct inbox that nothing reads."""
    live = RedisCommunicationChannel("live")
    live.bind("agent_x")
    await live.start()

    with pytest.raises(ChannelOwnerCollisionError):
        await AgentCommunicationManager().register_agent(
            AgentIdentity(agent_id="agent_x", agent_type="t"), [{"type": "direct"}, {"type": "redis"}]
        )

    assert "agent_x" not in _DIRECT_INBOXES
    await live.close()


@pytest.mark.asyncio
async def test_a_channel_whose_listener_died_stops_renewing(redis_server):
    """#17001 review: a refresh for a dead listener would keep an inbox nobody reads looking live."""
    channel = RedisCommunicationChannel("dying")
    channel.bind("agent_d")
    await channel.start()
    channel.listener_task.cancel()
    try:  # the listener ends quietly on cancel; a task cancelled before it ran raises instead
        await channel.listener_task
    except asyncio.CancelledError:
        pass
    assert channel.listener_task.done()
    stale = _server_now(redis_server) - REGISTRATION_TTL_SECONDS - 1
    redis_server.zadd(REGISTERED_KEY, {"agent_d": stale})

    await channel.refresh()

    assert redis_server.zscore(REGISTERED_KEY, "agent_d") == stale
    await channel.close()


@pytest.mark.asyncio
async def test_two_channels_racing_for_one_id_cannot_both_win(redis_server):
    """66's review of #17001: the claim was a get then a set. It is one script now."""
    first, second = RedisCommunicationChannel("r1"), RedisCommunicationChannel("r2")
    first.bind("agent_race")
    second.bind("agent_race")

    outcomes = await asyncio.gather(first.start(), second.start(), return_exceptions=True)

    refused = [o for o in outcomes if isinstance(o, ChannelOwnerCollisionError)]
    winner = first if outcomes[0] is None else second
    assert len(refused) == 1 and outcomes.count(None) == 1, outcomes
    assert redis_server.hget(OWNERS_KEY, "agent_race") == winner.instance
    await winner.close()


@pytest.mark.asyncio
async def test_a_channel_that_lost_its_id_stops_reading_the_inbox(redis_server):
    """A stale channel taken over must not keep a listener splitting its successor's inbox."""
    stale, successor = RedisCommunicationChannel("old"), RedisCommunicationChannel("new")
    stale.bind("agent_y")
    successor.bind("agent_y")
    await stale.start()
    redis_server.zadd(REGISTERED_KEY, {"agent_y": _server_now(redis_server) - REGISTRATION_TTL_SECONDS - 1})
    await successor.start()

    await stale.refresh()

    assert not stale.is_active
    try:  # its listener was cancelled: wait for it to wind down
        await stale.listener_task
    except asyncio.CancelledError:
        pass
    assert stale.listener_task.done()
    assert redis_server.hget(OWNERS_KEY, "agent_y") == successor.instance
    await stale.close()
    await successor.close()


@pytest.mark.asyncio
async def test_a_dropped_request_is_answered_with_an_error_at_once(redis_server, monkeypatch):
    """66's review of #17001: a shed request used to leave its requester waiting out the whole timeout."""
    monkeypatch.setattr(agent_communication, "MAX_INFLIGHT_HANDLERS", 1)
    monkeypatch.setattr(agent_communication, "INBOX_MAX_LENGTH", 1)
    manager, release = AgentCommunicationManager(), asyncio.Event()

    async def slow(message):
        await release.wait()

    a = await manager.register_agent(AgentIdentity(agent_id="agent_a", agent_type="t"), [{"type": "direct"}])
    b = await manager.register_agent(AgentIdentity(agent_id="agent_b", agent_type="t"), [{"type": "direct"}])
    b.register_message_handler(MessageType.REQUEST, slow)
    try:
        for _ in range(2):  # one handling, one queued
            assert await a.send_message(_to("agent_b"))
        await eventually(lambda: len(b._handling) == 1 and len(b._backlog) == 1)
        started = asyncio.get_running_loop().time()

        reply = await a.send_request(_to("agent_b"), timeout=5)

        assert reply is not None and reply.payload.content == {"error": "Agent overloaded", "error_type": "Overloaded"}
        assert asyncio.get_running_loop().time() - started < 2, "the requester waited instead of hearing no"
    finally:
        release.set()
        await manager.shutdown_all()


@pytest.mark.asyncio
async def test_a_peer_request_is_held_to_the_work_claims_like_any_other(redis_server, monkeypatch):
    """#17001 review (High): the peer path skipped execute_with_tracking, and with it hold_scopes.

    A scope another run holds must refuse a peer's request for it, and the refusal must
    reach the requester over the wire.
    """
    import fakeredis.aioredis as fakeredis_async

    from agents.base_agent import AgentRequest, AgentResponse, LocalAgent
    from autobot_shared.coordination import work_claims

    claims = fakeredis_async.FakeRedis(server=fakeredis_async.FakeServer(), decode_responses=True)

    async def _claims_client(database: str = "main"):
        return claims

    monkeypatch.setattr(work_claims, "get_async_redis_client", _claims_client)
    analytics = ModuleType("services.agent_analytics")
    analytics.get_agent_analytics = lambda: (_ for _ in ()).throw(RuntimeError("no analytics in this test"))
    monkeypatch.setitem(sys.modules, "services.agent_analytics", analytics)

    class _Writer(LocalAgent):
        def declared_scopes(self, request: AgentRequest):
            return ["path:shared/file.py"]

        async def process_request(self, request: AgentRequest) -> AgentResponse:
            return AgentResponse(request_id=request.request_id, agent_type=self.agent_type, status="success", result={})

        def get_capabilities(self):
            return []

    await work_claims.try_acquire("path:shared/file.py", agent_id="someone_else", task_id="t0", intent="editing")
    manager, writer = AgentCommunicationManager(), _Writer("writer")
    a = await manager.register_agent(AgentIdentity(agent_id="agent_a", agent_type="t"), [{"type": "direct"}])
    w = await manager.register_agent(AgentIdentity(agent_id="agent_w", agent_type="t"), [{"type": "direct"}])
    w.register_message_handler(MessageType.REQUEST, writer._handle_communication_request)
    try:
        reply = await a.send_request(_to("agent_w", action="write", payload={}), timeout=5)

        assert reply is not None
        assert reply.payload.content["status"] == "refused", reply.payload.content
        assert "someone_else" in reply.payload.content["error"]
    finally:
        await manager.shutdown_all()
