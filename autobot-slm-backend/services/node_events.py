# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one writer for node lifecycle events (#17856).

``api/nodes.py`` and ``api/updates.py`` each carried an identical copy.
"""

import uuid
from typing import Iterable, List, Set, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.database import EventSeverity, NodeEvent, NodeEventType
from models.enrollment_skip import ENROLLMENT_SKIP_REASON, EnrollmentSkip

logger = get_logger(__name__)


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


# Enrollment outcomes share the DEPLOYMENT_* event types with update-job events
# (api/updates.py); this structured marker in ``details`` tells them apart (#21036).
ENROLLMENT_KIND_KEY = "kind"
ENROLLMENT_KIND = "enrollment"


def enrollment_details(details: dict = None) -> dict:
    """*details* plus the enrollment marker, for the enrollment event writers."""
    return {**(details or {}), ENROLLMENT_KIND_KEY: ENROLLMENT_KIND}


async def get_enrollment_failed_node_ids(db: AsyncSession, node_ids: Iterable[str]) -> Set[str]:
    """Node ids (among *node_ids*) whose latest enrollment event is DEPLOYMENT_FAILED (#21036).

    Positive evidence only (events without the marker are not counted): a node with no enrollment event, or with a
    DEPLOYMENT_COMPLETED after its last failure, is not returned. One query.
    """
    ids = list(node_ids)
    if not ids:
        return set()
    enrollment = (
        NodeEvent.node_id.in_(ids),
        NodeEvent.details[ENROLLMENT_KIND_KEY].as_string() == ENROLLMENT_KIND,
        NodeEvent.event_type.in_((NodeEventType.DEPLOYMENT_FAILED.value, NodeEventType.DEPLOYMENT_COMPLETED.value)),
    )
    # Latest by autoincrement id, not created_at: timestamps can tie or skew; id is the monotonic insert order.
    latest = select(func.max(NodeEvent.id)).where(*enrollment).group_by(NodeEvent.node_id)
    rows = await db.execute(
        select(NodeEvent.node_id).where(
            NodeEvent.id.in_(latest),
            NodeEvent.event_type == NodeEventType.DEPLOYMENT_FAILED.value,
        )
    )
    return set(rows.scalars().all())


async def split_enrollment_failed(db: AsyncSession, node_ids: List[str]) -> Tuple[List[str], List[EnrollmentSkip]]:
    """Split *node_ids* into (targets, skipped with reason) by enrollment outcome; log each skip (#21036)."""
    failed = await get_enrollment_failed_node_ids(db, node_ids)
    for node_id in sorted(failed):
        logger.warning("fleet update: skipping node %s — %s (#21036)", node_id, ENROLLMENT_SKIP_REASON)
    return [n for n in node_ids if n not in failed], [EnrollmentSkip(node_id=n) for n in sorted(failed)]
