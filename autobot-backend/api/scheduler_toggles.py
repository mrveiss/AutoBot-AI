# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Scheduler Toggles Admin API (GH#12820)

Operator control over which background schedulers run, without a redeploy.

Endpoints:
- GET    /api/admin/schedulers            - every registered job, effective state, default
- PUT    /api/admin/schedulers/{name}     - override a job's state
- DELETE /api/admin/schedulers/{name}     - clear the override, reverting to the default

Effective state is resolved by ``services.scheduler_toggles`` — the same resolver the
schedulers themselves consult — so what this API reports is what the jobs actually do.
"""

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException

from api.feature_flags import require_admin
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.audit_logger import audit_log
from services.scheduler_toggles import (
    clear_scheduler_override,
    get_job,
    list_scheduler_states,
    set_scheduler_enabled,
)

from .schemas_system import (
    SchedulerStateResponse,
    SchedulerToggleUpdate,
    SchedulerToggleUpdateResponse,
)

logger = get_logger(__name__)

router = APIRouter(tags=["admin", "schedulers"])


def _require_registered(name: str) -> None:
    """404 for a scheduler the registry does not describe."""
    if get_job(name) is None:
        raise HTTPException(status_code=404, detail=f"Unknown scheduler '{name}'")


@router.get("/schedulers", response_model=SchedulerStateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_scheduler_toggles",
    error_code_prefix="SCHEDULER_TOGGLES",
)
async def list_schedulers(_admin: Dict = Depends(require_admin)) -> SchedulerStateResponse:
    """List every registered scheduler with its effective state and declared default."""
    return SchedulerStateResponse(schedulers=await list_scheduler_states())


@router.put("/schedulers/{name}", response_model=SchedulerToggleUpdateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="set_scheduler_toggle",
    error_code_prefix="SCHEDULER_TOGGLES",
)
async def set_scheduler(
    name: str,
    update: SchedulerToggleUpdate,
    admin: Dict = Depends(require_admin),
) -> SchedulerToggleUpdateResponse:
    """Override a scheduler's state. Takes effect on the job's next cycle."""
    _require_registered(name)

    if not await set_scheduler_enabled(name, update.enabled):
        raise HTTPException(status_code=503, detail=f"Could not persist toggle for '{name}'")

    await audit_log(
        operation="config.update",
        result="success",
        user_id=admin.get("username", "admin"),
        resource=f"scheduler:{name}",
        details={"scheduler": name, "enabled": update.enabled},
    )
    logger.info("Scheduler %s toggled to enabled=%s by %s", name, update.enabled, admin.get("username", "admin"))
    return SchedulerToggleUpdateResponse(name=name, enabled=update.enabled, override_active=True)


@router.delete("/schedulers/{name}", response_model=SchedulerToggleUpdateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_scheduler_toggle",
    error_code_prefix="SCHEDULER_TOGGLES",
)
async def clear_scheduler(
    name: str,
    admin: Dict = Depends(require_admin),
) -> SchedulerToggleUpdateResponse:
    """Clear the override so the scheduler reverts to its registry default."""
    _require_registered(name)

    if not await clear_scheduler_override(name):
        raise HTTPException(status_code=503, detail=f"Could not clear toggle for '{name}'")

    job = get_job(name)
    await audit_log(
        operation="config.update",
        result="success",
        user_id=admin.get("username", "admin"),
        resource=f"scheduler:{name}",
        details={"scheduler": name, "override_cleared": True, "reverted_to": job.default_enabled},
    )
    logger.info("Scheduler %s override cleared by %s", name, admin.get("username", "admin"))
    return SchedulerToggleUpdateResponse(name=name, enabled=job.default_enabled, override_active=False)
