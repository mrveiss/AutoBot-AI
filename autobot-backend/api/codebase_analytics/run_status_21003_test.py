# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21003: a killed run's partial findings are never the latest complete result."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from api.codebase_analytics import run_status, subprocess_runner
from api.codebase_analytics.progress_tracker import _mark_task_failed
from api.codebase_analytics.run_status import (
    RunKilled,
    describe_run_state,
    record_run_finished,
    record_run_started,
    status_for_returncode,
    sweep_abandoned,
)

HARD = 1800


class _Collection:
    """In-memory stand-in for the ChromaDB collection (get/upsert by id)."""

    def __init__(self):
        self.docs = {}

    async def get(self, ids, include=None):
        return {"metadatas": [self.docs[i] for i in ids if i in self.docs]}

    async def upsert(self, ids, documents, metadatas):
        for i, m in zip(ids, metadatas):
            self.docs[i] = dict(m)


@pytest.fixture
def collection():
    col = _Collection()
    with patch.object(run_status, "get_code_collection_async", AsyncMock(return_value=col)):
        yield col


@pytest.mark.asyncio
async def test_completed_run_advances_the_pointer(collection):
    await record_run_started("src", "run-1")
    await record_run_finished("src", "run-1", "completed")
    state = await describe_run_state("src", HARD)
    assert state["status"] == "completed"
    assert state["partial"] is False
    assert state["last_completed_run_id"] == "run-1"


@pytest.mark.asyncio
async def test_killed_run_keeps_the_previous_completed_run_and_is_partial(collection):
    await record_run_started("src", "run-1")
    await record_run_finished("src", "run-1", "completed")
    await record_run_started("src", "run-2")  # findings are stored while it runs ...
    await record_run_finished("src", "run-2", "killed", "exit -9")  # ... then SIGKILL
    state = await describe_run_state("src", HARD)
    assert state["status"] == "killed"
    assert state["partial"] is True
    assert state["reason"] == "exit -9"
    assert state["last_completed_run_id"] == "run-1"


@pytest.mark.asyncio
async def test_killed_first_run_has_no_completed_result(collection):
    await record_run_started("src", "run-1")
    await record_run_finished("src", "run-1", "killed", "exit -9")
    state = await describe_run_state("src", HARD)
    assert state["partial"] is True
    assert state["last_completed_run_id"] == ""


@pytest.mark.asyncio
async def test_supervisor_crash_report_does_not_overwrite_completed(collection):
    await record_run_started("src", "run-1")
    await record_run_finished("src", "run-1", "completed")
    await record_run_finished("src", "run-1", "killed", "late crash report")
    assert (await describe_run_state("src", HARD))["status"] == "completed"


@pytest.mark.asyncio
async def test_sources_do_not_share_a_record(collection):
    await record_run_started("a", "run-a")
    await record_run_finished("a", "run-a", "completed")
    await record_run_started("b", "run-b")
    await record_run_finished("b", "run-b", "failed", "boom")
    assert (await describe_run_state("a", HARD))["partial"] is False
    assert (await describe_run_state("b", HARD))["partial"] is True


@pytest.mark.asyncio
async def test_run_left_running_past_timeout_is_abandoned(collection):
    await record_run_started("src", "run-1")
    soon = datetime.now(tz=timezone.utc) + timedelta(seconds=HARD // 2)
    assert await sweep_abandoned("src", HARD, now=soon) is False  # control: still within its limit
    late = datetime.now(tz=timezone.utc) + timedelta(seconds=HARD + run_status.ABANDON_GRACE_SECONDS + 5)
    assert await sweep_abandoned("src", HARD, now=late) is True
    state = await describe_run_state("src", HARD)
    assert state["status"] == "abandoned"
    assert state["partial"] is True
    assert state["last_completed_run_id"] == ""


def test_sigkill_maps_to_killed_and_other_codes_to_failed():
    assert status_for_returncode(-9) == "killed"
    assert status_for_returncode(-11) == "failed"
    assert status_for_returncode(1) == "failed"


def test_task_record_says_killed_for_a_killed_worker():
    tasks = {"t": {"status": "running"}}
    _mark_task_failed("t", RunKilled("killed by the progress watchdog"), tasks)
    assert tasks["t"]["status"] == "killed"
    control = {"t": {"status": "running"}}
    _mark_task_failed("t", RuntimeError("x"), control)
    assert control["t"]["status"] == "failed"


@pytest.mark.asyncio
async def test_crash_exit_9_records_killed_with_the_supervisors_reason(collection):
    await record_run_started("src", "run-1")
    await record_run_finished("src", "run-1", "completed")
    await record_run_started("src", "run-2")
    tasks = {"run-2": {"status": "running"}}

    def mark(task_id, error):
        _mark_task_failed(task_id, error, tasks)

    with patch.object(subprocess_runner, "_load_task_from_redis", AsyncMock(return_value=tasks["run-2"])):
        await subprocess_runner._handle_subprocess_crash(
            "run-2", -9, mark, AsyncMock(), source_id="src", kill_reason="killed by the hard timeout"
        )
    assert tasks["run-2"]["status"] == "killed"
    state = await describe_run_state("src", HARD)
    assert (state["status"], state["partial"]) == ("killed", True)
    assert state["reason"] == "killed by the hard timeout"
    assert state["last_completed_run_id"] == "run-1"
