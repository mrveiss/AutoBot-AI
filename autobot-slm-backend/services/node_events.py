# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one writer for node lifecycle events (#17856).

``api/nodes.py`` and ``api/updates.py`` each carried an identical copy.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from models.database import EventSeverity, NodeEvent, NodeEventType


async def create_node_event(
    db: AsyncSession,
    node_id: str,
    event_type: NodeEventType,
    severity: EventSeverity,
    message: str,
    details: dict = None,
) -> NodeEvent:
    """Create a node lifecycle event; flushes but does not commit (caller owns the transaction)."""
    event = NodeEvent(
        event_id=str(uuid.uuid4())[:16],
        node_id=node_id,
        event_type=event_type.value,
        severity=severity.value,
        message=message,
        details=details or {},
    )
    db.add(event)
    await db.flush()
    return event
