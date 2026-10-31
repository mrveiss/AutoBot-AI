# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16644: the resumed fleet stage must not start while the detached self-update runs."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent))
from _code_sync_import import import_code_sync  # noqa: E402

import_code_sync()

from api import _resume_wait  # noqa: E402
from api.code_sync import UpdateAllJob, _execute_resume, _make_stage  # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _job():
    names = ("github_fetch", "code_source_pull", "slm_self_update", "fleet_nodes")
    return UpdateAllJob(
        job_id="j", status="running", created_at="2026-01-01T00:00:00+00:00", stages=[_make_stage(n) for n in names]
    )


_NEWER = "2999-01-01T00:00:00+00:00"
_OLDER = "2000-01-01T00:00:00+00:00"


def _activity(state, completed=None):
    if state is False and completed is None:
        completed = _NEWER  # an ended unit with a fresh completion unless a test says otherwise
    return SimpleNamespace(in_progress=state, reason="r", last_completed_play_at=completed)


def _wait(job, readings, timeout=60.0):
    marks = []
    with (
        patch.object(_resume_wait, "read_deploy_activity", AsyncMock(side_effect=readings)) as read,
        patch.object(_resume_wait, "_clear_resume_plan", AsyncMock()) as clear,
        patch("api.code_sync._rotated_completion_time", return_value=None),
    ):
        ok = _run(_resume_wait.wait_for_detached_self_update(job, marks.append, timeout, 0.001))
    return ok, read.await_count, len(marks), clear.await_count


def test_waits_while_unit_active_and_proceeds_when_it_ends():
    ok, polls, marks, clear = _wait(_job(), [_activity(True), _activity(True), _activity(False)])
    assert ok is True
    assert polls == 3  # held for two active readings
    assert marks == 2  # progress stamped per active poll
    assert clear == 0


def test_no_unit_proceeds_immediately():
    ok, polls, _, _ = _wait(_job(), [_activity(False)])
    assert ok is True and polls == 1


def test_unqueryable_unit_keeps_waiting_and_fails_at_the_deadline():
    job = _job()
    ok, polls, _, clear = _wait(job, [_activity(None)] * 50, timeout=0.0)
    assert ok is False and polls == 1
    assert job.status == "failed"
    assert [s.status for s in job.stages if s.name == "slm_self_update"] == ["failed"]
    assert clear == 1


def test_unknown_then_ended_with_completion_proceeds():
    ok, polls, marks, clear = _wait(_job(), [_activity(None), _activity(None), _activity(False)])
    assert ok is True and polls == 3 and marks == 2 and clear == 0


def test_ended_with_newer_completion_proceeds():
    ok, polls, _, clear = _wait(_job(), [_activity(False, _NEWER)])
    assert ok is True and polls == 1 and clear == 0


def test_ended_without_newer_completion_fails_the_stage():
    for completed in (None, _OLDER):
        job = _job()
        ok, _, _, clear = _wait(job, [SimpleNamespace(in_progress=False, reason="r", last_completed_play_at=completed)])
        assert ok is False
        assert job.status == "failed"
        assert "without a completion" in job.failure_reason
        assert [s.status for s in job.stages if s.name == "slm_self_update"] == ["failed"]
        assert clear == 1


def test_timeout_fails_the_job_and_clears_the_plan():
    job = _job()
    ok, _, _, clear = _wait(job, [_activity(True)] * 50, timeout=0.0)
    assert ok is False
    assert job.status == "failed"
    assert "still running" in job.failure_reason
    assert [s.status for s in job.stages if s.name == "slm_self_update"] == ["failed"]
    assert clear == 1


def test_execute_resume_does_not_start_fleet_stage_when_wait_refuses():
    job = _job()
    with (
        patch("api.code_sync.wait_for_detached_self_update", AsyncMock(return_value=False)),
        patch("api.code_sync._resume_verify_slm_stage", AsyncMock()) as verify,
        patch("api.code_sync._run_fleet_stage", AsyncMock()) as fleet,
    ):
        _run(_execute_resume(job, "abc", ["n1"]))
    verify.assert_not_awaited()
    fleet.assert_not_awaited()


def test_execute_resume_waits_before_verifying_and_running_fleet():
    job = _job()
    order = []

    async def waited(*_a, **_k):
        order.append("wait")
        return True

    async def verified(*_a, **_k):
        order.append("verify")
        return True

    async def fleet(*_a, **_k):
        order.append("fleet")

    with (
        patch("api.code_sync.wait_for_detached_self_update", waited),
        patch("api.code_sync._resume_verify_slm_stage", verified),
        patch("api.code_sync._run_fleet_stage", fleet),
    ):
        _run(_execute_resume(job, "abc", ["n1"]))
    assert order == ["wait", "verify", "fleet"]
