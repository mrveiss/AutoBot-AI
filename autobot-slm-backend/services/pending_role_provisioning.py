# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The builtin updater provisions a newly assigned role (#22211).

``update-all-nodes.yml`` deploys code and role-owned config; it never applies a role in full
(packages, units, credential registration, and the removal that follows). A role assigned to a node
therefore sat at ``not_installed`` until an operator pressed "provision" in the SLM.

For the roles listed in ``UPDATER_PROVISIONED_ROLES`` the fleet update now finishes the job: after
``update-all-nodes.yml`` succeeds on a node, the node's assigned-but-unprovisioned rows for those
roles are provisioned through the SLM's own provisioning path (``provision-fleet-roles.yml`` via
``api.nodes._execute_provision_playbook``). A failed provisioning fails the node's update, and the
row is left ``failed`` so the next update retries it.
"""

import logging
from typing import Any

from sqlalchemy import select

from models.database import Node, NodeRole
from services.database import db_service
from services.sync_restart import no_restart_args
from status_enums import RoleStatus

logger = logging.getLogger(__name__)

#: Roles the fleet update provisions when they are assigned but not yet provisioned.
UPDATER_PROVISIONED_ROLES = ("vnc",)
#: NodeRole statuses that mean "assigned, still to be provisioned" (a failed run is retried).
PENDING_STATUSES = (RoleStatus.NOT_INSTALLED.value, "failed")
_INSTALLING = "installing"


async def pending_roles(db, node_id: str) -> list:
    """The node's NodeRole rows for updater-provisioned roles that still need provisioning."""
    rows = await db.execute(
        select(NodeRole).where(
            NodeRole.node_id == node_id,
            NodeRole.role_name.in_(UPDATER_PROVISIONED_ROLES),
            NodeRole.status.in_(PENDING_STATUSES),
        )
    )
    return list(rows.scalars().all())


async def provision_pending_roles(node_id: str) -> tuple[bool, str]:
    """Provision the node's pending roles; returns (ok, message). (True, "") when none are pending."""
    from api.nodes import _execute_provision_playbook  # lazy: api.nodes imports services at import time

    async with db_service.session() as db:
        roles = await pending_roles(db, node_id)
        if not roles:
            return True, ""
        node = (await db.execute(select(Node).where(Node.node_id == node_id))).scalar_one_or_none()
        if node is None:
            return True, ""
        names = [r.role_name for r in roles]
        for role in roles:
            role.status = _INSTALLING
        await db.commit()
        try:
            await _execute_provision_playbook(db, node_id, node, roles, names)
        except Exception as exc:  # noqa: BLE001 - the helper marks the rows failed; report, never raise
            logger.error("Provisioning pending roles %s on %s failed: %s", names, node_id, exc)
            return False, f"provisioning of newly assigned role(s) {', '.join(names)} failed"
        return True, f"provisioned newly assigned role(s) {', '.join(names)}"


async def run_update_all_nodes(executor: Any, node_id: str, limit: list, restart: bool) -> dict:
    """Run ``update-all-nodes.yml`` for a node, then provision its pending roles (#22211)."""
    result = await executor.execute_playbook(
        playbook_name="update-all-nodes.yml", limit=limit, **no_restart_args(restart)  # #20743
    )
    if not result.get("success"):
        return result
    ok, message = await provision_pending_roles(node_id)
    if message:
        result = {**result, "output": f"{result.get('output', '')}\n{message}"}
    return {**result, "success": ok}
