# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16610 — a self-update that fails before the restart must fail its stage.

After the branch rename, a plain ``git fetch origin`` in the SLM's code-source
checkout failed on a stale remote-tracking ref, so ``execute_playbook`` refused
the detached self-update run, by design. ``_ansible_self_update`` logged that
and cleared the resume plan, but the update-all job's ``slm_self_update`` stage
stayed "running": nothing told the job. The completion watcher then waited out
its whole timeout for a play that never started, and replaced the real reason
with "reported no completion".

Pinned here:
  - ``_run_slm_stage`` hands the self-update a failure callback, so a refused or
    raising run ends the stage AND the job ``failed``, with the reason;
  - a successful run leaves the stage to the restart, as before;
  - the watcher stops once the job has failed, and the reconcile step keeps
    the self-update's reason instead of overwriting it.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync  # noqa: E402

import_code_sync()

from api.code_sync import (  # noqa: E402
    UpdateAllJob,
    _await_self_update_completion,
    _fail_fleet_stage,
    _get_stage,
    _make_stage,
    _reconcile_self_update_stage,
    _run_slm_stage,
    _StageStatus,
)

_SLM_IP = "192.0.2.10"
_SLM_NODE_ID = "slm-node-1"
_REFUSAL_OUTPUT = "code_source sync failed before self-update of update-all-nodes.yml (#14524)"
_SUMMARY = "code_source sync failed before self-update"
_STAGE_NAMES = ("github_fetch", "code_source_pull", "slm_self_update", "fleet_nodes")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _new_job() -> UpdateAllJob:
    job = UpdateAllJob(job_id="job-16610", status="running")
    job.stages = [_make_stage(name) for name in _STAGE_NAMES]
    return job


def _db_service_returning(slm_node) -> MagicMock:
    """db_service whose session() yields a db that finds *slm_node* for the IP lookup."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = slm_node
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db_service_ref = MagicMock()
    db_service_ref.session.return_value.__aenter__.return_value = db
    return db_service_ref


def _fire_slm_stage(job: UpdateAllJob):
    """Run ``_run_slm_stage`` up to its fire; return the coroutine it handed to fire_and_forget."""
    fired = []
    slm_node = SimpleNamespace(node_id=_SLM_NODE_ID, ip_address=_SLM_IP)
    with (
        patch("api.code_sync.settings") as mock_settings,
        patch("api.code_sync._get_slm_deployed_commit", AsyncMock(return_value="deployed-commit")),
        patch("api.code_sync._compute_deps_changed", AsyncMock(return_value=False)),
        patch("api.code_sync._persist_resume_plan", AsyncMock()),
        patch("api.code_sync.fire_and_forget", lambda coro, name=None: fired.append(coro)),
    ):
        mock_settings.external_url = f"http://{_SLM_IP}"
        assert _run(_run_slm_stage(job, "target-commit", [], _db_service_returning(slm_node))) is True
    assert len(fired) == 1, "the stage must fire exactly one self-update"
    return fired[0]


def _run_self_update(coro, execute_playbook) -> SimpleNamespace:
    """Drive the fired self-update coroutine against a stub executor."""
    executor = MagicMock()
    executor.execute_playbook = execute_playbook
    mocks = SimpleNamespace(clear_plan=AsyncMock(), version=AsyncMock(), summarize=MagicMock(return_value=_SUMMARY))
    with (
        patch("api.code_sync.get_playbook_executor", return_value=executor),
        patch("api.code_sync._colocated_node_ids", AsyncMock(return_value=[_SLM_NODE_ID])),
        patch("api.code_sync.summarize_playbook_failure", mocks.summarize),
        patch("api.code_sync._clear_resume_plan", mocks.clear_plan),
        patch("api.code_sync._update_fleet_node_version", mocks.version),
    ):
        _run(coro)
    return mocks


def test_refused_self_update_fails_the_stage_and_the_job_with_the_reason() -> None:
    """The #16610 path: execute_playbook refuses the detached run after a failed code-source sync."""
    job = _new_job()
    refused = AsyncMock(
        return_value={"success": False, "output": _REFUSAL_OUTPUT, "returncode": -1, "timed_out": False}
    )

    mocks = _run_self_update(_fire_slm_stage(job), refused)

    stage = _get_stage(job, "slm_self_update")
    assert stage.status == _StageStatus.FAILED, f"stage left at {stage.status!r}"
    assert stage.message == _SUMMARY
    assert stage.completed_at, "a failed stage must carry a completion time"
    assert job.status == "failed"
    assert job.failure_reason == _SUMMARY
    assert job.completed_at
    mocks.summarize.assert_called_once_with(_REFUSAL_OUTPUT)
    mocks.clear_plan.assert_awaited_once()
    mocks.version.assert_not_awaited()


