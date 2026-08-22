# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
EventBus routing after the socket consolidation (#14816, #14822).

Two properties are load-bearing for the frontend's move onto a single socket:

* ``PersistStrategy.NONE`` must still reach WebSocket clients.  It did before —
  through the single global broadcast slot inside ``EventManager`` — so if it
  did not also reach the channel, migrating the frontend to ``/ws/live`` would
  silently drop workflow, chain-of-thought and approval events.
* ``PersistStrategy.REDIS`` must publish rather than drop.  It previously logged
  critical and returned.
"""

from unittest.mock import AsyncMock, patch

import pytest

from events.bus import EventBus, PersistStrategy


@pytest.fixture
def buses():
    """Patch both managers and yield (event_manager, live_event_manager)."""
    event_manager = AsyncMock()
    live_manager = AsyncMock()
    with (
        patch("events.bus.get_event_manager", return_value=event_manager),
        patch("events.bus.get_live_event_manager", return_value=live_manager),
    ):
        yield event_manager, live_manager


@pytest.mark.asyncio
async def test_none_reaches_the_channel_so_the_single_socket_still_sees_it(buses):
    """#14822: without this the frontend migration loses every NONE event."""
    event_manager, live_manager = buses

    await EventBus().publish("global", "workflow_step_started", {"step": 1}, persist=PersistStrategy.NONE)

    live_manager.publish.assert_awaited_once()
    assert live_manager.publish.await_args.args[0] == "global"
    # In-process listeners must keep working too.
    event_manager.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_memory_does_not_notify_in_process_listeners(buses):
    event_manager, live_manager = buses

    await EventBus().publish("task:1", "progress", {}, persist=PersistStrategy.MEMORY)

    live_manager.publish.assert_awaited_once()
    event_manager.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_publishes_durably_instead_of_dropping(buses):
    """#14816: this path used to log critical and return."""
    _event_manager, live_manager = buses

    await EventBus().publish("chat:c1", "chat.message_added", {"m": 1}, persist=PersistStrategy.REDIS)

    live_manager.publish.assert_awaited_once()
    assert live_manager.publish.await_args.kwargs.get("durable") is True, (
        "REDIS published without requesting durable storage — nothing to replay from"
    )


@pytest.mark.asyncio
async def test_both_reaches_listeners_and_channel(buses):
    event_manager, live_manager = buses

    await EventBus().publish("global", "evt", {}, persist=PersistStrategy.BOTH)

    event_manager.publish.assert_awaited_once()
    live_manager.publish.assert_awaited_once()
