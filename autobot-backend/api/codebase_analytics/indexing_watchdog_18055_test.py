# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for #18055 — indexing killed by its own watchdog.

Background: ``_store_problems_batch_to_chromadb`` built one list of every
problem in the tree and issued a single unbounded ``upsert``.  That one
``await`` emitted no progress update for its whole duration, so on a large
repo the subprocess watchdog (#1341) read the frozen progress counters as a
hang and SIGKILLed the worker mid-write.  The scan completed, nothing was
persisted, ``last_indexed`` stayed null, and ``/stats`` reported ``no_data``.

Two boundaries are asserted here, both of which the pre-#18055 code crosses:

1. the number of ``upsert`` calls and progress ticks must scale with the
   problem count, not collapse to one;
2. the watchdog must treat a phase transition as liveness, while still
   killing a run that shows neither progress nor a phase change.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from api.codebase_analytics import problem_storage, subprocess_runner
from api.codebase_analytics.problem_storage import _store_problems_batch_to_chromadb


def _problems(n: int) -> list:
    return [{"type": "smell", "file_path": f"f{i}.py", "line": i, "message": "m"} for i in range(n)]


class _Recorder:
    """Captures each progress tick the store emits."""

    def __init__(self):
        self.ticks = []

    async def __call__(self, operation, current, total, current_file, **kwargs):
        self.ticks.append((operation, current, total))


@pytest.mark.asyncio
async def test_bulk_store_is_chunked_not_one_unbounded_upsert(monkeypatch):
    """The upsert count must track the problem count — the #18055 boundary.

    Pre-#18055 this is exactly 1 upsert for any input size, which is the
    defect: one unbounded, unreported await.
    """
    monkeypatch.setattr(problem_storage, "CHROMADB_BATCH_SIZE", 10)
    collection = AsyncMock()
    problems = _problems(35)

    await _store_problems_batch_to_chromadb(collection, problems, 0, source_id="src")

    assert collection.upsert.await_count == 4, "35 problems at a chunk size of 10 must take 4 upserts"
    sizes = [len(c.kwargs["ids"]) for c in collection.upsert.await_args_list]
    assert sizes == [10, 10, 10, 5]


@pytest.mark.asyncio
async def test_each_chunk_ticks_the_watchdog(monkeypatch):
    """Every chunk reports progress, so no chunk boundary is a silent window."""
    monkeypatch.setattr(problem_storage, "CHROMADB_BATCH_SIZE", 10)
    collection = AsyncMock()
    recorder = _Recorder()

    await _store_problems_batch_to_chromadb(collection, _problems(35), 0, source_id="src", progress_callback=recorder)

    assert [t[1] for t in recorder.ticks] == [10, 20, 30, 35]
    assert all(t[2] == 35 for t in recorder.ticks)
    assert {t[0] for t in recorder.ticks} == {"Storing problems"}


@pytest.mark.asyncio
async def test_document_ids_stay_unique_across_chunks(monkeypatch):
    """Chunking must not restart the index and collide doc ids."""
    monkeypatch.setattr(problem_storage, "CHROMADB_BATCH_SIZE", 10)
    collection = AsyncMock()

    await _store_problems_batch_to_chromadb(collection, _problems(35), 0, source_id="src")

    seen = [i for call in collection.upsert.await_args_list for i in call.kwargs["ids"]]
    assert len(seen) == 35
    assert len(set(seen)) == 35, "chunk offset must carry into the document id"


@pytest.mark.asyncio
async def test_one_failing_chunk_does_not_discard_the_others(monkeypatch):
    """A single failure used to lose the whole run; it must now lose one chunk."""
    monkeypatch.setattr(problem_storage, "CHROMADB_BATCH_SIZE", 10)
    collection = AsyncMock()
    calls = {"n": 0}

    async def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("transient write error")

    collection.upsert = AsyncMock(side_effect=flaky)

    stored = await _store_problems_batch_to_chromadb(collection, _problems(35), 0, source_id="src")

    assert collection.upsert.await_count == 4, "the run continues past a failing chunk"
    # The count must exclude the failed chunk. Reporting len(problems) here
    # would log more persisted than exists -- the caller logs this number.
    assert stored == 25, f"35 problems with one failed chunk of 10 is 25 stored, got {stored}"


@pytest.mark.asyncio
async def test_a_missing_source_id_fails_the_run_rather_than_storing_nothing(monkeypatch):
    """Fail closed, deliberately -- a behaviour change worth pinning.

    Document preparation now runs outside the per-chunk ``except``, so
    ``require_source_id``'s ValueError propagates instead of being logged as a
    storage failure.  The old path reported "completed, 0 problems stored" for
    a run that wrote nothing scoped, which is the unscoped-namespace defect
    #17758 exists to prevent.  If this ever starts passing silently again, the
    swallow is back.
    """
    monkeypatch.setattr(problem_storage, "CHROMADB_BATCH_SIZE", 10)
    collection = AsyncMock()

    with pytest.raises(ValueError, match="source_id"):
        await _store_problems_batch_to_chromadb(collection, _problems(5), 0, source_id=None)

    collection.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_upsert_failure_is_still_only_a_chunk(monkeypatch):
    """The fail-closed change must not have made write errors fatal too."""
    monkeypatch.setattr(problem_storage, "CHROMADB_BATCH_SIZE", 10)
    collection = AsyncMock()
    collection.upsert = AsyncMock(side_effect=RuntimeError("write error"))

    await _store_problems_batch_to_chromadb(collection, _problems(25), 0, source_id="src")

    assert collection.upsert.await_count == 3, "every chunk is still attempted"


# ---------------------------------------------------------------------------
# Watchdog liveness
# ---------------------------------------------------------------------------


class _FakeProc:
    """A subprocess that runs until it is killed or told it finished."""

    def __init__(self):
        self.killed = False
        self._exited = asyncio.Event()

    async def wait(self):
        if self.killed:
            return -9
        await self._exited.wait()
        return -9 if self.killed else 0

    def kill(self):
        self.killed = True
        self._exited.set()

    def finish(self):
        """Mirror a real subprocess exiting once its task state is terminal."""
        self._exited.set()


async def _run_watchdog(monkeypatch, states):
    """Drive the watchdog over a scripted sequence of Redis task states."""
    monkeypatch.setattr(subprocess_runner, "_SUBPROCESS_WATCHDOG_INTERVAL", 0.01)
    monkeypatch.setattr(subprocess_runner, "_SUBPROCESS_PROGRESS_TIMEOUT", 0.05)

    seq = list(states)
    proc = _FakeProc()

    async def fake_load(_task_id):
        state = seq.pop(0) if seq else states[-1]
        if state.get("status") in ("completed", "failed", "cancelled"):
            proc.finish()
        return state

    monkeypatch.setattr(subprocess_runner, "_load_task_from_redis", fake_load)
    rc = await asyncio.wait_for(subprocess_runner._wait_with_watchdog(proc, "t1"), timeout=5)
    return rc, proc


@pytest.mark.asyncio
async def test_phase_transition_counts_as_liveness(monkeypatch):
    """Frozen counters plus a moving phase is a live run, not a hang.

    This is the exact shape that killed every real indexing run: the per-file
    loop stops updating ``progress`` and the work moves on by phase.
    """
    frozen = {"current": 11055, "total": 11055, "operation": "Aggregating results"}
    states = [
        {"status": "running", "progress": frozen, "phases": {"current_phase": "scan", "phases_completed": []}},
    ]
    # Phase keeps advancing while the counters never move.
    for i in range(40):
        states.append(
            {
                "status": "running",
                "progress": frozen,
                "phases": {"current_phase": f"p{i}", "phases_completed": [f"p{j}" for j in range(i)]},
            }
        )
    states.append({"status": "completed", "progress": frozen, "phases": {"current_phase": "finalize"}})

    rc, proc = await _run_watchdog(monkeypatch, states)

    assert not proc.killed, "a run advancing its phase must not be killed"
    assert rc != -9


@pytest.mark.asyncio
async def test_a_genuine_hang_is_still_killed(monkeypatch):
    """Neither counters nor phase moving is still a hang — #1341 must hold."""
    stuck = {
        "status": "running",
        "progress": {"current": 1, "total": 2, "operation": "stuck"},
        "phases": {"current_phase": "scan", "phases_completed": []},
    }

    rc, proc = await _run_watchdog(monkeypatch, [stuck])

    assert proc.killed, "the hang detector must still fire"
    assert rc == -9