def test_self_update_that_raises_fails_the_stage_with_the_error() -> None:
    job = _new_job()
    raising = AsyncMock(side_effect=RuntimeError("executor unavailable"))

    mocks = _run_self_update(_fire_slm_stage(job), raising)

    stage = _get_stage(job, "slm_self_update")
    assert stage.status == _StageStatus.FAILED
    assert "executor unavailable" in stage.message
    assert job.status == "failed"
    assert "executor unavailable" in job.failure_reason
    mocks.clear_plan.assert_awaited_once()


def test_successful_self_update_leaves_the_stage_to_the_restart() -> None:
    """Success path unchanged: the service restarts and resume reconciliation resolves the stage."""
    job = _new_job()
    succeeded = AsyncMock(return_value={"success": True, "output": ""})

    mocks = _run_self_update(_fire_slm_stage(job), succeeded)

    assert _get_stage(job, "slm_self_update").status == _StageStatus.RUNNING
    assert job.status == "running"
    mocks.version.assert_awaited_once_with(_SLM_NODE_ID)
    mocks.clear_plan.assert_not_awaited()


def test_watcher_stops_once_the_self_update_failed_the_job() -> None:
    """A refused run never completes, so waiting out the timeout for it is the bug."""
    job = _new_job()
    stage = _get_stage(job, "slm_self_update")
    stage.started_at = "2026-09-13T08:00:00+00:00"
    _fail_fleet_stage(job, stage, _SUMMARY)
    # A newer completion IS on offer: without the failed-job check the watcher resolves on it.
    finished = SimpleNamespace(in_progress=False, reason="idle", last_completed_play_at="2026-09-13T09:00:00+00:00")
    activity = AsyncMock(return_value=finished)
    with (
        patch("api.code_sync.read_deploy_activity", activity),
        patch("api.code_sync._rotated_completion_time", return_value=None),
        patch("api.code_sync._SELF_UPDATE_WATCH_TIMEOUT_SECONDS", 5),
        patch("api.code_sync._SELF_UPDATE_WATCH_POLL_SECONDS", 0),
    ):
        assert _run(_await_self_update_completion(job, stage.started_at)) is None
    activity.assert_not_awaited()


def test_reconcile_keeps_the_self_update_failure_reason() -> None:
    job = _new_job()
    stage = _get_stage(job, "slm_self_update")
    stage.status = _StageStatus.RUNNING
    _fail_fleet_stage(job, stage, _SUMMARY)
    fleet = AsyncMock()
    with (
        patch("api.code_sync._await_self_update_completion", AsyncMock(return_value=None)),
        patch("api.code_sync._run_fleet_stage_or_already_current", fleet),
        patch("api.code_sync._clear_resume_plan", AsyncMock()),
    ):
        _run(_reconcile_self_update_stage(job, "target-commit", ["node-a"]))

    assert stage.status == _StageStatus.FAILED
    assert stage.message == _SUMMARY, "the reconcile step overwrote the self-update's reason"
    assert job.failure_reason == _SUMMARY
    fleet.assert_not_awaited()
