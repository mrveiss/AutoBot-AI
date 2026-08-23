# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Multi-client event delivery and delivery-independent persistence (#14814).

The defect: ``EventManager`` held its WebSocket broadcast callback as a single
scalar.  Registering a second client silently displaced the first, the first
disconnect cleared delivery for everyone still connected, and — because chat
history was written from inside the broadcast callback — persistence stopped
entirely once no client was attached.

These tests drive ``EventManager.publish`` (the production entry point) and
assert at the far boundary: what each registered client actually received, and
what the persistence hook actually recorded.  Mutating the fan-out back to a
single callback must fail them.
"""

import pytest

from event_manager import EventManager


def _collector():
    """Return (received_list, async callback appending to it)."""
    received: list = []

    async def callback(event):
        received.append(event)

    return received, callback


@pytest.mark.asyncio
async def test_two_clients_both_receive_every_event():
    """Both registered clients receive the event — not just the last registered."""
    manager = EventManager()
    a_received, a_cb = _collector()
    b_received, b_cb = _collector()

    manager.register_websocket_broadcast(a_cb)
    manager.register_websocket_broadcast(b_cb)

    await manager.publish("task_update", {"task_id": "t1"})

    assert len(a_received) == 1, "first client stopped receiving when the second connected"
    assert len(b_received) == 1
    assert a_received[0]["type"] == "task_update"
    assert a_received[0] == b_received[0]


@pytest.mark.asyncio
async def test_one_client_disconnecting_does_not_silence_the_others():
    """Unregistering one connection leaves the remaining connections delivering."""
    manager = EventManager()
    a_received, a_cb = _collector()
    b_received, b_cb = _collector()

    manager.register_websocket_broadcast(a_cb)
    manager.register_websocket_broadcast(b_cb)

    manager.unregister_websocket_broadcast(b_cb)
    await manager.publish("task_update", {"task_id": "t2"})

    assert len(a_received) == 1, "surviving client went silent when another disconnected"
    assert len(b_received) == 0, "unregistered client still received events"


@pytest.mark.asyncio
async def test_persistence_runs_with_zero_clients_connected():
    """History is written when nobody is attached — persistence is not a delivery side effect."""
    manager = EventManager()
    persisted: list = []

    async def hook(event):
        persisted.append(event)

    manager.register_persistence_hook(hook)
    assert manager.websocket_broadcast_count == 0

    await manager.publish("llm_response", {"text": "hello", "session_id": "s1"})

    assert len(persisted) == 1, "nothing was persisted while no client was connected"
    assert persisted[0]["payload"]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_persistence_runs_exactly_once_regardless_of_client_count():
    """Two clients must not produce two history writes."""
    manager = EventManager()
    persisted: list = []

    async def hook(event):
        persisted.append(event)

    manager.register_persistence_hook(hook)
    _, a_cb = _collector()
    _, b_cb = _collector()
    manager.register_websocket_broadcast(a_cb)
    manager.register_websocket_broadcast(b_cb)

    await manager.publish("llm_response", {"text": "hi"})

    assert len(persisted) == 1, f"expected one write, got {len(persisted)}"


@pytest.mark.asyncio
async def test_failing_client_is_dropped_without_blocking_the_others():
    """A dead socket must not stop delivery to healthy ones."""
    manager = EventManager()
    good_received, good_cb = _collector()

    async def exploding_cb(event):
        raise RuntimeError("websocket connection closed")

    manager.register_websocket_broadcast(exploding_cb)
    manager.register_websocket_broadcast(good_cb)

    await manager.publish("progress", {"pct": 10})

    assert len(good_received) == 1, "healthy client lost delivery because a peer failed"
    assert manager.websocket_broadcast_count == 1, "failed callback was not unregistered"

    await manager.publish("progress", {"pct": 20})
    assert len(good_received) == 2


@pytest.mark.asyncio
async def test_persistence_failure_does_not_stop_delivery():
    """A broken persistence hook must not cost connected clients their events."""
    manager = EventManager()
    received, cb = _collector()

    async def bad_hook(event):
        raise RuntimeError("database unavailable")

    manager.register_persistence_hook(bad_hook)
    manager.register_websocket_broadcast(cb)

    await manager.publish("progress", {"pct": 50})

    assert len(received) == 1, "delivery was lost because persistence failed"


def test_register_rejects_none_instead_of_silently_clearing():
    """The old API cleared the global slot with None; that must now be an error."""
    manager = EventManager()
    with pytest.raises(ValueError):
        manager.register_websocket_broadcast(None)
