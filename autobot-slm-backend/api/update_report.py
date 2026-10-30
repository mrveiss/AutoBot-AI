# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /code-sync/update-all/report: read-only report of the last update, admin-only (#19962)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.auth.permissions import Permission
from autobot_shared.env_utils import env_int_clamped
from models.database import Deployment
from services.auth import require_permission
from services.database import get_db
from services.playbook_executor import SELF_UPDATE_LOG_PATH
from services.self_update_log_reader import read_self_update_verdict
from services.update_report import build_update_report

router = APIRouter()

#: Role deploys listed in the report; the newest are kept.
DEPLOY_RUNS_LIMIT = env_int_clamped("AUTOBOT_SLM_UPDATE_REPORT_DEPLOY_RUNS", 50, 1, 500)


async def _deploy_runs_since(db: AsyncSession, started_at: str | None) -> list[Deployment]:
    """Role deploys since the update started; none when the log gives no start to measure from."""
    if not started_at:
        return []
    since = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    query = select(Deployment).where(Deployment.created_at >= since)
    result = await db.execute(query.order_by(Deployment.created_at.desc()).limit(DEPLOY_RUNS_LIMIT))
    return list(result.scalars().all())


@router.get("/update-all/report")
async def get_update_report(
    _: Annotated[dict, Depends(require_permission(Permission.ADMIN_SYSTEM))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """The last update's target, stage, result, failed task, error and role deploys."""
    from api.code_sync import _get_slm_deployed_commit  # code_sync mounts this router

    started_at = read_self_update_verdict(SELF_UPDATE_LOG_PATH).run_started_at
    target = await _get_slm_deployed_commit()  # the marker moves before pip runs, so it is the target, not a success
    return build_update_report(SELF_UPDATE_LOG_PATH, target, await _deploy_runs_since(db, started_at))
