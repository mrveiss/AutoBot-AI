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
from models.enrollment_skip import STATE_DEGRADED, STATE_FAILED, STATE_PENDING, EnrollmentSkip, enrollment_skip_reason
from services.node_health_status import REASON_RESOURCE_PRESSURE, REASON_SERVICE_HEALTH, degraded_reason
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


async def get_latest_enrollment_events(db: AsyncSession, node_ids: Iterable[str]) -> Dict[str, str]:
    """node_id -> the event_type of its latest enrollment event (DEPLOYMENT_FAILED or DEPLOYMENT_COMPLETED) (#21036).

    Positive evidence only (events without the marker are not counted): a node with no enrollment event is absent.
    One query.
    """
    ids = list(node_ids)
    if not ids:
        return {}
    enrollment = (
        NodeEvent.node_id.in_(ids),
        NodeEvent.details[ENROLLMENT_KIND_KEY].as_string() == ENROLLMENT_KIND,
        NodeEvent.event_type.in_((NodeEventType.DEPLOYMENT_FAILED.value, NodeEventType.DEPLOYMENT_COMPLETED.value)),
    )
    # Latest by autoincrement id, not created_at: timestamps can tie or skew; id is the monotonic insert order.
    latest = select(func.max(NodeEvent.id)).where(*enrollment).group_by(NodeEvent.node_id)
    rows = await db.execute(select(NodeEvent.node_id, NodeEvent.event_type).where(NodeEvent.id.in_(latest)))
    return {node_id: event_type for node_id, event_type in rows.all()}


async def get_enrollment_failed_node_ids(db: AsyncSession, node_ids: Iterable[str]) -> Set[str]:
    """Node ids (among *node_ids*) whose latest enrollment event is DEPLOYMENT_FAILED (#21036)."""
    events = await get_latest_enrollment_events(db, node_ids)
    return {n for n, event in events.items() if event == NodeEventType.DEPLOYMENT_FAILED.value}


#: Reasons only heartbeat processing writes (``reconciler.apply_agent_presence``): the node has an agent.
_HEARTBEAT_REASONS = (REASON_RESOURCE_PRESSURE, REASON_SERVICE_HEALTH)


def _enrollment_evidenced(node: Node, enrollment_event: Optional[str]) -> bool:
    """Did *node* complete enrollment? Its latest enrollment event decides; with none, a first heartbeat does.

    ``DEPLOYMENT_COMPLETED`` is written only after the enrollment playbook succeeds (``api.nodes``). ``last_heartbeat``
    is written only when the node's agent reports (``reconciler``), so a row that never enrolled keeps it NULL.
    """
    if degraded_reason(node) in _HEARTBEAT_REASONS:
        return True
    if enrollment_event is not None:
        return enrollment_event == NodeEventType.DEPLOYMENT_COMPLETED.value
    return node.last_heartbeat is not None


#: THE definition of "not fully enrolled" (owner ruling 2026-11-10, AC3 of #21036) for every update route: the
#: latest enrollment failed, or the node is ``pending``/``enrolling``, or it is ``degraded`` with no evidence that
#: enrollment ever completed. A node degraded for resource pressure or service health is enrolled and is updated.
def unenrolled_state(node: Node, enrollment_event: Optional[str] = None) -> Optional[str]:
    """The not-fully-enrolled state *node* shows, or None when it is fully enrolled (and so updated)."""
    if node.status not in {s.value for s in NOT_FULLY_ENROLLED_STATUSES}:
        return None
    if node.status != NodeStatus.DEGRADED.value:
        return STATE_PENDING
    return None if _enrollment_evidenced(node, enrollment_event) else STATE_DEGRADED


async def get_unenrolled_nodes(db: AsyncSession, node_ids: Iterable[str]) -> Dict[str, str]:
    """node_id -> not-fully-enrolled state for the nodes among *node_ids* that are not fully enrolled (#21036).

    A failed latest enrollment wins; otherwise the node row decides (``unenrolled_state``). Two queries.
    """
    ids = list(node_ids)
    if not ids:
        return {}
    events = await get_latest_enrollment_events(db, ids)
    states = {n: STATE_FAILED for n, e in events.items() if e == NodeEventType.DEPLOYMENT_FAILED.value}
    nodes = (await db.execute(select(Node).where(Node.node_id.in_(ids)))).scalars().all()
    for node in nodes:
        state = unenrolled_state(node, events.get(node.node_id))
        if state and node.node_id not in states:
            states[node.node_id] = state
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
    skipped = [EnrollmentSkip(node_id=n, reason=enrollment_skip_reason(states[n])) for n in sorted(states)]
    for skip in skipped:
        logger.warning("fleet update: skipping node %s — %s (#21036)", skip.node_id, skip.reason)
    return [n for n in node_ids if n not in states], skipped
