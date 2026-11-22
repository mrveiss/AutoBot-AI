# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Operator action: remove exactly the ``removed_from_source`` files (#22082).

``POST /code-sync/drift/prune/preview`` lists what would be removed;
``POST /code-sync/drift/prune`` removes the confirmed subset. Candidates are the
verdicts of ``services/full_tree_drift.py`` and nothing else -- see
``services/drift_prune.py``.

Approval gates (#17038, owner rules of 2026-09-18) govern deleting stored data
and credentials. A file git proves was deleted from source is deploy output, the
same class the updater's own ``sync_deletions`` pass removes unattended, so it is
not routed through the approval queue. It is admin-only, previewed, confirmed
by the exact path list, refused while a deploy runs, and audited.

Registers onto the SAME ``APIRouter`` ``api.code_sync`` builds (imported from
``api.full_tree_drift``, itself imported at the bottom of ``code_sync``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.code_sync import _reject_if_deploy_in_progress, router
from api.security import create_audit_log
from autobot_shared.auth.permissions import Permission
from services.auth import require_permission
from services.database import get_db
from services.deployed_dir_resolver import get_live_dir
from services.drift_checker import VISIBILITY_COMPONENTS
from services.drift_prune import (
    PruneResult,
    apply_prune,
    is_prunable_component,
    plan_prune,
)

_MAX_PATHS = 5000


class DriftPrunePreviewRequest(BaseModel):
    """Which component to preview."""

    component: str


class DriftPruneRequest(DriftPrunePreviewRequest):
    """The exact paths the operator confirmed from the preview."""

    paths: list[str] = Field(min_length=1, max_length=_MAX_PATHS)


class DriftPruneFile(BaseModel):
    """One file a prune would remove, and the commit that removed it from source."""

    path: str
    detail: str | None = None


class DriftPrunePreview(BaseModel):
    """Exactly what a prune of *component* would remove."""

    component: str
    files: list[DriftPruneFile]


class DriftPruneResponse(BaseModel):
    """Per-path outcome of a confirmed prune."""

    component: str
    removed: list[str]
    refused: dict[str, str]
    failed: dict[str, str]


def _require_component(component: str) -> None:
    if not is_prunable_component(component):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid component '{component}'. Must be one of: {sorted(VISIBILITY_COMPONENTS)}",
        )


async def _audit_prune(db: AsyncSession, user: dict, result: PruneResult, requested: int) -> None:
    """Record one audit row per prune run; it lands in the same transaction as the commit."""
    actor = str(user.get("sub", ""))
    await create_audit_log(
        db,
        category="deploy",
        action="drift_prune",
        user_id=actor,
        username=actor,
        resource_type="component",
        resource_id=result.component,
        description=f"Removed {len(result.removed)} of {requested} confirmed removed_from_source file(s)",
        success=not result.failed,
        extra_data={
            "removed": result.removed,
            "refused": result.refused,
            "failed": result.failed,
        },
    )
    await db.commit()


@router.post("/drift/prune/preview", response_model=DriftPrunePreview)
async def preview_drift_prune(
    request: DriftPrunePreviewRequest,
    _: Annotated[dict, Depends(require_permission(Permission.ADMIN_SYSTEM))],
) -> DriftPrunePreview:
    """List exactly the deployed files git proves were deleted from source (#22082)."""
    _require_component(request.component)
    plan = await plan_prune(request.component)
    if plan.error:
        raise HTTPException(status_code=409, detail=f"Cannot preview {request.component}: {plan.error}")
    return DriftPrunePreview(
        component=request.component,
        files=[DriftPruneFile(path=p, detail=d) for p, d in plan.files],
    )


@router.post("/drift/prune", response_model=DriftPruneResponse)
async def confirm_drift_prune(
    request: DriftPruneRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(require_permission(Permission.ADMIN_SYSTEM))],
) -> DriftPruneResponse:
    """Remove the confirmed paths that are still ``removed_from_source`` (#22082).

    Anything else in *paths* -- a host_state, artifact or modified file, or one
    that stopped being eligible since the preview -- is refused and left alone.
    """
    _require_component(request.component)
    await _reject_if_deploy_in_progress()
    result = await apply_prune(request.component, request.paths, get_live_dir(request.component))
    await _audit_prune(db, user, result, len(request.paths))
    return DriftPruneResponse(
        component=result.component,
        removed=result.removed,
        refused=result.refused,
        failed=result.failed,
    )
