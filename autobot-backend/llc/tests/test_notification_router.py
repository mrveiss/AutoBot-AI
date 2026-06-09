# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for LLC notification router (GH#8255)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from llc.notifications.publisher import LLCWebSocketPublisher
from llc.notifications.router import LLCNotificationRouter


class _FakePublisher:
    def __init__(self):
        self.calls: list[dict] = []

    async def publish(self, company_id, event_type, entity_type, entity_id, payload, actor_id=None):
        self.calls.append(
            dict(
                company_id=company_id,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload,
                actor_id=actor_id,
            )
        )


@pytest.mark.asyncio
async def test_dispatch_routes_to_publisher():
    pub = _FakePublisher()
    router = LLCNotificationRouter(publisher=pub)

    msg = {
        "type": "pmessage",
        "channel": b"llc:budget:warning",
        "data": json.dumps(
            {
                "event_type": "budget_warning_80",
                "company_id": "company-abc",
                "entity_type": "budget",
                "entity_id": "budget-1",
                "payload": {"threshold": 80},
            }
        ).encode(),
    }
    await router._dispatch(msg)

    assert len(pub.calls) == 1
    assert pub.calls[0]["company_id"] == "company-abc"
    assert pub.calls[0]["event_type"] == "budget_warning_80"
    assert pub.calls[0]["payload"] == {"threshold": 80}


@pytest.mark.asyncio
async def test_dispatch_skips_missing_company_id():
    pub = _FakePublisher()
    router = LLCNotificationRouter(publisher=pub)

    msg = {
        "type": "pmessage",
        "channel": b"llc:agent:paused",
        "data": json.dumps({"event_type": "agent_paused", "entity_type": "agent", "entity_id": "a1"}).encode(),
    }
    await router._dispatch(msg)
    assert pub.calls == []


@pytest.mark.asyncio
async def test_dispatch_ignores_non_message_types():
    pub = _FakePublisher()
    router = LLCNotificationRouter(publisher=pub)

    msg = {"type": "subscribe", "channel": b"llc:budget:*", "data": 1}
    await router._dispatch(msg)
    assert pub.calls == []


@pytest.mark.asyncio
async def test_dispatch_handles_invalid_json():
    pub = _FakePublisher()
    router = LLCNotificationRouter(publisher=pub)

    msg = {"type": "pmessage", "channel": b"llc:budget:*", "data": b"not-json"}
    await router._dispatch(msg)
    assert pub.calls == []


@pytest.mark.asyncio
async def test_start_stop_lifecycle():
    pub = _FakePublisher()
    router = LLCNotificationRouter(publisher=pub)

    async def _fake_subscribe_loop():
        await asyncio.sleep(10)

    with patch.object(router, "_subscribe_loop", side_effect=_fake_subscribe_loop):
        await router.start()
        assert router._task and not router._task.done()
        await router.stop()
        assert router._task.done()


@pytest.mark.asyncio
async def test_start_is_idempotent():
    pub = _FakePublisher()
    router = LLCNotificationRouter(publisher=pub)

    async def _sleep():
        await asyncio.sleep(10)

    with patch.object(router, "_subscribe_loop", side_effect=_sleep):
        await router.start()
        task_before = router._task
        await router.start()
        assert router._task is task_before
        await router.stop()


@pytest.mark.asyncio
async def test_reconnects_on_redis_failure():
    pub = _FakePublisher()
    router = LLCNotificationRouter(publisher=pub)
    call_count = 0

    async def _flaky_subscribe():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("redis down")
        router._stop_event.set()

    with patch.object(router, "_subscribe_loop", side_effect=_flaky_subscribe):
        with patch("llc.notifications.router._RECONNECT_DELAY", 0):
            await router.start()
            await asyncio.wait_for(router._task, timeout=2)

    assert call_count == 3


@pytest.mark.asyncio
async def test_publisher_pushes_to_live_event_manager():
    pub = LLCWebSocketPublisher()
    mock_lem = AsyncMock()
    mock_em = AsyncMock()

    import llc.notifications.publisher as pub_mod

    orig_lem = pub_mod.get_live_event_manager
    orig_em = pub_mod.get_event_manager
    pub_mod.get_live_event_manager = lambda: mock_lem  # type: ignore[assignment]
    pub_mod.get_event_manager = lambda: mock_em  # type: ignore[assignment]
    try:
        await pub.publish(
            company_id="c1",
            event_type="agent_paused",
            entity_type="agent",
            entity_id="a1",
            payload={"reason": "budget"},
        )
    finally:
        pub_mod.get_live_event_manager = orig_lem  # type: ignore[assignment]
        pub_mod.get_event_manager = orig_em  # type: ignore[assignment]

    mock_lem.publish.assert_awaited_once()
    call_args = mock_lem.publish.call_args
    assert call_args[0][0] == "company:c1"
    assert call_args[0][1] == "agent_paused"
    envelope = call_args[0][2]
    assert envelope["company_id"] == "c1"
    assert envelope["entity_id"] == "a1"


@pytest.mark.asyncio
async def test_publisher_survives_live_event_manager_failure():
    pub = LLCWebSocketPublisher()
    mock_lem = AsyncMock()
    mock_lem.publish.side_effect = RuntimeError("lem down")
    mock_em = AsyncMock()

    import llc.notifications.publisher as pub_mod

    orig_lem = pub_mod.get_live_event_manager
    orig_em = pub_mod.get_event_manager
    pub_mod.get_live_event_manager = lambda: mock_lem  # type: ignore[assignment]
    pub_mod.get_event_manager = lambda: mock_em  # type: ignore[assignment]
    try:
        await pub.publish(
            company_id="c1",
            event_type="budget_exhausted",
            entity_type="budget",
            entity_id="b1",
            payload={},
        )
    finally:
        pub_mod.get_live_event_manager = orig_lem  # type: ignore[assignment]
        pub_mod.get_event_manager = orig_em  # type: ignore[assignment]

    mock_em.publish_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_integration_publish_then_dispatch():
    """Publish event through router dispatch and verify publisher receives it."""
    pub = _FakePublisher()
    router = LLCNotificationRouter(publisher=pub)

    event_data = {
        "event_type": "approval_created",
        "company_id": "co-xyz",
        "entity_type": "approval",
        "entity_id": "appr-1",
        "payload": {"title": "Hire engineer"},
        "actor_id": "agent-ceo",
    }
    msg = {
        "type": "pmessage",
        "channel": b"llc:approval:created",
        "data": json.dumps(event_data).encode(),
    }
    await router._dispatch(msg)

    assert pub.calls[0]["company_id"] == "co-xyz"
    assert pub.calls[0]["actor_id"] == "agent-ceo"
    assert pub.calls[0]["payload"] == {"title": "Hire engineer"}
