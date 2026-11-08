# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hold the resumed fleet stage until the detached self-update has ended (#16644).

The self-update runs in a transient systemd unit (``playbook_executor``) so it
outlives the SLM restart its own Play 1 performs. The restarted process finds
the resume plan and used to start the fleet stage at once -- while the unit was
still running its later plays. Those plays restart the SLM a second time, which
killed the in-flight (attached) node deploy with code -15.

Only the no-restart path (``_await_self_update_completion``) ever waited. This
is the restart path's wait. It asks systemd whether the unit is active
(``read_deploy_activity``) instead of parsing log text: the log carries a PLAY
RECAP only at the very end, but a mid-run marker is easy to misread.

``in_progress is None`` (unit could not be queried) is NOT "finished": systemd
is busiest right after the SLM restart, which is exactly when the query times
out. It keeps polling until the deadline, like the reconcile path.

An ended unit only counts as a completed self-update when a completion newer
than the resume plan's job is on record (``resolve_completion_time``, shared
with the reconcile path). A unit that ended with no such completion crashed or
was killed; the SLM may be half-updated, so the fleet stage must not run.

Split out of ``api/code_sync.py``, which sits at its size ceiling.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from api._resume_plan import _clear_resume_plan
from autobot_shared.time_utils import utc_timestamp
from services.deploy_activity import read_deploy_activity

if TYPE_CHECKING:  # pragma: no cover - typing only
    from api.code_sync import UpdateAllJob

# Plain stdlib logging for the same reason as api/_resume_plan.py.
logger = logging.getLogger(__name__)


def _fail_resume(job: "UpdateAllJob", reason: str) -> None:
    """Fail the job and its self-update stage with *reason*."""
    now = utc_timestamp()
    for stage in job.stages:
        if stage.name == "slm_self_update":
            stage.status = "failed"
            stage.message = reason[:300]
            stage.completed_at = now
    job.status = "failed"
    job.failure_reason = reason[:300]
    job.completed_at = now


def resolve_completion_time(activity, since: str | None) -> str | None:
    """Return when the self-update completed, or None if no completion newer than *since*.

    Shared by the reconcile path (``_await_self_update_completion``) and the
    resume wait. Requires the unit to be not running (``in_progress is False``;
    None/unknown is not finished) and a completion strictly newer than *since*.
    """
    # Lazy: api.code_sync imports this module at load time.
    from api.code_sync import _completion_is_newer_than, _rotated_completion_time

    if activity.in_progress is not False:
        return None
    if not _completion_is_newer_than(activity.last_completed_play_at, since):
        return None
    rotated_at = _rotated_completion_time(run_alive=activity.in_progress)
    if rotated_at is None:
        return activity.last_completed_play_at
    # #14804: the reading came from the rotated log, so the live mtime dates a
    # truncation rather than a play. Resolve on the rotated file's own mtime when
    # that post-dates our firing; waiting instead made the condition permanent and
    # turned a successful self-update into a FAILED job an hour later.
    if _completion_is_newer_than(rotated_at, since):
        logger.warning(
            "update-all: self-update recap landed in the rotated log; resolving on its rotation time %s",
            rotated_at,
        )
        return rotated_at
    logger.warning("update-all: rotated-log verdict pre-dates this run — still waiting")
    return None


async def wait_for_detached_self_update(
    job: "UpdateAllJob",
    mark_progress,
    timeout_s: float,
    poll_s: float,
) -> bool:
    """Block until the detached self-update unit has ended WITH a fresh completion.

    Returns True when the fleet stage may start: the unit is not active and a
    completion newer than the job's creation (the resume plan's ``created_at``)
    is on record. Keeps polling while the unit is active or unqueryable. Returns
    False after failing the job and clearing the plan when that is not reached
    within *timeout_s*, or when the unit ended with no newer completion (a
    crashed or killed run). Each poll stamps progress so the staleness rule does
    not retire the job mid-wait (#14703).
    """
    deadline = time.monotonic() + timeout_s
    announced = False
    while True:
        activity = await read_deploy_activity()
        if activity.in_progress is False:
            if resolve_completion_time(activity, job.created_at) is not None:
                return True
            reason = (
                "detached self-update ended without a completion newer than this run — "
                "not continuing to the fleet stage"
            )
            logger.error("update-all resume: %s", reason)
            _fail_resume(job, reason)
            await _clear_resume_plan()
            return False
        if not announced:
            logger.info(
                "update-all resume: detached self-update still running or unknown (%s); holding the fleet stage",
                activity.reason,
            )
            announced = True
        mark_progress(job)
        if time.monotonic() >= deadline:
            reason = (
                f"detached self-update still running or not queryable after {timeout_s}s — "
                "not continuing to the fleet stage"
            )
            logger.error("update-all resume: %s", reason)
            _fail_resume(job, reason)
            await _clear_resume_plan()
            return False
        await asyncio.sleep(poll_s)
