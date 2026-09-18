# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The originator of a message survives every relay, and a peer's request keeps it (#16950)."""

import asyncio
import contextvars
from typing import Dict, List

import pytest

from agents.base_agent import AgentRequest, AgentResponse, LocalAgent
from protocols.agent_communication import (
    AgentCommunicationProtocol,
    AgentIdentity,
    CommunicationChannel,
    MessageHeader,
    MessagePayload,
    MessageType,
    StandardMessage,
)
from protocols.message_origin import Origin, acting_for, current_origin, origin_of, stamp


def _header(**kwargs) -> MessageHeader:
    return MessageHeader(**kwargs)


class TestStamp:
    def test_the_first_send_starts_a_chain(self):
        header = _header()
        stamp(header, "agent_a")

        assert (header.originator, header.chain) == ("agent_a", ["agent_a"])

    def test_a_send_made_while_handling_a_request_keeps_its_originator(self):
        header = _header()
        with acting_for(Origin("agent_a", ("agent_a",))):
            stamp(header, "relay_b")

        assert (header.originator, header.chain) == ("agent_a", ["agent_a", "relay_b"])

    def test_a_header_that_already_names_an_originator_keeps_it(self):
        header = _header(originator="agent_a", chain=["agent_a"])
        with acting_for(Origin("someone_else", ("someone_else",))):
            stamp(header, "relay_b")

        assert header.originator == "agent_a"

    def test_a_resend_by_the_same_hop_is_not_counted_twice(self):
        header = _header()
        stamp(header, "agent_a")
        stamp(header, "agent_a")

        assert header.chain == ["agent_a"]

    def test_the_origin_does_not_outlive_the_work(self):
        with acting_for(Origin("agent_a", ("agent_a",))):
            pass

        assert current_origin() is None


class TestOriginOf:
    def test_a_header_names_its_originator(self):
        origin = origin_of(_header(originator="agent_a", chain=["agent_a", "relay_b"]))

        assert origin == Origin("agent_a", ("agent_a", "relay_b"))

    @pytest.mark.parametrize(
        "sender",
        [AgentIdentity(agent_id="old_agent", agent_type="t"), {"agent_id": "old_agent"}],
        ids=["local identity", "after a redis round trip"],
    )
    def test_a_header_from_before_this_field_is_its_senders(self, sender):
        """Never "nobody": the sender is the only principal known, so it is the originator."""
        assert origin_of(_header(sender=sender)) == Origin("old_agent", ("old_agent",))

    def test_a_header_naming_no_one_has_no_origin(self):
        assert origin_of(_header()) is None


def test_the_originator_survives_the_wire_format():
    """The Redis channel moves messages as JSON; the fields must come back out of it."""
    message = StandardMessage(
        header=_header(originator="agent_a", chain=["agent_a", "relay_b"]), payload=MessagePayload()
    )

    header = StandardMessage.from_json(message.to_json()).header

    assert (header.originator, header.chain) == ("agent_a", ["agent_a", "relay_b"])


class _Capture(CommunicationChannel):
    def __init__(self) -> None:
        super().__init__("capture")
        self.sent: List[StandardMessage] = []

    async def send(self, message: StandardMessage) -> bool:
        self.sent.append(message)
        return True

    async def receive(self, timeout=None):
        return None

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_send_message_stamps_the_hop():
    protocol = AgentCommunicationProtocol(AgentIdentity(agent_id="agent_a", agent_type="t"))
    channel = _Capture()
    protocol.add_channel("capture", channel)

    await protocol.send_message(StandardMessage(header=_header(), payload=MessagePayload()))

    assert (channel.sent[0].header.originator, channel.sent[0].header.chain) == ("agent_a", ["agent_a"])


class _Relay(LocalAgent):
    """Records the request it was given, and what a message sent while handling it would carry."""

    def __init__(self) -> None:
        super().__init__("relay_b")
        self.seen: AgentRequest | None = None
        self.onward = _header()

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        self.seen = request
        stamp(self.onward, "relay_b")
        return AgentResponse(request_id=request.request_id, agent_type=self.agent_type, status="success", result={})

    def get_capabilities(self) -> List[str]:
        return []


