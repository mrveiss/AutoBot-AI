# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one writer for node lifecycle events (#17856).

``api/nodes.py`` and ``api/updates.py`` each carried an identical copy.
"""

import uuid
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.database import EventSeverity, Node, NodeEvent, NodeEventType, NodeStatus
from models.enrollment_skip import STATE_DEGRADED, STATE_FAILED, STATE_PENDING, EnrollmentSkip, skip_reason

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


#: The ONE definition of "fully enrolled" (owner decision on #21036, 2026-11-09): a node is fully enrolled unless
#: its latest enrollment failed (event evidence, ``get_enrollment_failed_node_ids``), its NodeStatus is one of these
#: (-> the state named in the skip reason), or it has never heartbeated (enrollment unconfirmed -> pending).
NOT_ENROLLED_STATUS_STATES = {
    NodeStatus.PENDING.value: STATE_PENDING,
    NodeStatus.ENROLLING.value: STATE_PENDING,
    NodeStatus.DEGRADED.value: STATE_DEGRADED,
}


def unenrolled_state(status: str, last_heartbeat: Optional[datetime]) -> Optional[str]:
    """The not-fully-enrolled state a node's row shows, or None when the row shows a fully enrolled node."""
    state = NOT_ENROLLED_STATUS_STATES.get(status)
    if state is None and last_heartbeat is None:
        return STATE_PENDING
    return state


async def get_unenrolled_nodes(db: AsyncSession, node_ids: Iterable[str]) -> Dict[str, str]:
    """node_id -> not-fully-enrolled state for the nodes among *node_ids* that are not fully enrolled (#21036).

    A failed latest enrollment wins; otherwise the node row decides (``unenrolled_state``). Two queries.
    """
    ids = list(node_ids)
    if not ids:
        return {}
    states = {n: STATE_FAILED for n in await get_enrollment_failed_node_ids(db, ids)}
    rows = await db.execute(select(Node.node_id, Node.status, Node.last_heartbeat).where(Node.node_id.in_(ids)))
    for node_id, status, last_heartbeat in rows.all():
        state = unenrolled_state(status, last_heartbeat)
        if state and node_id not in states:
            states[node_id] = state
    return states


async def split_enrollment_failed(db: AsyncSession, node_ids: List[str]) -> Tuple[List[str], List[EnrollmentSkip]]:
    """Split *node_ids* into (targets, skipped with reason) by enrollment state; log each skip (#21036)."""
    states = await get_unenrolled_nodes(db, node_ids)
    skipped = [EnrollmentSkip(node_id=n, reason=skip_reason(states[n])) for n in sorted(states)]
    for skip in skipped:
        logger.warning("fleet update: skipping node %s — %s (#21036)", skip.node_id, skip.reason)
    return [n for n in node_ids if n not in states], skipped
