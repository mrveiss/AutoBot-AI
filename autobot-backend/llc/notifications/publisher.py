# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC WebSocket publisher (GH#8255).

Publishes LLC events to WebSocket clients filtered by company_id using both
the LiveEventManager (company:{id} channel) and the EventManager broadcast.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from event_manager import get_event_manager
    from live_event_manager import get_live_event_manager
except ImportError:
    get_live_event_manager = None  # type: ignore[assignment]
    get_event_manager = None  # type: ignore[assignment]


@dataclass
class LLCEvent:
    """Typed event envelope for LLC WebSocket messages."""

    company_id: str
    event_type: str
    entity_type: str
    entity_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    actor_id: Optional[str] = None


class LLCWebSocketPublisher:
    """Publishes LLC events to connected WebSocket clients.

    Uses the LiveEventManager channel ``company:{company_id}`` so only clients
    subscribed to that company receive the event (multi-tenant isolation).

    Also fans out via EventManager for clients using the broadcast path.
    Never raises — failures are logged but must not break the caller.
    """

    async def publish(
        self,
        company_id: str,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: Dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> None:
        channel = f"company:{company_id}"
        envelope: Dict[str, Any] = {
            "event_type": event_type,
            "company_id": company_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
            "actor_id": actor_id,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        try:
            if get_live_event_manager is not None:
                await get_live_event_manager().publish(channel, event_type, envelope)
        except Exception as exc:
            logger.warning("LLC publisher: LiveEventManager push failed: %s", exc)

        try:
            if get_event_manager is not None:
                # EventManager uses publish(), not publish_event() (GH#8544)
                await get_event_manager().publish(f"llc:{event_type}", envelope)
        except Exception as exc:
            logger.warning("LLC publisher: EventManager push failed: %s", exc)
