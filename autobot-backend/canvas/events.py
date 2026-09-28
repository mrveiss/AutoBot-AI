# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canvas cell events, published on the one bus (#17020).

`CanvasView.vue` did `onMounted(loadCanvas)` and nothing else, so a second tab
-- or the same tab after a change made anywhere else -- showed a stale canvas
until reloaded. `useCanvasWebSocket` was written to receive exactly this event
and opened `/api/canvas/{id}/ws`, a route the backend never served.

WHY A CHANNEL AND NOT THE ROUTE THE CLIENT ASKED FOR. `EVENT_STATE_DOCTRINE`
principle 5 is "channels, not routes": a new event type extends the channel
grammar in `live_event_manager.py` rather than adding an endpoint. Serving
`/api/canvas/{id}/ws` would have made a third parallel delivery system of
exactly the kind principle 1 names -- *"three parallel systems is the state this
codebase was already in once, and callers had to publish twice to reach
everyone"*. The doctrine's anti-goals do carve out sockets of their own for
binary and high-volume streams (VNC framebuffers, audio, PTY bytes, log tails);
a canvas cell delta is a JSON event and is not in that carve-out.

WHY A SEPARATE MODULE. `api/canvas.py` is grandfathered at 637 lines in a
shrink-only ratchet, so the publisher could not live beside its callers without
raising a ceiling the rules say to split instead. The canvas package is the
domain home, and `events.bus` is imported here rather than into
`api/websockets.py` -- which holds the rest of the canvas event helpers -- to
keep the bus out of that module's import graph.
"""

from __future__ import annotations

from typing import Any

from autobot_shared.logging_manager import get_logger
from events.bus import PersistStrategy, publish_event

logger = get_logger(__name__)

#: The channel a canvas's subscribers listen on. `live_event_manager` accepts
#: the `canvas` prefix and `api/live_events._authorize_canvas_channel` gates it
#: on the same owner check every REST route on the resource applies.
CANVAS_CHANNEL = "canvas:{canvas_id}"

CANVAS_CELL_EVENT = "canvas_cell"


def canvas_channel(canvas_id: Any) -> str:
    """The channel name for one canvas, so no call site formats it by hand."""
    return CANVAS_CHANNEL.format(canvas_id=canvas_id)


async def publish_cell(canvas_id: Any, cell: Any) -> None:
    """Announce a committed cell change to that canvas's subscribers.

    Call **after** the transaction commits. Publishing before it would announce
    a write a later rollback discards, and publishing inside the persistence
    step would make delivery a side effect of it -- principle 4 keeps the two
    concerns separate.

    `PersistStrategy.NONE` deliberately. The durable fact is the cell row, and a
    client that was away re-reads it with `GET /api/canvas/{id}`; the event is
    the notification, not the record. That is what principle 2 asks -- the
    user-visible truth is recoverable from state rather than only from the
    stream -- and it is why this event does not need replay.

    Never raises into its caller. The write has already committed by the time
    this runs, so a delivery failure must not turn a successful save into an
    error; it is logged and dropped.
    """
    try:
        await publish_event(
            canvas_channel(canvas_id),
            CANVAS_CELL_EVENT,
            cell_payload(canvas_id, cell),
            persist=PersistStrategy.NONE,
        )
    except Exception:
        logger.warning(
            "canvas_cell publish failed for canvas %s cell %s",
            canvas_id,
            getattr(cell, "id", "?"),
        )


def cell_payload(canvas_id: Any, cell: Any) -> dict:
    """The `canvas_cell` payload, in the shape `get_canvas_cell_event` defined.

    That builder (`api/websockets.py:325`) was written for this event and had
    **zero callers** -- it is reused rather than re-specified, so the field
    names the frontend already parses stay the contract. Its `seq` is the cell's
    version, which the REST routes increment, so a client can order updates it
    receives out of order.
    """
    from api.websockets import get_canvas_cell_event

    return get_canvas_cell_event(
        cell_id=str(cell.id),
        seq=getattr(cell, "version", 0),
        delta=getattr(cell, "content", None) or "",
        state=getattr(cell, "state", ""),
        canvas_id=str(canvas_id),
    )["payload"]
