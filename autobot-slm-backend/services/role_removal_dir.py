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
* a directory that is, contains or sits inside the directory of any other role on the node is kept. "Other roles" are
  the node's ``NodeRole`` rows plus its detected roles (``Node.detected_roles``, filled from the agent's heartbeat
  role report); the roles count as known only when that list is non-empty, contains the role being removed and is
  fresh (an empty list is the column default and what an agent without role definitions sends), otherwise
  nothing is removed, because a role running on the node but missing from ``NodeRole`` would be invisible.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Mapping

from autobot_shared.install_paths import overlaps, relative_to_root
from models.manifest import RoleManifest
from services.role_manifest_shape import find_role_manifest


def _install_dir(role_name: str, manifests: Dict[str, RoleManifest], target_paths: Mapping[str, str | None]):
    """(relative directory or None, whether role_name owns it, whether it is never removed with its directory)."""
    manifest, owns_whole = find_role_manifest(role_name, manifests)
    if manifest is not None:
        return relative_to_root(manifest.deploy.destination), owns_whole, manifest.deploy_to_all
    rel = relative_to_root(target_paths.get(role_name))
    return rel, rel is not None, False


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
        if theirs is not None and overlaps(rel, theirs):
            return None
    return rel


def detected_roles_if_fresh(node, now: datetime, timeout_s: float, role_name: str):
    """The node's detected roles, or None unless they are provably a real, current report.

    ``Node.detected_roles`` defaults to ``[]`` and the agent sends ``{}`` when it has no role definitions, so an empty
    list means "never reported", not "runs nothing". A report is trusted only when it is a non-empty list that
    CONTAINS ``role_name`` (the agent reports a role it runs) and the last heartbeat is within ``timeout_s``.
    """
    from services.node_health_status import as_utc

    beat = as_utc(getattr(node, "last_heartbeat", None))
    detected = getattr(node, "detected_roles", None)
    if not isinstance(detected, list) or role_name not in detected or beat is None:
        return None
    return set(detected) if beat >= now - timedelta(seconds=timeout_s) else None


async def role_removal_path(db, node_id: str, role_name: str) -> str | None:
    """:func:`removal_path` for ``role_name`` on ``node_id``; None unless the node's role picture is complete."""
    from sqlalchemy import select

    from config import settings
    from models.database import Node, NodeRole, Role
    from services.manifest_loader import get_manifest_loader

    node = (await db.execute(select(Node).where(Node.node_id == node_id))).scalar_one_or_none()
    detected = detected_roles_if_fresh(
        node, datetime.now(timezone.utc), settings.heartbeat_interval * settings.unhealthy_threshold
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
