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

from pathlib import PurePosixPath
from typing import Annotated

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.code_sync import router
from api.security import create_audit_log
from autobot_shared.auth.permissions import Permission
from autobot_shared.security.path_http import require_contained_relative_path
from services.auth import require_permission
from services.database import get_db
from services.deploy_activity import read_deploy_activity
from services.deployed_dir_resolver import get_live_dir
from services.drift_checker import VISIBILITY_COMPONENTS
from services.drift_prune import (
    PruneResult,
    apply_prune,
    canonical_component,
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


def _require_component(component: str) -> str:
    """The allowlisted component name for *component*, or 400."""
    known = canonical_component(component)
    if known is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid component '{component}'. Must be one of: {sorted(VISIBILITY_COMPONENTS)}",
        )
    return known


def _require_contained_paths(component: str, paths: list[str]) -> None:
    """400 for any path that is not a plain file name under *component*'s deployed tree.

    The parent directory goes through the canonical containment check (absolute, ``..``
    and a symlinked parent that leaves the tree all refuse). The leaf is not resolved: a
    symlink leaf is removed as a link, never followed (``services/drift_prune.py``).
    """
    base = get_live_dir(component)
    for path in paths:
        pure = PurePosixPath(path)
        if pure.name in ("", ".", "..") or path.startswith("/") or "\x00" in path:
            raise HTTPException(status_code=400, detail="Invalid path")
        if str(pure.parent) != ".":
            require_contained_relative_path(str(pure.parent), base)


async def _refuse_unless_deploy_idle() -> None:
    """409 unless a self-update play is KNOWN not to be running (#22082).

    The strict twin of ``code_sync._reject_if_deploy_in_progress``, which logs and
    proceeds when the probe cannot answer (right for a resync). Removing files is
    not undone by retrying, so a probe that raises or reports "unknown" refuses.
    """
    try:
        activity = await read_deploy_activity()
    except Exception as exc:  # noqa: BLE001 - an unanswerable probe must refuse, never proceed
        raise HTTPException(status_code=409, detail=f"Cannot confirm no deploy is running: {exc}") from exc
    if activity.in_progress is not False:
        raise HTTPException(
            status_code=409,
            detail=f"A self-update play is running or its state is unknown ({activity.reason}); retry once it is idle.",
        )


async def _audit_pending(db: AsyncSession, user: dict, component: str, paths: list[str]):
    """Commit the intent BEFORE anything is removed: no deletion without a durable row."""
    actor = str(user.get("sub", ""))
    log = await create_audit_log(
        db,
        category="deploy",
        action="drift_prune",
        user_id=actor,
        username=actor,
        resource_type="component",
        resource_id=component,
        description=f"Pending removal of {len(paths)} confirmed removed_from_source file(s)",
        success=False,
        extra_data={"status": "pending", "requested": paths},
    )
    await db.commit()
    return log


async def _audit_outcome(db: AsyncSession, log, result: PruneResult | None, error: str | None = None) -> None:
    """Record what the run did on the row written before it."""
    extra = dict(log.extra_data or {})
    if result is None:
        extra.update(status="aborted", error=error)
        log.description = f"Aborted before removal: {error}"
        log.success = False
    else:
        extra.update(status="completed", removed=result.removed, refused=result.refused, failed=result.failed)
        log.description = f"Removed {len(result.removed)} of {len(extra.get('requested', []))} confirmed file(s)"
        log.success = not result.failed
    log.extra_data = extra
    await db.commit()


@router.post("/drift/prune/preview", response_model=DriftPrunePreview)
async def preview_drift_prune(
    request: DriftPrunePreviewRequest,
    _: Annotated[dict, Depends(require_permission(Permission.ADMIN_SYSTEM))],
) -> DriftPrunePreview:
    """List exactly the deployed files git proves were deleted from source (#22082)."""
    component = _require_component(request.component)
    plan = await plan_prune(component)
    if plan.error:
        raise HTTPException(status_code=409, detail=f"Cannot preview {component}: {plan.error}")
    return DriftPrunePreview(
        component=component,
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
    component = _require_component(request.component)
    _require_contained_paths(component, request.paths)
    await _refuse_unless_deploy_idle()
    log = await _audit_pending(db, user, component, request.paths)
    try:
        result = await apply_prune(component, request.paths, before_delete=_refuse_unless_deploy_idle)
    except Exception as exc:
        await _audit_outcome(db, log, None, f"{type(exc).__name__}: {exc}")
        raise
    await _audit_outcome(db, log, result)
    return DriftPruneResponse(
        component=result.component, removed=result.removed, refused=result.refused, failed=result.failed
    )
