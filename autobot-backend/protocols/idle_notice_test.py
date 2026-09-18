#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the one-shot idle notice (#16949).

Drives `notify_agent_idle`/`wait_for_idle` through the real `EventBus` (no
mocking of it) -- the nested `{"type", "payload"}` wrapping that
`EventManager.publish` applies is exactly the thing a mock would have
hidden, and is what #16949's own implementation got wrong on the first pass.
"""

import asyncio

import pytest

from protocols.agent_kind import AgentKind
from protocols.agent_presence import AgentPresenceRegistry
from protocols.idle_notice import IdleWaitExpiredError, notify_agent_idle, wait_for_idle


def _registry(ttl: float = 60.0) -> AgentPresenceRegistry:
    return AgentPresenceRegistry(ttl_seconds=ttl)


class TestWaitForIdle:
    async def test_an_already_idle_peer_resolves_without_subscribing(self):
        reg = _registry()
        reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="i1", busy=False)

        await asyncio.wait_for(
            wait_for_idle(reg, kind=AgentKind.AI_STACK, tenant_id=None, name="rag", timeout_seconds=1),
            timeout=1,
        )

    async def test_a_busy_to_idle_transition_resolves_the_wait(self):
        reg = _registry()
        reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="i1", busy=True)

        async def _flip_after_a_beat() -> None:
            await asyncio.sleep(0.05)
            reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="i1", busy=False)

        asyncio.ensure_future(_flip_after_a_beat())

        await asyncio.wait_for(
            wait_for_idle(reg, kind=AgentKind.AI_STACK, tenant_id=None, name="rag", timeout_seconds=2),
            timeout=2,
        )

    async def test_a_peer_that_never_goes_idle_raises_on_timeout(self):
        reg = _registry()
        reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="i1", busy=True)

        with pytest.raises(IdleWaitExpiredError):
            await wait_for_idle(reg, kind=AgentKind.AI_STACK, tenant_id=None, name="rag", timeout_seconds=0.1)

    async def test_a_mismatched_transition_does_not_resolve_a_different_waiter(self):
        """Only the exact (kind, tenant_id, name) match may resolve the wait."""
        reg = _registry()
        reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="i1", busy=True)
        reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="other", instance_id="i2", busy=True)
        reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="other", instance_id="i2", busy=False)

        with pytest.raises(IdleWaitExpiredError):
            await wait_for_idle(reg, kind=AgentKind.AI_STACK, tenant_id=None, name="rag", timeout_seconds=0.1)

    async def test_the_subscription_is_unsubscribed_after_a_transition_resolves_it(self, monkeypatch):
        """No leaked listener on the subscribed (busy-now) path either."""
        reg = _registry()
        reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="i1", busy=True)

        from events.bus import get_event_bus

        bus = get_event_bus()
        calls = []
        original_unsubscribe = bus.unsubscribe
        monkeypatch.setattr(bus, "unsubscribe", lambda *a, **k: (calls.append(1), original_unsubscribe(*a, **k))[1])

        async def _flip_after_a_beat() -> None:
            await asyncio.sleep(0.05)
            reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="i1", busy=False)

        asyncio.ensure_future(_flip_after_a_beat())
        await wait_for_idle(reg, kind=AgentKind.AI_STACK, tenant_id=None, name="rag", timeout_seconds=2)

        assert calls == [1]

    async def test_the_subscription_is_unsubscribed_after_a_timeout(self, monkeypatch):
        reg = _registry()
        reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="i1", busy=True)

        from events.bus import get_event_bus

        bus = get_event_bus()
        calls = []
        original_unsubscribe = bus.unsubscribe
        monkeypatch.setattr(bus, "unsubscribe", lambda *a, **k: (calls.append(1), original_unsubscribe(*a, **k))[1])

        with pytest.raises(IdleWaitExpiredError):
            await wait_for_idle(reg, kind=AgentKind.AI_STACK, tenant_id=None, name="rag", timeout_seconds=0.1)

        assert calls == [1]


class TestNotifyAgentIdle:
    async def test_reporting_busy_then_idle_fires_exactly_one_notice(self):
        reg = _registry()
        reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="i1", busy=True)

        received = []

        async def _listener(event_data: dict) -> None:
            received.append(event_data["payload"])

        from events.bus import get_event_bus
        from protocols.idle_notice import EVT_AGENT_IDLE

        bus = get_event_bus()
        bus.subscribe(EVT_AGENT_IDLE, _listener)
        try:
            reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="i1", busy=False)
            await asyncio.sleep(0.05)
        finally:
            bus.unsubscribe(EVT_AGENT_IDLE, _listener)

        assert len(received) == 1
        assert received[0]["name"] == "rag"

    async def test_an_already_idle_first_report_fires_no_notice(self):
        """A first report that starts idle is "already free", not a transition."""
        reg = _registry()
        received = []

        async def _listener(event_data: dict) -> None:
            received.append(event_data)

        from events.bus import get_event_bus
        from protocols.idle_notice import EVT_AGENT_IDLE

        bus = get_event_bus()
        bus.subscribe(EVT_AGENT_IDLE, _listener)
        try:
            reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="i1", busy=False)
            await asyncio.sleep(0.05)
        finally:
            bus.unsubscribe(EVT_AGENT_IDLE, _listener)

        assert received == []

    def test_notify_with_no_running_loop_is_a_safe_noop(self):
        """A sync caller (e.g. a unit test calling report() directly outside
        an event loop) must not raise -- there is nothing to schedule onto."""
        notify_agent_idle(kind=AgentKind.AI_STACK, tenant_id=None, name="rag")
