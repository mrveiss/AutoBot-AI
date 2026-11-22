# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which install directory removing a role from a node may delete (#22030, #21974).

``Role.target_path`` is where the code-sync writes, which is not necessarily a directory the role owns: the roles of
one manifest (backend, celery, scheduler) share its ``destination``, and the removal playbook deletes whatever
directory it is handed. So the directory comes from the manifest ``destination``, and only for a role that owns the
whole manifest; a role that merely tags a service of a shared manifest owns no directory and removes none. A directory
another role on the node resolves to is kept too. A role no manifest resolves to keeps its own ``target_path``.
"""

from __future__ import annotations

from typing import Dict, Iterable, Mapping

from models.manifest import RoleManifest
from services.role_manifest_shape import find_role_manifest


def _install_dir(role_name: str, manifests: Dict[str, RoleManifest], target_paths: Mapping[str, str | None]):
    """(directory path, whether role_name owns it) -- the manifest destination, else the role's own target path."""
    manifest, owns_whole = find_role_manifest(role_name, manifests)
    if manifest is not None:
        return manifest.deploy.destination.rstrip("/"), owns_whole
    path = (target_paths.get(role_name) or "").rstrip("/")
    return (path or None), bool(path)


def removal_path(
    role_name: str,
    other_roles: Iterable[str],
    manifests: Dict[str, RoleManifest],
    target_paths: Mapping[str, str | None],
) -> str | None:
    """The directory to remove with ``role_name``, or None when it owns none or another role on the node uses it."""
    path, owns = _install_dir(role_name, manifests, target_paths)
    if not path or not owns:
        return None
    for other in other_roles:
        if _install_dir(other, manifests, target_paths)[0] == path:
            return None
    return path


async def role_removal_path(db, node_id: str, role_name: str) -> str | None:
    """:func:`removal_path` for ``role_name`` on ``node_id``, reading the node's other roles from the database."""
    from sqlalchemy import select

    from models.database import NodeRole, Role
    from services.manifest_loader import get_manifest_loader

    others = (
        (
            await db.execute(
                select(NodeRole.role_name).where(NodeRole.node_id == node_id, NodeRole.role_name != role_name)
            )
        )
        .scalars()
        .all()
    )
    rows = (await db.execute(select(Role.name, Role.target_path).where(Role.name.in_([role_name, *others])))).all()
    return removal_path(role_name, others, get_manifest_loader().load_all(), {name: path for name, path in rows})
