# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21003: a killed run's partial findings are never presented as the latest complete result."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from api.codebase_analytics import run_status, subprocess_runner
from api.codebase_analytics.chromadb_storage import _delete_source_documents
from api.codebase_analytics.progress_tracker import _mark_task_failed
from api.codebase_analytics.run_status import (
    RunKilled,
    describe_run_state,
    hard_timeout_kill_reason,
    record_run_finished,
    record_run_started,
    status_for_returncode,
    watchdog_kill_reason,
)

HARD = 1800


class _Collection:
    """In-memory stand-in for the ChromaDB collection: get/upsert/delete, ``where`` by equality."""

    def __init__(self):
        self.docs = {}
        self.reads = 0
        self.writes = 0

    def _matching(self, ids, where):
        if ids is not None:
            return [i for i in ids if i in self.docs]
        return [i for i, m in self.docs.items() if all(m.get(k) == v for k, v in (where or {}).items())]

    async def get(self, ids=None, where=None, include=None):
        self.reads += 1
        found = self._matching(ids, where)
        return {"ids": found, "metadatas": [self.docs[i] for i in found]}

    async def upsert(self, ids, documents, metadatas):
        self.writes += 1
        for i, m in zip(ids, metadatas):
            self.docs[i] = dict(m)

    async def delete(self, ids):
        for i in ids:
            self.docs.pop(i, None)


@pytest.fixture
def collection():
    col = _Collection()
    with patch.object(run_status, "get_code_collection_async", AsyncMock(return_value=col)):
        yield col


async def _state(source="src"):
    return await describe_run_state(source, HARD)


@pytest.mark.asyncio
async def test_completed_run_advances_the_pointer(collection):
    await record_run_started("src", "run-1")
    await record_run_finished("src", "run-1", "completed")
    state = await _state()
    assert state["status"] == "completed"
    assert state["partial"] is False
    assert state["last_completed_at"] == state["finished_at"] != ""


@pytest.mark.asyncio
async def test_killed_run_keeps_the_previous_completion_time_and_is_partial(collection):
    await record_run_started("src", "run-1")
    await record_run_finished("src", "run-1", "completed")
    completed_at = (await _state())["last_completed_at"]
    await record_run_started("src", "run-2")  # findings are stored while it runs ...
    await record_run_finished("src", "run-2", "killed", "exit -9")  # ... then SIGKILL
    state = await _state()
    assert (state["status"], state["partial"], state["reason"]) == ("killed", True, "exit -9")
    assert state["last_completed_at"] == completed_at
    assert state["started_at"] != "" and state["finished_at"] != ""


@pytest.mark.asyncio
async def test_killed_first_run_has_no_completion_time(collection):
    await record_run_started("src", "run-1")
    await record_run_finished("src", "run-1", "killed", "exit -9")
    state = await _state()
    assert state["partial"] is True
    assert state["last_completed_at"] == ""


@pytest.mark.asyncio
async def test_a_late_crash_report_never_overwrites_completed(collection):
    await record_run_started("src", "run-1")
    await record_run_finished("src", "run-1", "completed")
    assert await record_run_finished("src", "run-1", "killed", "late crash report") is False
    state = await _state()
    assert (state["status"], state["partial"], state["reason"]) == ("completed", False, "")


@pytest.mark.asyncio
async def test_the_first_terminal_status_of_a_run_is_final_even_when_it_is_not_completed(collection):
    await record_run_started("src", "run-1")
    await record_run_finished("src", "run-1", "killed", "exit -9")
    assert await record_run_finished("src", "run-1", "completed") is False
    state = await _state()
    assert (state["status"], state["last_completed_at"]) == ("killed", "")


@pytest.mark.asyncio
async def test_a_new_run_id_starts_fresh_after_any_terminal_status(collection):
    await record_run_started("src", "run-1")
    await record_run_finished("src", "run-1", "completed")
    await record_run_started("src", "run-2")
    state = await _state()
    assert (state["run_id"], state["status"], state["partial"]) == ("run-2", "running", True)
    assert state["last_completed_at"] != ""  # the pointer survives the new run
    await record_run_finished("src", "run-2", "failed", "boom")
    await record_run_started("src", "run-3")
    assert (await _state())["status"] == "running"


@pytest.mark.asyncio
async def test_a_stale_report_from_another_run_does_not_touch_the_newest_run(collection):
    await record_run_started("src", "run-2")
    assert await record_run_finished("src", "run-1", "failed", "old run") is False
    state = await _state()
    assert (state["run_id"], state["status"]) == ("run-2", "running")


