# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one writer for node lifecycle events (#17856).

``api/nodes.py`` and ``api/updates.py`` each carried an identical copy.
"""

import uuid
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.database import EventSeverity, Node, NodeEvent, NodeEventType, NodeStatus
from models.enrollment_skip import STATE_DEGRADED, STATE_FAILED, STATE_PENDING, EnrollmentSkip, skip_reason
from status_enums import NOT_FULLY_ENROLLED_STATUSES

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


#: "Fully enrolled" = latest enrollment not failed (event evidence, ``get_enrollment_failed_node_ids``) and the
#: NodeStatus not in ``status_enums.NOT_FULLY_ENROLLED_STATUSES`` (owner ruling 2026-11-10). A node that never
#: heartbeated is NOT skipped for that reason.
def unenrolled_state(status: str) -> Optional[str]:
    """The not-fully-enrolled state a node's row shows, or None when the row shows a fully enrolled node."""
    if status not in {s.value for s in NOT_FULLY_ENROLLED_STATUSES}:
        return None
    return STATE_DEGRADED if status == NodeStatus.DEGRADED.value else STATE_PENDING


async def get_unenrolled_nodes(db: AsyncSession, node_ids: Iterable[str]) -> Dict[str, str]:
    """node_id -> not-fully-enrolled state for the nodes among *node_ids* that are not fully enrolled (#21036).

    A failed latest enrollment wins; otherwise the node row decides (``unenrolled_state``). Two queries.
    """
    ids = list(node_ids)
    if not ids:
        return {}
    states = {n: STATE_FAILED for n in await get_enrollment_failed_node_ids(db, ids)}
    rows = await db.execute(select(Node.node_id, Node.status).where(Node.node_id.in_(ids)))
    for node_id, status in rows.all():
        state = unenrolled_state(status)
        if state and node_id not in states:
            states[node_id] = state
    return states


#: Role token on the SLM manager's own row (the same set ``main`` registers for the local node).
SLM_MANAGER_ROLE = "slm-backend"


def _pick_slm_node(rows: List[Node], host: str) -> Optional[Node]:
    """The SLM's own row among the rows sharing its address: the manager-role row, else the lowest ``id``.

    Several rows on one address are normal (co-located roles each have a row), so only a pick the role cannot
    settle is logged. *rows* arrive ordered by ``id``, which keeps the fallback stable.
    """
    managers = [n for n in rows if SLM_MANAGER_ROLE in (n.roles or [])]
    if len(rows) > 1 and len(managers) != 1:
        logger.warning(
            "SLM self node is ambiguous: %d nodes share %s, %d carry role %s; using %s (#21036)",
            len(rows),
            host,
            len(managers),
            SLM_MANAGER_ROLE,
            (managers or rows)[0].node_id,
        )
    return (managers or rows or [None])[0]


async def get_slm_self_node(db: AsyncSession, external_url: str) -> Optional[Node]:
    """The co-located SLM host's node (the node at the external URL's host), or None; never raises on duplicates.

    ``Node.ip_address`` is not unique, so the match is a deterministic pick (``_pick_slm_node``), not a single-row
    assertion. The one definition of "which node is the SLM" for update-all and the scheduled run (#21036).
    """
    host = urlparse(external_url).hostname or ""
    if not host:
        return None
    rows = (await db.execute(select(Node).where(Node.ip_address == host).order_by(Node.id))).scalars().all()
    return _pick_slm_node(list(rows), host)


async def get_slm_self_node_id(db: AsyncSession, external_url: str) -> Optional[str]:
    """node_id of the co-located SLM host, or None; the node that is never skipped (#21036)."""
    node = await get_slm_self_node(db, external_url)
    return node.node_id if node else None


async def split_enrollment_failed(
    db: AsyncSession, node_ids: List[str], exempt: Iterable[str] = ()
) -> Tuple[List[str], List[EnrollmentSkip]]:
    """Split *node_ids* into (targets, skipped with reason) by enrollment state; *exempt* is never skipped (#21036)."""
    states = await get_unenrolled_nodes(db, [n for n in node_ids if n not in set(exempt)])
    skipped = [EnrollmentSkip(node_id=n, reason=skip_reason(states[n])) for n in sorted(states)]
    for skip in skipped:
        logger.warning("fleet update: skipping node %s — %s (#21036)", skip.node_id, skip.reason)
    return [n for n in node_ids if n not in states], skipped
