# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16640 — update-all must not read "completed" while a co-located deploy failed.

Host evidence (2026-09-13): POST /code-sync/update-all finished with status
`completed`, and the SLM self-node read `code_status: up_to_date` -- but in
the same run, the co-located browser-service and npu-worker deploys both
failed (ansible recap `failed=1`). The failures reached only the server log
line (`_stage_log`); nothing in the returned job/stage state, or the node's
own reported status, said so.

Root cause: the C4 fast path (`_run_slm_stage`, "SLM control plane already
at target commit") called `_resolve_colocated_managed_services` and then
unconditionally set `stage.status = CURRENT` and advanced the node's
`code_status` to up-to-date, regardless of what that call reported.

Pinned here:
  - a failed co-located role leaves the `slm_self_update` stage `partial`,
    naming the failed component(s) and reason(s) in `stage.message`;
  - the node's code_version/code_status is NOT advanced when any co-located
    component failed;
  - `_run_fleet_stage_or_already_current` (no other outdated fleet nodes)
    and `_run_fleet_stage` (other nodes ARE outdated) both keep `job.status`
    out of "completed"/"already_current" when the self-node's stage is
    `partial` -- two different code paths reach the same terminal state.
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
    _get_stage,
    _make_stage,
    _run_fleet_stage,
    _run_fleet_stage_or_already_current,
    _run_slm_stage,
    _StageStatus,
)

_SLM_IP = "192.0.2.10"
_SLM_NODE_ID = "slm-node-1"
_STAGE_NAMES = ("github_fetch", "code_source_pull", "slm_self_update", "fleet_nodes")
_BROWSER_FAILURE = "browser-service: Failed to find required executable \"virtualenv\""
_NPU_FAILURE = "npu-worker: pip rejects ../autobot_shared as an editable requirement (#15733)"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _new_job() -> UpdateAllJob:
    job = UpdateAllJob(job_id="job-16640", status="running")
    job.stages = [_make_stage(name) for name in _STAGE_NAMES]
    return job


def _db_service_returning(slm_node) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = slm_node
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db_service_ref = MagicMock()
    db_service_ref.session.return_value.__aenter__.return_value = db
    return db_service_ref


def _run_c4_fast_path(job: UpdateAllJob, colocated_failures: list[str]) -> MagicMock:
    """Drive `_run_slm_stage` down the C4 "already current" branch.

    `_resolve_colocated_managed_services` is patched directly -- the same
    module boundary test_code_sync_self_update_failure_16610.py patches
    `_get_slm_deployed_commit`/`_persist_resume_plan` at -- so this test is
    about what the C4 branch DOES with the result, not about the ansible role
    machinery underneath it.
    """
    slm_node = SimpleNamespace(node_id=_SLM_NODE_ID, ip_address=_SLM_IP)
    advance = AsyncMock()
    resolve = AsyncMock(return_value=colocated_failures)
    with (
        patch("api.code_sync.settings") as mock_settings,
        patch("api.code_sync._get_slm_deployed_commit", AsyncMock(return_value="target-commit")),
        patch("api.code_sync._resolve_colocated_managed_services", resolve),
        patch("api.code_sync._advance_node_version_if_fully_synced", advance),
    ):
        mock_settings.external_url = f"http://{_SLM_IP}"
        fired = _run(_run_slm_stage(job, "target-commit", [], _db_service_returning(slm_node)))
    assert fired is False, "C4 (already current) must not fire a self-update"
    resolve.assert_awaited_once_with(_get_stage(job, "slm_self_update"), _SLM_NODE_ID)
    return advance


def test_a_failed_colocated_component_leaves_the_stage_partial_with_the_reason() -> None:
    job = _new_job()
    advance = _run_c4_fast_path(job, [_BROWSER_FAILURE, _NPU_FAILURE])

    stage = _get_stage(job, "slm_self_update")
    assert stage.status == _StageStatus.PARTIAL, f"stage left at {stage.status!r}"
    assert _BROWSER_FAILURE in stage.message
    assert _NPU_FAILURE in stage.message
    assert stage.completed_at, "a terminal stage must carry a completion time"
    advance.assert_not_awaited(), "code_status must not advance to up_to_date over a failed component"


def test_no_colocated_failures_keeps_the_existing_current_behaviour() -> None:
    job = _new_job()
    advance = _run_c4_fast_path(job, [])

    stage = _get_stage(job, "slm_self_update")
    assert stage.status == _StageStatus.CURRENT
    assert "no restart needed" in stage.message
    advance.assert_awaited_once_with("autobot-slm-backend")


def _job_with_partial_slm_stage() -> UpdateAllJob:
    job = _new_job()
    stage = _get_stage(job, "slm_self_update")
    stage.status = _StageStatus.PARTIAL
    stage.message = f"SLM already at abc123 — co-located component(s) failed: {_BROWSER_FAILURE}"
    return job


def test_already_current_dispatch_reports_partial_not_completed() -> None:
    """No other outdated fleet nodes: the pre-#16640 code set
    job.status = 'already_current' here purely from deployed == remote_commit,
    never looking at whether the self-node's OWN stage was clean."""
    job = _job_with_partial_slm_stage()
    with patch("api.code_sync._get_slm_deployed_commit", AsyncMock(return_value="target-commit")):
        _run(_run_fleet_stage_or_already_current(job, [], "target-commit"))

    assert job.status == "partial", f"job left at {job.status!r}"
    assert job.completed_at


def test_already_current_dispatch_is_unaffected_when_slm_stage_is_clean() -> None:
    """Control: a clean CURRENT stage still reaches already_current, proving
    the new branch does not just always report partial."""
    job = _new_job()
    _get_stage(job, "slm_self_update").status = _StageStatus.CURRENT
    with patch("api.code_sync._get_slm_deployed_commit", AsyncMock(return_value="target-commit")):
        _run(_run_fleet_stage_or_already_current(job, [], "target-commit"))

    assert job.status == "already_current"


def test_fleet_stage_with_other_outdated_nodes_still_reports_partial() -> None:
    """The self-node's co-located failure must survive even when OTHER fleet
    nodes also needed updating -- _run_fleet_stage's own completion line
    unconditionally overwrote job.status based only on skipped_fleet_nodes,
    silently dropping this signal the moment there was other fleet work."""
    job = _job_with_partial_slm_stage()

    async def _sync_one_node(executor, node_id, job_, stage, slm_own_ip):
        job_.completed_fleet_nodes += 1
        return True

    with (
        patch("api.code_sync.get_playbook_executor", return_value=MagicMock()),
        patch("api.code_sync.settings") as mock_settings,
        patch("api.code_sync._sync_fleet_node", AsyncMock(side_effect=_sync_one_node)),
        patch("api.code_sync._clear_resume_plan", AsyncMock()),
    ):
        mock_settings.external_url = f"http://{_SLM_IP}"
        _run(_run_fleet_stage(job, ["other-node-1"]))

    assert job.status == "partial", f"job left at {job.status!r} despite the co-located failure"
    assert job.skipped_fleet_nodes == 0, "control: no fleet node was actually skipped this time"
