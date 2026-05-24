"""LLC WebSocket publisher interface (GH#8261).

GH#8255 (notification router) and GH#8221 (Kanban board real-time) both push
LLC events to WebSocket clients filtered by company_id. This publisher ensures
both callers use the same typed event envelope and company_id filter, and that
events reach both the RedisEventStreamManager and the LiveEventManager.

Concrete implementation in GH#8255. This file provides the interface stub.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class LLCEvent:
    """Typed event envelope for LLC WebSocket messages.

    Both WebSocket buses (RedisEventStreamManager and LiveEventManager) receive
    this envelope so subscribers on either bus get consistent payloads.
    """

    company_id: str
    event_type: str
    entity_type: str
    entity_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    actor_id: Optional[str] = None


class LLCWebSocketPublisher:
    """Publishes LLC events to connected WebSocket clients.

    Multi-tenant safety: company_id filter is applied before push so a client
    subscribed to company A never receives events from company B.

    Both GH#8255 (notification router) and GH#8221 (Kanban real-time) inject
    this rather than calling the WebSocket manager directly.
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
        """Publish an LLC event to all matching WebSocket subscribers.

        Pushes to both RedisEventStreamManager and LiveEventManager with the
        company_id filter applied. Never raises — publishing failures are
        logged but must not break the calling operation.

        Args:
            company_id: Tenant scope — only subscribers for this company receive
                the event.
            event_type: Logical event kind (use ActivityEventType string values).
            entity_type: Resource type name (e.g. "work_item", "sprint").
            entity_id: PK of the affected resource.
            payload: Serializable event data.
            actor_id: Optional agent/user that triggered the event.
        """
        raise NotImplementedError("LLCWebSocketPublisher.publish() — concrete impl in GH#8255")
