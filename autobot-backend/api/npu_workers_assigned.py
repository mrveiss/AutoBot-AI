# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Nodes the SLM assigned npu-worker with no paired worker, for an admin to pair (#19706)."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas_npu_assigned import AssignedWorker, AssignedWorkersResponse
from auth_middleware import check_admin_permission
from autobot_shared.logging_manager import get_logger
from services.npu_worker_assignments import assigned_unpaired_workers

logger = get_logger(__name__)

router = APIRouter()


@router.get("/npu/assigned-unpaired-workers", response_model=AssignedWorkersResponse)
async def list_assigned_unpaired_workers(
    admin_check: bool = Depends(check_admin_permission),
) -> AssignedWorkersResponse:
    """Read only. A person pairs each through POST /npu/workers/pair."""
    try:
        found = await assigned_unpaired_workers()
    except Exception as exc:  # "could not read" must not look like "nothing to pair"
        logger.warning("Could not read the SLM's npu-worker assignments: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The SLM's nodes could not be read") from exc
    return AssignedWorkersResponse(workers=[AssignedWorker(url=u, hostname=h) for u, h in found.items()])
