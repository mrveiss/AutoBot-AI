# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which install directory removing a role from a node may delete (#22030, #21974).

The result is a directory RELATIVE to the install root (possibly several segments, e.g. the agent's ``slm/agent``
package) or None, and None is the answer whenever removal is not provably safe. Removing any single role can never
delete the install root, a ``.`` / ``..`` path, a path outside the root, or a directory another role still needs:

* the directory comes from the manifest ``destination`` (not the code-sync target), and only for a role that owns the
  whole manifest -- a role that merely tags a service of a shared manifest (celery, redis, ...) owns none;
* a role no manifest resolves to keeps its own ``target_path`` only when that path is strictly inside the root;
* a ``deploy_to_all`` manifest (``autobot_shared``, the SLM agent) and a ``required`` role are never removed with
  their directory -- the other roles import from, or are managed by, them;
* another role located AT the install root itself overlaps every directory below it, so nothing is removed;
* a directory that is, contains or sits inside the directory of any other role on the node is kept. "Other roles" are
  the node's ``NodeRole`` rows plus its detected roles (``Node.detected_roles``, filled from the agent's heartbeat
  role report); the roles count as known only when that list is non-empty, contains the role being removed and the
  role report that wrote it was RECEIVED recently -- a heartbeat without a report does not renew it (an empty list
  is the column default and what an agent without role definitions sends), otherwise nothing is removed,
  because a role running on the node but missing from ``NodeRole`` would be invisible.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Mapping

from autobot_shared.install_paths import FLEET_INSTALL_ROOT, overlaps, relative_to_root
from models.manifest import RoleManifest
from services.role_manifest_shape import find_role_manifest


def _install_dir(role_name: str, manifests: Dict[str, RoleManifest], target_paths: Mapping[str, str | None]):
    """(relative directory or None, whether role_name owns it, whether it is never removed with its directory)."""
    manifest, owns_whole = find_role_manifest(role_name, manifests)
    if manifest is not None:
        return relative_to_root(manifest.deploy.destination), owns_whole, manifest.deploy_to_all
    rel = relative_to_root(target_paths.get(role_name))
    return rel, rel is not None, False


def _at_install_root(name: str, manifests: Dict[str, RoleManifest], target_paths: Mapping[str, str | None]) -> bool:
    """Whether a role is located at the install root itself, i.e. overlaps every removable directory."""
    manifest = find_role_manifest(name, manifests)[0]
    path = manifest.deploy.destination if manifest is not None else target_paths.get(name)
    return isinstance(path, str) and path.rstrip("/") == FLEET_INSTALL_ROOT.rstrip("/")


def removal_path(
    role_name: str,
    other_roles: Iterable[str],
    manifests: Dict[str, RoleManifest],
    target_paths: Mapping[str, str | None],
    required: frozenset = frozenset(),
    known_roles: frozenset | None = None,
) -> str | None:
    """The directory (relative to the install root) to remove with ``role_name``, or None to remove none.

    ``known_roles`` are the roles that have a ``Role`` row. When given, a role -- the one removed or any other on the
    node -- with neither a row nor a manifest is one nothing is known about (its ``required`` flag, its directory),
    so nothing is removed rather than guessed.
    """
    other_roles = list(other_roles)
    if known_roles is not None and any(
        name not in known_roles and find_role_manifest(name, manifests)[0] is None for name in (role_name, *other_roles)
    ):
        return None
    rel, owns, protected = _install_dir(role_name, manifests, target_paths)
    if rel is None or not owns or protected or role_name in required:
        return None
    for other in other_roles:
        theirs = _install_dir(other, manifests, target_paths)[0]
        if _at_install_root(other, manifests, target_paths) or (theirs is not None and overlaps(rel, theirs)):
            return None
    return rel


#: ``Node.extra_data`` key holding when the node's last heartbeat ROLE REPORT was received (ISO 8601, UTC).
ROLE_REPORT_AT_KEY = "role_report_at"


def record_role_report(node, detected: list[str], now: datetime | None = None) -> None:
    """Store a heartbeat's detected roles together with the time that report arrived (extra_data is reassigned)."""
    node.detected_roles = detected
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    node.extra_data = {**(getattr(node, "extra_data", None) or {}), ROLE_REPORT_AT_KEY: stamp}


def _role_report_time(node) -> datetime | None:
    """When the node's role report was received, or None when never recorded or unreadable."""
    from services.node_health_status import as_utc

    raw = (getattr(node, "extra_data", None) or {}).get(ROLE_REPORT_AT_KEY)
    try:
        return as_utc(datetime.fromisoformat(raw)) if isinstance(raw, str) else None
    except ValueError:
        return None


def detected_roles_if_fresh(node, now: datetime, timeout_s: float, role_name: str):
    """The node's detected roles, or None unless they are provably a real, current report.

    ``Node.detected_roles`` defaults to ``[]`` and the agent sends ``{}`` when it has no role definitions, so an empty
    list means "never reported", not "runs nothing". A report is trusted only when it is a non-empty list that
    CONTAINS ``role_name`` (the agent reports a role it runs) and the report itself -- not merely a later heartbeat,
    which leaves ``detected_roles`` untouched -- was received within ``timeout_s``.
    """
    received = _role_report_time(node)
    detected = getattr(node, "detected_roles", None)
    if not isinstance(detected, list) or role_name not in detected or received is None:
        return None
    return set(detected) if received >= now - timedelta(seconds=timeout_s) else None


async def role_removal_path(db, node_id: str, role_name: str) -> str | None:
    """:func:`removal_path` for ``role_name`` on ``node_id``; None unless the node's role picture is complete."""
    from sqlalchemy import select

    from config import settings
    from models.database import Node, NodeRole, Role
    from services.manifest_loader import get_manifest_loader

    node = (await db.execute(select(Node).where(Node.node_id == node_id))).scalar_one_or_none()
    detected = detected_roles_if_fresh(
        node, datetime.now(timezone.utc), settings.heartbeat_interval * settings.unhealthy_threshold, role_name
    )
    if detected is None:
        return None
    assigned = (await db.execute(select(NodeRole.role_name).where(NodeRole.node_id == node_id))).scalars().all()
    others = (set(assigned) | detected) - {role_name}
    rows = (
        await db.execute(select(Role.name, Role.target_path, Role.required).where(Role.name.in_([role_name, *others])))
    ).all()
    required = frozenset(name for name, _path, req in rows if req)
    paths = {name: path for name, path, _req in rows}
    return removal_path(
        role_name, others, get_manifest_loader().load_all(), paths, required, frozenset(name for name, *_ in rows)
    )
