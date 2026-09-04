# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM Replication Background Jobs

The session-owning seam for replication work that outlives the HTTP request
which started it (#15549).

``api/stateful.py``'s ``start_replication`` hands its job to
``fire_and_forget`` and returns. FastAPI closes the ``Depends(get_db)`` session
in dependency teardown as soon as that response is sent, so a job holding a
reference to it is operating on a session whose lifetime has already ended:
``close()`` expunges the identity map, leaving every ORM row loaded through it
detached, and a later query silently checks a *fresh* connection out of the
pool rather than failing — which is why the defect corrupted state
nondeterministically instead of raising.

So the boundary carries plain identifiers only, and the job opens and owns its
own session here — the idiom ``_run_deployment`` (``services/deployment.py``),
``_run_backup``/``_run_restore`` (``api/stateful.py``) and ``_lag_monitor_loop``
(``services/replication.py``) already follow. ``ReplicationService`` keeps the
steps; this module keeps the lifetime.
"""

from __future__ import annotations

import logging
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import BackupServiceType, Node
from services.replication import replication_service

logger = logging.getLogger(__name__)


async def _load_replication_nodes(
    db: AsyncSession,
    source_node_id: str,
    target_node_id: str,
) -> Tuple[Node, Node] | None:
    """Load both replication endpoints through the job's own session.

    The rows the job works with have to be loaded by the session that owns
    them; a row handed across the background boundary is detached from the
    moment the request's session closes, which is the same defect as passing
    the session itself.

    Args:
        db: Database session owned by the background job
        source_node_id: Primary/master node id
        target_node_id: Replica node id

    Returns:
        (source_node, target_node), or None if either id is unknown
    """
    result = await db.execute(select(Node).where(Node.node_id.in_([source_node_id, target_node_id])))
    by_id = {node.node_id: node for node in result.scalars().all()}
    source_node = by_id.get(source_node_id)
    target_node = by_id.get(target_node_id)
    if source_node is None or target_node is None:
        return None
    return source_node, target_node


async def setup_replication(
    replication_id: str,
    source_node_id: str,
    target_node_id: str,
    service_type: BackupServiceType = BackupServiceType.REDIS,
) -> Tuple[bool, str]:
    """Set up replication from source to target, owning the session it uses.

    Takes identifiers rather than a session and two ORM rows (#15549): this
    runs after the request that scheduled it has already been torn down.

    Args:
        replication_id: Replication ID to track
        source_node_id: Primary/master node id
        target_node_id: Replica node id
        service_type: Service to replicate (currently only REDIS supported)

    Returns:
        Tuple of (success, message)
    """
    # #13578: identity against the member. The string comparison this replaces
    # only worked because ``BackupServiceType`` subclasses ``str``; it would
    # have silently passed a plain "redis" from any caller and silently failed
    # on any other spelling.
    if service_type is not BackupServiceType.REDIS:
        return False, f"Unsupported service type: {service_type.value}"

    from services.database import db_service

    async with db_service.session() as db:
        nodes = await _load_replication_nodes(db, source_node_id, target_node_id)
        if nodes is None:
            logger.error("Replication %s: source or target node not found", replication_id)
            return False, "Source or target node not found"
        return await replication_service.run_replication_steps(db, replication_id, *nodes)
