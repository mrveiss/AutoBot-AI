# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The originator of a message survives every relay, and a peer's request keeps it (#16950)."""

from typing import List

import pytest

from agents.base_agent import AgentRequest, AgentResponse, LocalAgent
from protocols.agent_communication import (
    AgentCommunicationProtocol,
    AgentIdentity,
    CommunicationChannel,
    MessageHeader,
    MessagePayload,
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
