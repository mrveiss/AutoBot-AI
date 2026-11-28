# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SLM manager node seeder helpers (#11360).

Extracted from main.py so the role-sync logic is unit-testable without
bootstrapping the full FastAPI application.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.role_group_ownership import merge_declared_roles
from models.database import NodeRole, RoleStatus

logger = logging.getLogger(__name__)


async def sync_slm_node_roles(session: AsyncSession, node_id: str, all_roles: list, detected_roles: list) -> None:
    """Upsert NodeRole rows for the SLM manager node (#11360).

    Roles in *detected_roles* are marked ACTIVE (confirmed running via systemd).
    Other assigned roles get a NOT_INSTALLED row so fleet-health can distinguish
    them from genuinely absent roles. Existing rows are updated; missing rows are
    inserted.  Stale rows (role no longer in all_roles) are left unchanged.
    """
    from sqlalchemy import select

    detected_set = set(detected_roles)
    nr_result = await session.execute(select(NodeRole).where(NodeRole.node_id == node_id))
    existing_map = {nr.role_name: nr for nr in nr_result.scalars().all()}

    for role_name in all_roles:
        desired_status = RoleStatus.ACTIVE.value if role_name in detected_set else RoleStatus.NOT_INSTALLED.value
        if role_name in existing_map:
            row = existing_map[role_name]
            if row.status != desired_status and role_name in detected_set:
                row.status = desired_status
        else:
            session.add(NodeRole(node_id=node_id, role_name=role_name, status=desired_status, assignment_type="auto"))


async def heal_existing_slm_node_roles(session: AsyncSession, node, node_id: str, slm_roles: list) -> None:
    """Heal an existing SLM node's roles on self-registration.

    ``detected_roles`` is reset to the SLM roles so the fleet view shows them running (older
    rows predate this). The SLM roles are DECLARED too -- merged, never removed -- so the
    inventory, which gates redis/database on declared or self-detected ownership, can't drop
    them from the SLM node (#19197).
    """
    if list(node.detected_roles or []) != slm_roles:
        node.detected_roles = slm_roles
    node.roles = merge_declared_roles(node.roles, slm_roles)
    await sync_slm_node_roles(session, node_id, list(node.roles), slm_roles)