@pytest.mark.asyncio
async def test_a_different_run_id_takes_over_a_terminal_record_when_its_start_write_was_lost(collection):
    """Run 2's start was never recorded; its kill must not leave run 1's ``completed`` standing."""
    await record_run_started("src", "run-1")
    await record_run_finished("src", "run-1", "completed")
    assert await record_run_finished("src", "run-2", "killed", "exit -9") is True
    state = await _state()
    assert (state["run_id"], state["status"], state["partial"]) == ("run-2", "killed", True)
    assert state["last_completed_at"] != ""  # run 1's completion is still the last complete one


@pytest.mark.asyncio
async def test_a_run_left_running_past_its_limit_reads_as_abandoned_without_writing(collection):
    await record_run_started("src", "run-1")
    writes, reads = collection.writes, collection.reads
    soon = datetime.now(tz=timezone.utc) + timedelta(seconds=HARD // 2)
    assert (await describe_run_state("src", HARD, now=soon))["status"] == "running"  # control: within its limit
    late = datetime.now(tz=timezone.utc) + timedelta(seconds=HARD + run_status.ABANDON_GRACE_SECONDS + 5)
    state = await describe_run_state("src", HARD, now=late)
    assert (state["status"], state["partial"], state["last_completed_at"]) == ("abandoned", True, "")
    assert "worker is gone" not in state["reason"] and state["reason"] != ""
    assert collection.writes == writes, "a read must not write"
    assert collection.reads == reads + 2, "one record read per call"
    assert collection.docs["codebase_run_src"]["latest_status"] == "running"  # never persisted as abandoned
    assert await record_run_finished("src", "run-1", "completed") is True  # a real report still lands


@pytest.mark.asyncio
async def test_sources_do_not_share_a_record(collection):
    await record_run_started("a", "run-a")
    await record_run_finished("a", "run-a", "completed")
    await record_run_started("b", "run-b")
    await record_run_finished("b", "run-b", "failed", "boom")
    assert (await _state("a"))["partial"] is False
    assert (await _state("b"))["partial"] is True


@pytest.mark.asyncio
async def test_the_record_survives_the_next_runs_per_source_delete(collection):
    """Fails on a record carrying ``source_id``: ``_delete_source_documents`` matches that key."""
    await record_run_started("A", "run-1")
    await record_run_finished("A", "run-1", "completed")
    collection.docs["problem-a"] = {"type": "problem", "source_id": "A"}
    collection.docs["problem-b"] = {"type": "problem", "source_id": "B"}

    await _delete_source_documents(collection, "run-2", "A")

    assert "problem-a" not in collection.docs  # control: the delete did run and did match A's findings
    assert "problem-b" in collection.docs
    assert "source_id" not in collection.docs["codebase_run_A"]
    state = await _state("A")
    assert state is not None and state["last_completed_at"] != ""


@pytest.mark.asyncio
async def test_a_run_with_no_source_or_a_malformed_one_records_nothing(collection):
    assert await record_run_started(None, "run-1") is False
    assert await record_run_finished(None, "run-1", "failed", "x") is False
    assert await record_run_started("*", "run-1") is False
    assert collection.docs == {}
    assert await describe_run_state(None, HARD) is None


@pytest.mark.asyncio
async def test_only_terminal_statuses_can_be_reported(collection):
    for bad in ("running", "abandoned", "bogus"):
        with pytest.raises(ValueError):
            await record_run_finished("src", "run-1", bad)


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


def test_the_two_kill_reasons_are_distinct_and_carry_the_limit_that_fired():
    watchdog = watchdog_kill_reason(310, 300)
    hard = hard_timeout_kill_reason(1800)
    assert watchdog != hard
    assert "watchdog" in watchdog and "310s" in watchdog and "limit 300s" in watchdog
    assert "hard timeout" in hard and "1800s" in hard


class _KillableProc:
    """A subprocess that runs until it is killed."""

    def __init__(self):
        self.killed = False
        self.waiting = asyncio.Event()  # set once the supervisor is waiting on the worker
        self._exited = asyncio.Event()

    async def wait(self):
        self.waiting.set()
        await self._exited.wait()
        return -9

    def kill(self):
        self.killed = True
        self._exited.set()


class _ExitedProc:
    """A worker that has already exited with ``code``."""

    def __init__(self, code):
        self._code = code

    async def wait(self):
        return self._code

    def kill(self):
        raise ProcessLookupError


def _supervisor(monkeypatch, limits: dict, redis_state, proc=None):
    """The real supervisor coroutine over ``proc`` (default: a worker that never finishes) and its task dict."""
    for name, value in limits.items():
        monkeypatch.setattr(subprocess_runner, name, value)
    monkeypatch.setattr(subprocess_runner, "_load_task_from_redis", AsyncMock(return_value=redis_state))
    spawn = AsyncMock(return_value=proc or _KillableProc())
    monkeypatch.setattr(subprocess_runner.asyncio, "create_subprocess_exec", spawn)
    tasks: dict = {}
    coroutine = subprocess_runner._run_indexing_subprocess(
        "run-2",
        "/repo",
        tasks,
        asyncio.Lock(),
        lambda: {"status": "running"},
        AsyncMock(),
        lambda task_id, error: _mark_task_failed(task_id, error, tasks),
        source_id="src",
    )
    return coroutine, tasks


async def _supervise(monkeypatch, limits: dict, redis_state, proc=None):
    """Run the supervisor to its end; a regression fails after 10 s instead of waiting on the real limits."""
    coroutine, tasks = _supervisor(monkeypatch, limits, redis_state, proc)
    await asyncio.wait_for(coroutine, 10)
    return tasks["run-2"]


@pytest.mark.asyncio
async def test_a_hard_timeout_kill_is_recorded_killed_with_its_limit(collection, monkeypatch):
    await record_run_started("src", "run-1")
    await record_run_finished("src", "run-1", "completed")
    task = await _supervise(
        monkeypatch,
        {"_SUBPROCESS_HARD_TIMEOUT": 0.05, "_SUBPROCESS_WATCHDOG_INTERVAL": 0.01},
        None,
    )
    state = await _state()
    assert task["status"] == "killed"
    assert (state["status"], state["partial"]) == ("killed", True)
    assert state["reason"] == hard_timeout_kill_reason(0.05)
    assert state["last_completed_at"] != ""


@pytest.mark.asyncio
async def test_a_watchdog_kill_is_recorded_killed_with_its_own_reason_and_limit(collection, monkeypatch):
    frozen = {"status": "running", "progress": {"current": 1, "total": 9}, "phases": {}}
    await _supervise(
        monkeypatch,
        {"_SUBPROCESS_PROGRESS_TIMEOUT": 0.05, "_SUBPROCESS_WATCHDOG_INTERVAL": 0.01},
        frozen,
    )
    state = await _state()
    assert (state["status"], state["partial"]) == ("killed", True)
    assert "progress watchdog" in state["reason"]
    assert "limit 0.05s" in state["reason"]
    assert state["reason"] != hard_timeout_kill_reason(1800)


@pytest.mark.asyncio
async def test_a_crash_that_is_not_a_kill_is_failed_with_the_exit_code(collection):
    await record_run_started("src", "run-2")
    tasks = {"run-2": {"status": "running"}}
    with patch.object(subprocess_runner, "_load_task_from_redis", AsyncMock(return_value=tasks["run-2"])):
        await subprocess_runner._handle_subprocess_crash(
            "run-2", -11, lambda t, e: _mark_task_failed(t, e, tasks), AsyncMock(), source_id="src"
        )
    state = await _state()
    assert (state["status"], state["partial"]) == ("failed", True)
    assert "exit code -11" in state["reason"]


@pytest.mark.asyncio
async def test_cancelling_the_supervisor_kills_the_worker_and_records_cancelled(collection, monkeypatch):
    proc = _KillableProc()
    coroutine, _ = _supervisor(monkeypatch, {"_SUBPROCESS_WATCHDOG_INTERVAL": 0.01}, None, proc)
    run = asyncio.ensure_future(coroutine)
    await asyncio.wait_for(proc.waiting.wait(), 10)
    assert not proc.killed  # control: the worker was running, nothing killed it yet
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(run, 10)
    state = await _state()
    assert proc.killed
    assert (state["status"], state["partial"], state["reason"]) == ("cancelled", True, "cancelled by user")
    assert await record_run_finished("src", "run-2", "completed") is False  # an orphan's late completion
    assert (await _state())["status"] == "cancelled"


@pytest.mark.asyncio
async def test_a_worker_that_cannot_be_started_is_recorded_failed(collection, monkeypatch):
    coroutine, _ = _supervisor(monkeypatch, {}, None)
    monkeypatch.setattr(
        subprocess_runner.asyncio, "create_subprocess_exec", AsyncMock(side_effect=OSError("/secret/path: no exec"))
    )
    with pytest.raises(OSError):
        await asyncio.wait_for(coroutine, 10)
    state = await _state()
    assert (state["status"], state["partial"]) == ("failed", True)
    assert "OSError" in state["reason"] and "/secret/path" not in state["reason"]


@pytest.mark.asyncio
async def test_a_completed_task_is_recorded_completed_when_the_worker_died_after_finishing(collection):
    """Hard timeout after the Redis task said ``completed`` but before the record write landed."""
    await record_run_started("src", "run-2")
    marked = []
    done = {"status": "completed"}
    with patch.object(subprocess_runner, "_load_task_from_redis", AsyncMock(return_value=done)):
        await subprocess_runner._handle_subprocess_crash(
            "run-2", -9, lambda t, e: marked.append(e), AsyncMock(), source_id="src", kill_reason="killed late"
        )
    state = await _state()
    assert (state["status"], state["partial"]) == ("completed", False)
    assert marked == []  # the task is not re-marked failed


@pytest.mark.asyncio
async def test_a_clean_exit_with_a_completed_task_backstops_the_record(collection, monkeypatch):
    await record_run_started("src", "run-2")  # the worker's own record write was lost
    done = {"status": "completed"}
    await _supervise(monkeypatch, {}, done, proc=_ExitedProc(0))
    assert (await _state())["status"] == "completed"


@pytest.mark.asyncio
async def test_a_late_completed_from_an_older_run_does_not_make_a_killed_newer_run_complete(collection):
    await record_run_started("src", "run-x")
    await record_run_started("src", "run-y")
    await record_run_finished("src", "run-y", "killed", "exit -9")
    assert await record_run_finished("src", "run-x", "completed") is False
    state = await _state()
    assert (state["run_id"], state["status"], state["partial"], state["last_completed_at"]) == (
        "run-y",
        "killed",
        True,
        "",
    )


@pytest.mark.asyncio
async def test_a_late_failure_from_an_older_run_does_not_make_a_completed_newer_run_partial(collection):
    await record_run_started("src", "run-x")
    await record_run_started("src", "run-y")
    await record_run_finished("src", "run-y", "completed")
    assert await record_run_finished("src", "run-x", "killed", "late") is False
    state = await _state()
    assert (state["run_id"], state["status"], state["partial"]) == ("run-y", "completed", False)


@pytest.mark.asyncio
async def test_the_record_remembers_only_the_last_cap_run_ids_newest_last(collection):
    ids = [f"run-{n}" for n in range(run_status.MAX_SEEN_RUN_IDS + 3)]
    for run_id in ids:
        await record_run_started("src", run_id)
    seen = run_status._decode_seen(collection.docs["codebase_run_src"])
    assert seen == ids[-run_status.MAX_SEEN_RUN_IDS :]
    assert len(seen) == run_status.MAX_SEEN_RUN_IDS


@pytest.mark.asyncio
async def test_a_record_written_before_the_field_existed_reads_as_empty_and_an_unseen_id_takes_over(collection):
    collection.docs["codebase_run_src"] = {
        "type": "run_status",
        "owner_source": "src",
        "latest_run_id": "run-1",
        "latest_status": "completed",
        "last_completed_at": "2026-11-01T00:00:00+00:00",
    }
    assert run_status._decode_seen(collection.docs["codebase_run_src"]) == []
    assert await record_run_finished("src", "run-2", "killed", "exit -9") is True
    state = await _state()
    assert (state["run_id"], state["status"]) == ("run-2", "killed")
    assert state["last_completed_at"] == "2026-11-01T00:00:00+00:00"
    assert run_status._decode_seen(collection.docs["codebase_run_src"]) == ["run-2"]


@pytest.mark.asyncio
async def test_a_naive_started_at_is_read_as_utc_not_an_error(collection):
    """Fails with ``TypeError`` on a bare ``fromisoformat`` compared to an aware ``now``."""
    collection.docs["codebase_run_src"] = {
        "latest_run_id": "run-1",
        "latest_status": "running",
        "latest_started_at": "2020-01-01T00:00:00",
    }
    assert (await _state())["status"] == "abandoned"
    collection.docs["codebase_run_src"]["latest_started_at"] = "garbage"
    assert (await _state())["status"] == "running"