@pytest.mark.asyncio
async def test_a_peer_request_carries_its_originator_into_the_agent():
    """The handler used to drop the sender entirely, so a peer's request read as the agent's own."""
    agent = _Relay()
    inbound = StandardMessage(
        header=_header(
            sender=AgentIdentity(agent_id="agent_a", agent_type="t"), originator="agent_a", chain=["agent_a"]
        ),
        payload=MessagePayload(content={"action": "process", "payload": {}}),
    )

    await agent._handle_communication_request(inbound)

    assert (agent.seen.originator, agent.seen.chain) == ("agent_a", ["agent_a"])
    assert (agent.onward.originator, agent.onward.chain) == ("agent_a", ["agent_a", "relay_b"])
    assert current_origin() is None


class _Routed(CommunicationChannel):
    """Delivers each message to its ``recipient``'s protocol, over the JSON wire format.

    The real channels cannot do this yet: they put a message back on the sender's own
    queue or Redis key, and ``recipient`` is never read (#16986). This stand-in is the
    transport only. Sending, stamping, handling, the agent's request handler and the
    response correlation are all the production code. Each delivery runs in a fresh
    context, as a receiver's own poller task would, so no origin leaks from the sender.
    """

    def __init__(self, owner: str, protocols: Dict[str, AgentCommunicationProtocol]) -> None:
        super().__init__(f"{owner}_routed")
        self.protocols = protocols

    async def send(self, message: StandardMessage) -> bool:
        wire = StandardMessage.from_json(message.to_json())
        target = self.protocols[message.header.recipient]
        asyncio.get_running_loop().create_task(
            target._handle_message(wire, self.channel_id), context=contextvars.Context()
        )
        return True

    async def receive(self, timeout=None):
        return None

    async def close(self):
        return None


class _Hop(LocalAgent):
    """A peer that records what it was asked, and forwards to *onward* if it has one."""

    def __init__(self, agent_type: str, onward: str | None = None) -> None:
        super().__init__(agent_type)
        self.onward, self.seen, self.origin_while_handling = onward, None, None

    async def process_request(self, request: AgentRequest) -> AgentResponse:
        self.seen, self.origin_while_handling = request, current_origin()
        result = {"handled_by": self.agent_type}
        if self.onward:
            reply = await self.communication_protocol.send_request(_request_to(self.onward), timeout=5)
            result["onward_reply"] = reply.payload.content if reply else None
        return AgentResponse(request_id=request.request_id, agent_type=self.agent_type, status="success", result=result)

    def get_capabilities(self) -> List[str]:
        return []


def _request_to(recipient: str) -> StandardMessage:
    header = _header(message_type=MessageType.REQUEST, recipient=recipient)
    return StandardMessage(header=header, payload=MessagePayload(content={"action": "process", "payload": {}}))


def _wire(protocols: Dict[str, AgentCommunicationProtocol], agent_id: str, hop: _Hop | None = None) -> None:
    protocol = AgentCommunicationProtocol(AgentIdentity(agent_id=agent_id, agent_type="t"))
    protocol.add_channel(f"{agent_id}_routed", _Routed(agent_id, protocols))
    if hop is not None:
        hop.communication_protocol = protocol
        protocol.register_message_handler(MessageType.REQUEST, hop._handle_communication_request)
    protocols[agent_id] = protocol


@pytest.mark.asyncio
async def test_two_real_round_trips_carry_the_originator_to_the_last_hop():
    """c0's review of #16966: A asks B, and B, while handling it, asks C. Both replies come back.

    B's onward request is built with no originator at all. C must still see A, because B
    sent it while acting for A, and the chain must name every hop in order.
    """
    protocols: Dict[str, AgentCommunicationProtocol] = {}
    relay_b, agent_c = _Hop("relay_b", onward="agent_c"), _Hop("agent_c")
    _wire(protocols, "agent_a")
    _wire(protocols, "relay_b", relay_b)
    _wire(protocols, "agent_c", agent_c)

    reply = await protocols["agent_a"].send_request(_request_to("relay_b"), timeout=5)

    assert reply is not None and reply.header.message_type is MessageType.RESPONSE
    onward = reply.payload.content["result"]["onward_reply"]
    assert onward["status"] == "success" and onward["result"] == {"handled_by": "agent_c"}
    assert (relay_b.seen.originator, relay_b.seen.chain) == ("agent_a", ["agent_a"])
    assert (agent_c.seen.originator, agent_c.seen.chain) == ("agent_a", ["agent_a", "relay_b"])
    assert agent_c.origin_while_handling == Origin("agent_a", ("agent_a", "relay_b"))
    assert current_origin() is None
