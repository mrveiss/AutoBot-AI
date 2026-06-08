# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Event-publishing primitive.

Wraps events/bus.py so orchestration code has a single stable import path
that also satisfies the two-bus requirement (#4959): every call reaches
both EventManager and LiveEventManager via the unified EventBus facade.

See docs/developer/PRIMITIVES.md for the full inventory and #5060 for the
extraction-first methodology.
"""

from __future__ import annotations

from typing import Any, Dict

from events.bus import PersistStrategy
from events.bus import publish_event as _bus_publish_event

__all__ = ["publish_event", "PersistStrategy"]


async def publish_event(
    channel: str,
    event_type: str,
    payload: Dict[str, Any],
    *,
    persist: PersistStrategy = PersistStrategy.MEMORY,
) -> None:
    """Publish an event to both EventManager and LiveEventManager.

    This is the canonical publish point for orchestration code.  It routes
    through ``events/bus.py`` (the unified EventBus facade) so:
      - ``persist=MEMORY`` (default): reaches LiveEventManager (WebSocket fan-out)
      - ``persist=NONE``:  reaches EventManager only (fire-and-forget)
      - ``persist=BOTH``:  reaches both managers

    For durable Redis-backed events, use RedisEventStreamManager directly;
    the EventBus facade intentionally does not wrap it.
    """
    await _bus_publish_event(channel, event_type, payload, persist=persist)
