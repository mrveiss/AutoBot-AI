# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-node LLM hardware capability profile API (#15495).

A small router nested onto ``nodes_router`` in ``api/__init__.py`` -- the
same move ``api/gpu.py`` made onto ``monitoring_router`` (#16281) -- because
``api/nodes.py`` is at its file-size ratchet ceiling and cannot gain a route
of its own.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.capability_schemas import NodeCapabilityProfileResponse
from models.database import Node
from models.node_capability import node_capability_profiles
from services.auth import get_current_user
from services.database import get_db

router = APIRouter(tags=["capability-profile"])


@router.get("/{node_id}/capability-profile", response_model=NodeCapabilityProfileResponse)
async def get_node_capability_profile(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeCapabilityProfileResponse:
    """A node's hardware capability profile -- all-unknown fields if it has never reported one."""
    node_result = await db.execute(select(Node.node_id).where(Node.node_id == node_id))
    if node_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    result = await db.execute(select(node_capability_profiles).where(node_capability_profiles.c.node_id == node_id))
    row = result.first()
    if row is None:
        return NodeCapabilityProfileResponse(node_id=node_id)

    return NodeCapabilityProfileResponse(
        node_id=row.node_id,
        total_ram_mb=row.total_ram_mb,
        total_vram_mb=row.total_vram_mb,
        gpu_present=row.gpu_present,
        gpu_model=row.gpu_model,
        npu_present=row.npu_present,
        free_disk_model_dir_mb=row.free_disk_model_dir_mb,
        updated_at=row.updated_at,
    )
