# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The builtin updater provisions a newly assigned role (#22211).

``update-all-nodes.yml`` deploys code and role-owned config; it never applies a role in full
(packages, units, credential registration, and the removal that follows). A role assigned to a node
therefore sat at ``not_installed`` until an operator pressed "provision" in the SLM.

For the roles listed in ``UPDATER_PROVISIONED_ROLES`` the fleet update now finishes the job: the
node's assigned-but-unprovisioned rows for those roles (and a vnc role whose node has no registered
VNC credential) are provisioned through the SLM's own provisioning path (``provision-fleet-roles.yml``
via ``api.nodes._execute_provision_playbook``), and the row is left ``failed`` when that fails.

Provisioning runs BEFORE ``update-all-nodes.yml`` (#22262): the play's vnc gate requires the
``autobot-vnc`` account on every node whose vnc role is active, and only provisioning creates it, so
provisioning only after a successful update deadlocked a held-but-unprovisioned node (it failed the
gate, so it was never provisioned, so it failed every later update). It runs again after a successful
update, for the restart-resume path.

Only ASSIGNED roles are provisioned: a row whose role is declared on ``Node.roles``, the operator-intent
record the inventory stamps as ``node_roles_declared`` (#14594), which is also what the vnc gate reads
(owner, 2026-11-27: a role the node only DETECTED, e.g. a local vncserver on the SLM manager, is not a
fleet vnc node and is never provisioned here).

A node whose provisioning keeps failing is not retried on every update: a row attempted within
``SLM_ROLE_PROVISION_RETRY_COOLDOWN_HOURS`` is skipped. A provisioning failure is reported as a warning in the
node's output and never fails its update by itself; a node whose vnc account is still missing then fails the
update at the play's gate, naming the account. A row a crash left at ``installing`` becomes eligible again
once it is older than the cooldown.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from models.database import Node, NodeCredential, NodeRole
from services.database import db_service
from services.sync_restart import no_restart_args
from status_enums import RoleStatus

logger = get_logger(__name__)

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
_INSTALLED = "installed"  # what api.nodes._execute_provision_playbook records on success
#: Statuses only the provisioner writes: their ``updated_at`` is the time of the attempt.
_PROVISIONER_STATUSES = (_FAILED, _INSTALLING, _INSTALLED)
#: Provisioner-owned statuses the role detector and the health poll must NOT overwrite: a ``failed``/``installing``
#: row stays so, so its ``updated_at`` keeps marking the attempt and the retry cooldown holds (#22262).
PROVISIONER_HELD_STATUSES = (_FAILED, _INSTALLING)
#: The inventory host of the update's Play 0 (the archive build on the SLM, #1091): a play target, never a node.
#: Every ``update-all-nodes.yml`` limit starts with it; the one spelling of it.
ARCHIVE_BUILD_HOST = "localhost"


def is_provisioner_held(role) -> bool:
    """True for an updater-provisioned role left failed/installing: only the updater retry settles it (#22262)."""
    return role.role_name in UPDATER_PROVISIONED_ROLES and role.status in PROVISIONER_HELD_STATUSES


#: Hours before a role already attempted on a node is provisioned again (registered in env_registry_slm_rollback).
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
    """Whether the fleet update should provision this row now: the ONE rule (#22211, #22262).

    * ``not_installed``: assigned, never attempted -> yes, at once.
    * a row the PROVISIONER wrote (``failed``, ``installing``, ``installed``) is provisioned again when it is
      failed/stuck or lacks its credential, and only once the cooldown has passed.
    * a row the role DETECTOR wrote (``active``/``inactive``: held, never provisioned) lacking its credential is
      provisioned at once. Its ``updated_at`` moves with every detection, so it is no sign of an attempt and
      must not hold the cooldown (#22262).
    """
    if role.status == RoleStatus.NOT_INSTALLED.value:
        return True
    wanted = CREDENTIAL_REGISTERED_BY_ROLE.get(role.role_name)
    missing_credential = wanted is not None and wanted not in credential_types
    if role.status not in _PROVISIONER_STATUSES:
        return missing_credential
    if _attempted_recently(role, now or datetime.now(timezone.utc)):
        return False
    return role.status in (_FAILED, _INSTALLING) or missing_credential


async def provisioner_holds(db, role) -> bool:
    """Whether the role detector, health poll and code sync must leave this row alone (#22262).

    :func:`is_provisioner_held`, plus an ``installed`` row whose credential is still missing inside the
    cooldown: letting detection rewrite it to ``active`` would make ``updated_at`` (the attempt's clock)
    look like a detection and re-provision it at once.
    """
    if is_provisioner_held(role):
        return True
    wanted = CREDENTIAL_REGISTERED_BY_ROLE.get(role.role_name)
    if wanted is None or role.status != _INSTALLED or not _attempted_recently(role, datetime.now(timezone.utc)):
        return False
    return wanted not in await _credential_types(db, role.node_id)


async def set_role_status_if_unchanged(db, role, new_status: str) -> bool:
    """Write *new_status* only while the row still has the status the caller observed (conditional UPDATE).

    A provisioner that committed ``installing``/``failed`` after the caller loaded the row wins; the caller's
    stale result is dropped. Returns whether the row was updated.
    """
    result = await db.execute(
        update(NodeRole).where(NodeRole.id == role.id, NodeRole.status == role.status).values(status=new_status)
    )
    return result.rowcount > 0


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


async def _run_provisioning(db, node_id: str, node, roles: list, **playbook_kwargs: Any) -> str:
    """Provision `roles`; return a warning message ('' on success). A row never stays at installing."""
    from api.nodes import _execute_provision_playbook  # lazy: api.nodes imports services at import time

    names = [r.role_name for r in roles]
    try:
        await _execute_provision_playbook(db, node_id, node, roles, names, **playbook_kwargs)
        return ""
    except Exception as exc:  # noqa: BLE001 - the helper marks the rows failed; report, never raise
        logger.error("Provisioning pending roles %s on %s failed: %s", names, node_id, exc)
        return f"WARNING: provisioning of role(s) {', '.join(names)} failed; it does not fail the code update"
    finally:
        await _settle_installing(node_id, names)


async def _settle_installing(node_id: str, names: list[str]) -> None:
    """A crash or cancellation must not leave a row at installing: it is failed, and the cooldown applies.

    Runs in a FRESH session: the provisioning session may be in a failed transaction after the exception.
    """
    try:
        async with db_service.session() as db:
            rows = await db.execute(select(NodeRole).where(NodeRole.node_id == node_id, NodeRole.role_name.in_(names)))
            stuck = [r for r in rows.scalars().all() if r.status == _INSTALLING]
            for role in stuck:
                role.status = _FAILED
            if stuck:
                await db.commit()
    except Exception as exc:  # noqa: BLE001 - the age rule in _needs_provisioning recovers the row
        logger.error("Could not reset roles %s on %s from installing: %s", names, node_id, exc)


async def _provision_pending_roles(node_id: str, **playbook_kwargs: Any) -> str:
    """Provision the node's pending roles; returns a message for the node's output ('' when none ran).

    ``playbook_kwargs`` (the no-restart arguments of a sync with ``restart=False``) reach the provisioning run.
    """
    async with db_service.session() as db:
        node = (await db.execute(select(Node).where(Node.node_id == node_id))).scalar_one_or_none()
        if node is None:
            return ""
        declared = set(node.roles or [])  # assigned only: what node_roles_declared is stamped from (#14594)
        roles = [r for r in await pending_roles(db, node_id) if r.role_name in declared]
        if not roles:
            return ""
        for role in roles:
            role.status = _INSTALLING
        await db.commit()
        warning = await _run_provisioning(db, node_id, node, roles, **playbook_kwargs)
        return warning or f"provisioned newly assigned role(s) {', '.join(r.role_name for r in roles)}"


async def provision_pending_roles(node_id: str, **playbook_kwargs: Any) -> str:
    """``_provision_pending_roles``, with any error (the queries, the commit) turned into a warning.

    It runs before and after the code update; a database error here must not fail it or break the fleet loop.
    """
    try:
        return await _provision_pending_roles(node_id, **playbook_kwargs)
    except Exception as exc:  # noqa: BLE001 - reported as a warning; CancelledError still propagates
        logger.error("Pending-role provisioning for %s could not run: %s", node_id, exc)
        return "WARNING: pending roles could not be provisioned (database error); it does not fail the code update"


def _with_messages(result: dict, messages: list[str], prepend: bool = False) -> dict:
    """``result`` with the non-empty provisioning ``messages`` joined into its output (ahead of it or after it)."""
    text = "\n".join(m for m in messages if m)
    if not text:
        return result
    output = result.get("output", "")
    return {**result, "output": f"{text}\n{output}" if prepend else f"{output}\n{text}"}


async def _provision_before_update(node_id: str, limit: list, restart_args: dict) -> list[str]:
    """Provision the pending roles of every node the run targets, ahead of the play's vnc gate (#22262).

    ``limit`` names the inventory hosts: the archive-build host, the node, and for the self-update the nodes
    co-located with the SLM (#15475), each gated by its own ``role_vnc_active``.
    """
    targets = dict.fromkeys([node_id, *(host for host in limit if host != ARCHIVE_BUILD_HOST)])
    return [await provision_pending_roles(target, **restart_args) for target in targets]


async def _raw_update_targets(limit_hosts: list[str] | None) -> list[str]:
    """Node ids an ``update-all-nodes.yml`` run over the setup-wizard inventory reaches that hold an assigned role.

    A limit naming only nodes (node id or inventory host name) narrows the set; a group or pattern token may cover
    any node, so then every node with an assigned updater-provisioned role is a target.
    """
    from api.setup_wizard import _sanitize_ansible_name  # lazy: the inventory's own host naming (#9283)

    async with db_service.session() as db:
        nodes = list((await db.execute(select(Node))).scalars().all())
    names = {n.node_id: {n.node_id, _sanitize_ansible_name(n.ansible_target)} for n in nodes}
    tokens = set(limit_hosts or []) - {ARCHIVE_BUILD_HOST}
    narrow = bool(tokens) and tokens <= set().union(*names.values())
    assigned = [n.node_id for n in nodes if set(n.roles or []) & set(UPDATER_PROVISIONED_ROLES)]
    return [node_id for node_id in assigned if not narrow or names[node_id] & tokens]


async def provision_before_raw_update(playbook_file: str, limit_hosts: list[str] | None) -> list[str]:
    """Output lines of the pending-role step for a run that bypasses ``run_update_all_nodes`` (#22262).

    ``POST /infrastructure/execute`` runs ``update-all-nodes.yml`` through its own subprocess, so it takes this
    step before the play's vnc gate instead. Any other playbook is left alone.
    """
    from services.rollback_target import ROLLBACK_PLAYBOOK  # the one name of the fleet update playbook

    if playbook_file != ROLLBACK_PLAYBOOK:
        return []
    try:
        targets = await _raw_update_targets(limit_hosts)
    except Exception as exc:  # noqa: BLE001 - the update goes on; the gate still fails an unprovisioned node
        logger.error("Pending-role targets for a raw update could not be read: %s", exc)
        return ["[WARNING] pending roles could not be provisioned (database error); it does not fail the update"]
    lines = []
    for node_id in targets:
        message = await provision_pending_roles(node_id)
        if message:
            lines.append(f"[INFO] {node_id}: {message}")
    return lines


async def run_update_all_nodes(
    executor: Any, node_id: str, limit: list, restart: bool, resume_after_restart: bool = False, **playbook_kwargs: Any
) -> dict:
    """Provision the targets' pending roles, run ``update-all-nodes.yml``, then provision again (#22211, #22262).

    The first step creates what the play's vnc gate requires (#22262); the second, after a successful run only,
    picks up anything still pending. Both use the run's restart policy, and a provisioning failure is a warning
    in the output: it never fails the update by itself. ``resume_after_restart`` is for a run that restarts
    THIS process (the SLM's own self-update): the node is marked first and, when the restart cuts the run, the
    restarted process does the second step (``services/pending_role_resume.py``) instead of this one.
    """
    from services.pending_role_resume import clear_provision_marker, mark_provision_after_restart

    restart_args = no_restart_args(restart)  # #20743
    early = await _provision_before_update(node_id, limit, restart_args)
    if resume_after_restart:
        await mark_provision_after_restart(node_id)
    result = await executor.execute_playbook(
        playbook_name="update-all-nodes.yml", limit=limit, **playbook_kwargs, **restart_args
    )
    result = _with_messages(result, early, prepend=True)
    if resume_after_restart:
        from api._resume_plan import restart_cut_the_wait

        if restart_cut_the_wait(result, node_id):
            return result  # the marker stays; the restarted process provisions
        await clear_provision_marker(node_id)
    if not result.get("success"):
        return result
    return _with_messages(result, [await provision_pending_roles(node_id, **restart_args)])
