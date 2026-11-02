# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which nodes hold a role, and which of them are down (#19706).

A role flagged ``multi_node`` in role_registry can sit on several nodes, so "is the role up"
stops being one answer: fleet health has to say when some of its nodes are down.
"""

from typing import Dict, Iterable, List

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Node, NodeRole
from status_enums import NodeStatus, RoleStatus

_ASSIGNED_STATUSES = ["active", "installed", "not_installed"]
_NODE_DOWN_STATUSES = {NodeStatus.OFFLINE.value, NodeStatus.ERROR.value}


class RoleNodeHealth(BaseModel):
    """A multi-node role with at least one of its nodes down."""

    role: str
    nodes_up: List[str]
    nodes_down: List[str]


async def get_role_owners(db: AsyncSession) -> Dict[str, List[str]]:
    """Return role_name -> every node_id the role is assigned to (#1389, #19706)."""
    result = await db.execute(
        select(NodeRole.role_name, NodeRole.node_id).where(NodeRole.status.in_(_ASSIGNED_STATUSES))
    )
    owners: Dict[str, List[str]] = {}
    for row in result.all():
        owners.setdefault(row.role_name, []).append(row.node_id)
    return owners


def _service_multi_node_roles() -> List[str]:
    """Multi-node roles that run a service; a role with none has nothing that can go down."""
    from services.role_registry import DEFAULT_ROLES

    return [r["name"] for r in DEFAULT_ROLES if r.get("multi_node") and r.get("systemd_service")]


def classify_role_nodes(rows: Iterable) -> List[RoleNodeHealth]:
    """Split each role's nodes into up and down, keeping only roles with a node down.

    A node a role is not installed on yet is neither: the role has not been started there.
    """
    up: Dict[str, List[str]] = {}
    down: Dict[str, List[str]] = {}
    for row in rows:
        if row.status == RoleStatus.NOT_INSTALLED.value:
            continue
        is_down = row.status == RoleStatus.INACTIVE.value or row.node_status in _NODE_DOWN_STATUSES
        (down if is_down else up).setdefault(row.role_name, []).append(row.hostname)
    return [
        RoleNodeHealth(role=role, nodes_up=sorted(up.get(role, [])), nodes_down=sorted(nodes))
        for role, nodes in sorted(down.items())
    ]


async def get_roles_with_nodes_down(db: AsyncSession) -> List[RoleNodeHealth]:
    """Return the multi-node roles that have at least one node down."""
    result = await db.execute(
        select(NodeRole.role_name, NodeRole.status, Node.hostname, Node.status.label("node_status"))
        .join(Node, Node.node_id == NodeRole.node_id)
        .where(NodeRole.role_name.in_(_service_multi_node_roles()))
    )
    return classify_role_nodes(result.all())


def describe_roles_with_nodes_down(roles: List[RoleNodeHealth]) -> str:
    """One sentence naming each role's down nodes, for the fleet health detail line."""
    return "; ".join(
        f"{r.role} down on {', '.join(r.nodes_down)} "
        f"({len(r.nodes_down)} of {len(r.nodes_down) + len(r.nodes_up)} nodes)"
        for r in roles
    )


def with_nodes_down(health, roles: List[RoleNodeHealth]):
    """Add roles with a node down to a FleetHealthResponse; they degrade a healthy fleet."""
    if not roles:
        return health
    described = describe_roles_with_nodes_down(roles)
    if health.health == "healthy":
        update = {"health": "degraded", "detail": f"Degraded: {described}"}
    else:
        update = {"detail": f"{health.detail}; {described}"}
    return health.model_copy(update={**update, "roles_with_nodes_down": roles})
