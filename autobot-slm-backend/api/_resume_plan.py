# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Resume-plan persistence for the update-all orchestration (#15881).

Split out of ``api/code_sync.py``, which sits at its #14236 ceiling: carrying
the stage log across the SLM restart is added lines, and a grandfathered file
may not grow. The ratchet'"'"'s answer to "I need room" is "make the file smaller",
so the two writers move here.

The plan is what survives the restart the self-update performs. Everything the
resumed process knows about the run before it started comes from this row.
"""

import json as _json
from typing import TYPE_CHECKING, Any, Dict, List

from sqlalchemy import select

from autobot_shared.logging_manager import get_logger
from models.settings import Setting

if TYPE_CHECKING:  # pragma: no cover - typing only
    from api.code_sync import UpdateAllJob

logger = get_logger(__name__)

#: Settings key the plan is stored under.
_UPDATE_ALL_RESUME_KEY = "slm_update_all_resume"

_RESUME_PLAN_VERSION = 2

#: Plans written by an older SLM stay readable (#15881). Rejecting v1 would
#: discard the in-flight plan belonging to the very update deploying this
#: change -- the SLM would restart, find its own plan unreadable, and wedge.
_SUPPORTED_RESUME_PLAN_VERSIONS = frozenset({1, 2})

#: Per-stage log lines carried across the restart. It lives in a Settings row,
#: so it is smaller than the 200 a stage holds in memory.
_RESUME_PLAN_LOG_LINES = 60

#: Commit prefix used in this module's log lines only. `code_sync._short_sha`
#: is not imported: this module must not depend on it, or the extraction that
#: made room in that file reintroduces the coupling it removed.
_LOG_SHA_PREFIX = 12

async def _persist_resume_plan(
    job: UpdateAllJob,
    remaining_node_ids: List[str],
    target_commit: str,
) -> None:
    """Write resume plan to Settings so a fresh SLM process can continue fleet stage.

    Includes target_commit (C1) and version sentinel (M2).
    Always called even when remaining_node_ids is empty (C5).
    """
    from services.database import db_service

    plan = {
        "version": _RESUME_PLAN_VERSION,  # M2
        "job_id": job.job_id,
        "remaining_node_ids": remaining_node_ids,
        "target_commit": target_commit,  # C1
        "created_at": job.created_at,
        # #15881: `_stage_log` writes to `stage.log_lines`, which lives in the
        # process the self-update is about to restart. Without this the operator
        # watching the GUI sees the log stop at "Firing Ansible self-update
        # (fire-and-forget)" and never learn the outcome -- the resumed job
        # backfills "completed before restart" placeholders over the real lines.
        "stage_logs": {
            stage.name: list(stage.log_lines or [])[-_RESUME_PLAN_LOG_LINES:] for stage in job.stages
        },
    }
    async with db_service.session() as db:
        result = await db.execute(select(Setting).where(Setting.key == _UPDATE_ALL_RESUME_KEY))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = _json.dumps(plan)
        else:
            db.add(Setting(key=_UPDATE_ALL_RESUME_KEY, value=_json.dumps(plan)))
        await db.commit()
    logger.info(
        "update-all: persisted resume plan for %d fleet nodes (target=%s)",
        len(remaining_node_ids),
        (target_commit[:_LOG_SHA_PREFIX] if target_commit else None),
    )


async def _clear_resume_plan() -> None:
    """Remove resume plan from Settings after fleet stage completes."""
    from services.database import db_service

    try:
        async with db_service.session() as db:
            result = await db.execute(select(Setting).where(Setting.key == _UPDATE_ALL_RESUME_KEY))
            setting = result.scalar_one_or_none()
            if setting:
                await db.delete(setting)
                await db.commit()
    except Exception as exc:
        logger.warning("update-all: failed to clear resume plan: %s", exc)


