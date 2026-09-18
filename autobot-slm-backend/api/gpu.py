# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
GPU API Routes (#16281)

Serves each node's GPU state from its latest heartbeat. ``api/__init__.py``
mounts this router on the monitoring router, so the route is
``GET /api/monitoring/gpu/nodes`` behind monitoring's guards. The NPU routes
(``api/npu.py``) probe a worker on demand; GPUs need no probe of their own,
because every agent reports them with its heartbeat (#16280).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.gpu_schemas import GPUNodeListResponse
from services.auth import get_current_user
from services.database import get_db
from services.node_gpu import fleet_gpu_statuses

router = APIRouter(prefix="/gpu", tags=["gpu"])


@router.get("/nodes", response_model=GPUNodeListResponse)
async def list_gpu_nodes(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> GPUNodeListResponse:
    """Every node's GPU state: not reported, none present, or its devices."""
    statuses = await fleet_gpu_statuses(db)
    return GPUNodeListResponse(nodes=statuses, total=len(statuses))
