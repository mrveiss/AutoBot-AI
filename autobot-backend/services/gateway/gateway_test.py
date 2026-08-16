# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Wiring tests for the ingest governance stage (#14028) on the channel-adapter
Gateway stack — ``Gateway.receive_message``.

This is the *second* ingest seam identified while triaging #14028 (the other
is ``GatewayManager.normalize_message``, covered in ``tests/test_gateway_manager.py``).
Currently disabled at application startup (initialization/lifespan.py, #881 —
"testing event loop deadlock"), so it carries no live traffic today, but the
guard must still be wired here rather than left ungoverned for when it is
re-enabled.
"""

from typing import Any, Dict

import pytest

from services.gateway.channel_adapters.base import BaseChannelAdapter
from services.gateway.config import GatewayConfig
from services.gateway.gateway import Gateway
from services.gateway.types import ChannelMessage, ChannelType, GatewaySession, MessageType


class _FakeChannelAdapter(BaseChannelAdapter):
    """Builds a ChannelMessage straight from a raw dict — no real transport."""

    def __init__(self) -> None:
        super().__init__(ChannelType.WEBSOCKET)

    async def send_message(self, message, session, connection_context=None) -> bool:
        return True

    async def receive_message(self, raw_data: Dict[str, Any], session: GatewaySession):
        return ChannelMessage(
            message_id=raw_data.get("message_id", "generated"),
            session_id=session.session_id,
            channel=self.channel_type,
            message_type=MessageType.USER_TEXT,
            content=raw_data.get("content", ""),
            metadata=raw_data.get("metadata", {}),
        )

    async def connect(self, session, connection_params):
        return object()

    async def disconnect(self, session, connection_context=None) -> None:
        return None

    async def handle_heartbeat(self, session, connection_context=None) -> bool:
        return True


@pytest.fixture(autouse=True)
def _reset_gateway_singleton():
    """Gateway.__new__ is a process-wide singleton (double-checked lock, #11637);
    reset it around each test so state doesn't leak across tests/modules."""
    Gateway._instance = None
    yield
    Gateway._instance = None


@pytest.fixture
def fake_redis(monkeypatch):
    from services.gateway import ingest_governor as governor_module

    store: dict = {}

    class _FakeAsyncRedis:
        async def set(self, key, value, nx=False, ex=None):
            if nx and key in store:
                return None
            store[key] = value
            return True

        async def get(self, key):
            return store.get(key)

        async def incr(self, key):
            value = int(store.get(key) or 0) + 1
            store[key] = str(value)
            return value

        async def expire(self, key, seconds):
            return key in store

    async def _get(*_a, **_k):
        return _FakeAsyncRedis()

    monkeypatch.setattr(governor_module, "get_async_redis_client", _get)
    return store


async def _build_gateway_with_session(user_id: str = "u1") -> tuple[Gateway, GatewaySession]:
    gateway = Gateway(config=GatewayConfig())
    gateway.register_channel_adapter(ChannelType.WEBSOCKET, _FakeChannelAdapter())
    session = await gateway.session_manager.create_session(user_id=user_id, channel=ChannelType.WEBSOCKET)
    return gateway, session


class TestChannelAdapterIngestGovernance:
    """#14028 governance applied at the channel_adapters seam, asserted
    separately from the platform-adapter seam per the corrected acceptance
    criteria (two disjoint ingest stacks, see issue #14028 comment history)."""

    @pytest.mark.asyncio
    async def test_governance_stage_actually_runs(self, fake_redis, monkeypatch):
        """Wraps the real evaluate() with a spy and drives receive_message for
        real — not a source-text substring check (#14028)."""
        from services.gateway import ingest_governor as governor_module

        real_evaluate = governor_module.ingest_governor.evaluate
        calls = []

        async def _spy(**kwargs):
            calls.append(kwargs)
            return await real_evaluate(**kwargs)

        monkeypatch.setattr(governor_module.ingest_governor, "evaluate", _spy)

        gateway, session = await _build_gateway_with_session()
        message = await gateway.receive_message({"message_id": "wire-1", "content": "hi"}, session.session_id)

        assert message is not None
        assert len(calls) == 1
        assert calls[0]["message_id"] == "wire-1"
        assert calls[0]["author_id"] == session.user_id

    @pytest.mark.asyncio
    async def test_bot_self_authored_message_dropped(self, fake_redis, monkeypatch):
        monkeypatch.setenv("AUTOBOT_GATEWAY_BOT_ID_WEBSOCKET", "u-bot")
        gateway, session = await _build_gateway_with_session(user_id="u-bot")

        result = await gateway.receive_message({"message_id": "self-1", "content": "echo"}, session.session_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_duplicate_message_id_produces_one_pass_through(self, fake_redis):
        gateway, session = await _build_gateway_with_session()

        first = await gateway.receive_message({"message_id": "dup-ws-1", "content": "hi"}, session.session_id)
        second = await gateway.receive_message({"message_id": "dup-ws-1", "content": "hi"}, session.session_id)

        assert first is not None
        assert second is None

    @pytest.mark.asyncio
    async def test_chain_over_recursion_ceiling_halted(self, fake_redis):
        """The recursion counter is server-side Redis state keyed on
        (platform, channel) -- not a payload field, since no platform
        round-trips one (#14028 review correction)."""
        from services.gateway.ingest_governor import INGEST_MAX_CHAIN_DEPTH, ingest_governor

        gateway, session = await _build_gateway_with_session()
        for _ in range(INGEST_MAX_CHAIN_DEPTH + 1):
            await ingest_governor.record_agent_send(platform=session.channel.value, channel_id=session.session_id)

        result = await gateway.receive_message({"message_id": "chain-ws-1", "content": "forwarded"}, session.session_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_send_message_records_agent_send_for_recursion_tracking(self, fake_redis):
        """Wiring assertion for the send side: an AGENT_TEXT ``send_message``
        call must increment the same counter ``receive_message`` reads
        (#14028) -- drives the real seam, not a source-text check."""
        from services.gateway.ingest_governor import INGEST_MAX_CHAIN_DEPTH
        from services.gateway.types import ChannelMessage, MessageType

        gateway, session = await _build_gateway_with_session()

        for i in range(INGEST_MAX_CHAIN_DEPTH + 1):
            reply = ChannelMessage(
                session_id=session.session_id,
                channel=session.channel,
                message_type=MessageType.AGENT_TEXT,
                content=f"agent reply {i}",
            )
            sent = await gateway.send_message(reply)
            assert sent is True

        result = await gateway.receive_message({"message_id": "post-loop-1", "content": "hi"}, session.session_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_normal_message_still_routes(self, fake_redis):
        gateway, session = await _build_gateway_with_session()

        result = await gateway.receive_message({"message_id": "normal-ws-1", "content": "hello"}, session.session_id)

        assert result is not None
        assert result.content == "hello"


class TestEgressGovernanceIsWiredAtTheSharedSeam:
    """#14067: outbound sends crossed no approval seam and left no record.

    These drive `Gateway.send_message` for real. The governor's own unit tests
    all stay green if the seam is never called, which is exactly the failure
    mode these exist to catch.
    """

    @pytest.mark.asyncio
    async def test_the_egress_stage_actually_runs_on_an_agent_send(self, fake_redis, monkeypatch):
        from services.gateway import egress_governor as governor_module
        from services.gateway.types import ChannelMessage, MessageType

        calls = []
        real_evaluate = governor_module.egress_governor.evaluate

        async def _spy(**kwargs):
            calls.append(kwargs)
            return await real_evaluate(**kwargs)

        monkeypatch.setattr(governor_module.egress_governor, "evaluate", _spy)

        gateway, session = await _build_gateway_with_session()
        reply = ChannelMessage(
            message_id="egress-1",
            session_id=session.session_id,
            channel=session.channel,
            message_type=MessageType.AGENT_TEXT,
            content="a reply to a real person",
        )
        assert await gateway.send_message(reply) is True
        assert len(calls) == 1
        assert calls[0]["message_id"] == "egress-1"

    @pytest.mark.asyncio
    async def test_a_denied_send_never_reaches_the_adapter(self, fake_redis, monkeypatch):
        """The property that matters: blocked at the seam, not merely reported."""
        from services.gateway import egress_governor as governor_module
        from services.gateway.egress_governor import EgressVerdict
        from services.gateway.types import ChannelMessage, MessageType

        gateway, session = await _build_gateway_with_session()
        adapter = gateway._channel_adapters[ChannelType.WEBSOCKET]
        delivered = []

        async def _spy_send(message, session_, connection_context=None):
            delivered.append(message)
            return True

        monkeypatch.setattr(adapter, "send_message", _spy_send)

        async def _deny(**_kwargs):
            return EgressVerdict(allowed=False, reason="denied by test", rule="approver")

        monkeypatch.setattr(governor_module.egress_governor, "evaluate", _deny)

        reply = ChannelMessage(
            session_id=session.session_id,
            channel=session.channel,
            message_type=MessageType.AGENT_TEXT,
            content="must not be sent",
        )
        assert await gateway.send_message(reply) is False
        assert delivered == [], "a denied message was handed to the adapter anyway"

    @pytest.mark.asyncio
    async def test_an_approved_send_reaches_the_adapter_unchanged(self, fake_redis, monkeypatch):
        from services.gateway.types import ChannelMessage, MessageType

        gateway, session = await _build_gateway_with_session()
        adapter = gateway._channel_adapters[ChannelType.WEBSOCKET]
        delivered = []

        async def _spy_send(message, session_, connection_context=None):
            delivered.append(message)
            return True

        monkeypatch.setattr(adapter, "send_message", _spy_send)

        reply = ChannelMessage(
            session_id=session.session_id,
            channel=session.channel,
            message_type=MessageType.AGENT_TEXT,
            content="allowed content",
        )
        assert await gateway.send_message(reply) is True
        assert [m.content for m in delivered] == ["allowed content"]

    @pytest.mark.asyncio
    async def test_a_newly_added_adapter_inherits_the_gate_with_no_adapter_change(self, fake_redis, monkeypatch):
        """The structural claim, asserted rather than asserted-about.

        A brand-new adapter subclass with no knowledge of egress governance must
        still be gated, because the stage lives at the Gateway seam.
        """
        from services.gateway import egress_governor as governor_module
        from services.gateway.egress_governor import EgressVerdict
        from services.gateway.types import ChannelMessage, MessageType

        class _BrandNewAdapter(_FakeChannelAdapter):
            def __init__(self) -> None:
                super().__init__()
                self.delivered = []

            async def send_message(self, message, session, connection_context=None) -> bool:
                self.delivered.append(message)
                return True

        gateway = Gateway(config=GatewayConfig())
        adapter = _BrandNewAdapter()
        gateway.register_channel_adapter(ChannelType.WEBSOCKET, adapter)
        session = await gateway.session_manager.create_session(user_id="u2", channel=ChannelType.WEBSOCKET)

        async def _deny(**_kwargs):
            return EgressVerdict(allowed=False, reason="denied by test", rule="approver")

        monkeypatch.setattr(governor_module.egress_governor, "evaluate", _deny)

        reply = ChannelMessage(
            session_id=session.session_id,
            channel=session.channel,
            message_type=MessageType.AGENT_TEXT,
            content="new adapter, same gate",
        )
        assert await gateway.send_message(reply) is False
        assert adapter.delivered == []

    @pytest.mark.asyncio
    async def test_session_control_traffic_is_not_governed(self, fake_redis, monkeypatch):
        """Heartbeats and lifecycle events are not messages to a person."""
        from services.gateway import egress_governor as governor_module
        from services.gateway.types import ChannelMessage, MessageType

        calls = []

        async def _spy(**kwargs):
            calls.append(kwargs)
            from services.gateway.egress_governor import EgressVerdict

            return EgressVerdict(allowed=True)

        monkeypatch.setattr(governor_module.egress_governor, "evaluate", _spy)

        gateway, session = await _build_gateway_with_session()
        control = ChannelMessage(
            session_id=session.session_id,
            channel=session.channel,
            message_type=MessageType.SESSION_START,
            content="",
        )
        await gateway.send_message(control)
        assert calls == []
