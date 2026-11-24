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
roles (and a vnc role whose node has no registered VNC credential) are provisioned through the
SLM's own provisioning path (``provision-fleet-roles.yml`` via
``api.nodes._execute_provision_playbook``). A failed provisioning fails the node's update, and the
row is left ``failed``.

A node whose provisioning keeps failing is not retried on every update: a row attempted within
``SLM_ROLE_PROVISION_RETRY_COOLDOWN_HOURS`` is skipped, and by then the code deploy has succeeded, so a
provisioning failure is reported as a warning in the node's output and does not fail its update. A row a
crash left at ``installing`` becomes eligible again once it is older than the cooldown.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from autobot_shared.env_utils import env_int_clamped
from models.database import Node, NodeCredential, NodeRole
from services.database import db_service
from services.sync_restart import no_restart_args
from status_enums import RoleStatus

logger = logging.getLogger(__name__)

#: Roles the fleet update provisions when they are assigned but not yet provisioned.
UPDATER_PROVISIONED_ROLES = ("vnc",)
#: NodeRole statuses that mean "assigned, still to be provisioned" (a failed run is retried).
PENDING_STATUSES = (RoleStatus.NOT_INSTALLED.value, "failed")
#: A role whose provisioning registers a credential, mapped to its `node_credentials.credential_type`.
#: Such a role is provisioned again when the node has none, whatever the role row's status: the row can
#: read active (the units were installed or detected) while the registration never happened (#22211).
CREDENTIAL_REGISTERED_BY_ROLE = {"vnc": "vnc"}
_INSTALLING = "installing"
_FAILED = "failed"
#: Hours before a role already attempted on a node is provisioned again (registered in env_registry_slm_roles).
RETRY_COOLDOWN_HOURS = env_int_clamped("SLM_ROLE_PROVISION_RETRY_COOLDOWN_HOURS", 6, min_v=1, max_v=720)


async def _credential_types(db, node_id: str) -> set[str]:
    """Credential types the node has an ACTIVE credential for (a deactivated one is not registered)."""
    rows = await db.execute(
        select(NodeCredential.credential_type).where(
            NodeCredential.node_id == node_id, NodeCredential.is_active.is_(True)
        )
    )
    return {r[0] for r in rows.all()}


def _attempted_recently(role, now: datetime) -> bool:
    """True when the row was touched (provisioning attempted) inside the cooldown."""
    touched = getattr(role, "updated_at", None)
    if touched is None:
        return False
    if touched.tzinfo is None:
        touched = touched.replace(tzinfo=timezone.utc)
    return now - touched < timedelta(hours=RETRY_COOLDOWN_HOURS)


def _needs_provisioning(role, credential_types: set[str], now: datetime | None = None) -> bool:
    """Whether the fleet update should provision this row now.

    * ``not_installed``: assigned, never attempted -> yes, at once.
    * every other status is a row that was already attempted (or is mid-attempt, or was left at
      ``installing`` by a crash): provision again only when it is failed or lacks its credential, and only
      once the cooldown has passed.
    """
    if role.status == RoleStatus.NOT_INSTALLED.value:
        return True
    if _attempted_recently(role, now or datetime.now(timezone.utc)):
        return False
    wanted = CREDENTIAL_REGISTERED_BY_ROLE.get(role.role_name)
    missing_credential = wanted is not None and wanted not in credential_types
    return role.status in (_FAILED, _INSTALLING) or missing_credential


async def pending_roles(db, node_id: str) -> list:
    """The node's updater-provisioned NodeRole rows that need provisioning now (see ``_needs_provisioning``)."""
    rows = await db.execute(
        select(NodeRole).where(NodeRole.node_id == node_id, NodeRole.role_name.in_(UPDATER_PROVISIONED_ROLES))
    )
    roles = list(rows.scalars().all())
    if not roles:
        return []
    creds = await _credential_types(db, node_id)
    now = datetime.now(timezone.utc)
    return [r for r in roles if _needs_provisioning(r, creds, now)]


async def _run_provisioning(db, node_id: str, node, roles: list, names: list[str]) -> str:
    """Provision `roles`; return a warning message ('' on success). A row never stays at installing."""
    from api.nodes import _execute_provision_playbook  # lazy: api.nodes imports services at import time

    try:
        await _execute_provision_playbook(db, node_id, node, roles, names)
        return ""
    except Exception as exc:  # noqa: BLE001 - the helper marks the rows failed; report, never raise
        logger.error("Provisioning pending roles %s on %s failed: %s", names, node_id, exc)
        return f"WARNING: provisioning of role(s) {', '.join(names)} failed; the code update succeeded"
    finally:
        await _settle_installing(db, roles)


async def _settle_installing(db, roles: list) -> None:
    """A crash or cancellation must not leave a row at installing: it is failed, and the cooldown applies."""
    stale = [r for r in roles if r.status == _INSTALLING]
    if not stale:
        return
    try:
        for role in stale:
            role.status = _FAILED
        await db.commit()
    except Exception as exc:  # noqa: BLE001 - the age rule in _needs_provisioning recovers the row
        logger.error("Could not reset roles %s from installing: %s", [r.role_name for r in stale], exc)


async def provision_pending_roles(node_id: str) -> str:
    """Provision the node's pending roles; returns a message for the node's output ('' when none ran)."""
    async with db_service.session() as db:
        roles = await pending_roles(db, node_id)
        if not roles:
            return ""
        node = (await db.execute(select(Node).where(Node.node_id == node_id))).scalar_one_or_none()
        if node is None:
            return ""
        names = [r.role_name for r in roles]
        for role in roles:
            role.status = _INSTALLING
        await db.commit()
        warning = await _run_provisioning(db, node_id, node, roles, names)
        return warning or f"provisioned newly assigned role(s) {', '.join(names)}"


async def run_update_all_nodes(executor: Any, node_id: str, limit: list, restart: bool, **playbook_kwargs: Any) -> dict:
    """Run ``update-all-nodes.yml`` for a node, then provision its pending roles (#22211).

    The code deploy is the node's update. Provisioning runs only after it succeeded, and a failure of it is
    appended to the output as a warning: it never turns a successful update into a failed one.
    """
    result = await executor.execute_playbook(
        playbook_name="update-all-nodes.yml", limit=limit, **playbook_kwargs, **no_restart_args(restart)  # #20743
    )
    if not result.get("success"):
        return result
    message = await provision_pending_roles(node_id)
    if message:
        result = {**result, "output": f"{result.get('output', '')}\n{message}"}
    return result
