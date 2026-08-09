# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A whole-tree scan must not stall the event loop (#12866).

``asyncio.to_thread`` moves work off the loop but not off the GIL, and
``analyze_directory`` is pure-Python `re`/`ast` — neither releases it. With
``uvicorn --workers 1`` there is no second worker, so every client stalls
together: 27.5% of the GUI's 5 s status polls exceeded their budget on a healthy
box and rendered "Backend API — Unreachable".

The load-bearing test is ``test_a_scan_in_a_process_does_not_delay_the_event_loop``.
It measures how long a 5 ms heartbeat actually takes while a GIL-bound scan runs,
both ways, and compares them.

Tick *count* was tried first and does not discriminate: CPython hands the GIL
over every switch interval, so the loop keeps running under ``to_thread`` — it
just runs late. Latency does discriminate, and reproducibly:

    asyncio.to_thread    median tick 10.7ms   p95 11.3-15.9ms
    ProcessPoolExecutor  median tick  5.3ms   p95  5.5ms

against a 5 ms request. That per-wakeup tax, compounded across every await in a
request, is how a 25 ms endpoint became a 12 s one. Everything else here is a
property of the plumbing — this is the property the issue is about.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from code_intelligence.shared import process_offload
from code_intelligence.shared.process_offload import (
    run_directory_scan,
    run_isolated,
    shutdown_scan_pool,
)

pytestmark = pytest.mark.asyncio


class _FakeAnalyzer:
    """Stands in for a BaseCodeAnalyzer subclass.

    Module-level (not nested in a test) because a spawned child re-imports this
    module to unpickle the class — a locally defined one is unpicklable.
    """

    def __init__(self, project_root=None, exclude_patterns=None, use_semantic_analysis=False):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.exclude_patterns = list(exclude_patterns or [])
        self.use_semantic_analysis = use_semantic_analysis
        self.results = []
        self.total_files_scanned = 0

    def analyze_directory(self, directory=None):
        self.results = [f"finding:{self.project_root.name}", f"dir:{directory}"]
        self.total_files_scanned = 7
        return self.results

    def get_summary(self):
        return {"total": len(self.results), "files_analyzed": self.total_files_scanned}


class _BurnCPU:
    """A deliberately GIL-bound workload, for the responsiveness test."""

    def __init__(self, project_root=None, exclude_patterns=None, use_semantic_analysis=False):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.exclude_patterns = list(exclude_patterns or [])
        self.results = []
        self.total_files_scanned = 0

    def analyze_directory(self, directory=None):
        # Pure-Python arithmetic: holds the GIL exactly like a regex scan does.
        total = 0
        for i in range(4_000_000):
            total += i * i
        self.results = [total]
        self.total_files_scanned = 1
        return self.results


class _Boom:
    def __init__(self, **_kwargs):
        pass

    def analyze_directory(self, directory=None):
        raise RuntimeError("scan exploded in the child")


@pytest.fixture(autouse=True)
async def _fresh_pool():
    """Each test gets a pool it can break without affecting the next."""
    await shutdown_scan_pool()
    process_offload._pool_unavailable_reason = None
    yield
    await shutdown_scan_pool()
    process_offload._pool_unavailable_reason = None


async def test_scan_result_and_file_count_both_cross_the_process_boundary():
    """Returning findings alone would misreport ``files_analyzed``.

    ``get_summary()`` falls back to counting *distinct files that had a finding*
    when ``total_files_scanned`` is 0 — so a scan of 7 files reporting 2 findings
    in 1 file would claim it analysed 1 file. Silently wrong, never raised.
    """
    analyzer = _FakeAnalyzer(project_root="/tmp/example")

    results = await run_directory_scan(analyzer)

    assert results == ["finding:example", "dir:None"]
    assert analyzer.results == results, "the caller's analyzer must carry the child's findings"
    assert analyzer.total_files_scanned == 7, "the scanned-file count must survive the hop"
    assert analyzer.get_summary() == {"total": 2, "files_analyzed": 7}


async def test_directory_argument_reaches_the_child():
    analyzer = _FakeAnalyzer(project_root="/tmp/example")
    await run_directory_scan(analyzer, "/tmp/example/sub")
    assert analyzer.results[1] == "dir:/tmp/example/sub"


async def test_semantic_analysis_is_off_in_the_child():
    """Semantic analysis holds Redis/ChromaDB handles, which do not pickle.

    ``analyze_directory`` is regex+AST only — the semantic path is
    ``analyze_directory_async`` — so a worker never needs it, and constructing it
    there would open connections from a short-lived process.
    """
    captured = {}

    class _Recorder(_FakeAnalyzer):
        def __init__(self, **kwargs):
            captured.update(kwargs)
            super().__init__(**kwargs)

    # Called directly rather than through the pool: the assertion is about the
    # kwargs the child constructor receives, and a spawned child cannot write
    # back into this process's dict.
    process_offload._scan_in_child(_Recorder, "/tmp/example", ["venv"], None)

    assert captured["use_semantic_analysis"] is False
    assert captured["project_root"] == "/tmp/example"
    assert captured["exclude_patterns"] == ["venv"]


async def _median_tick_delay_during_scan(force_thread: bool) -> float:
    """Median time a 5 ms heartbeat actually takes while a GIL-bound scan runs."""
    await shutdown_scan_pool()
    process_offload._pool_unavailable_reason = "forced for measurement" if force_thread else None

    delays: list[float] = []
    stop = False

    async def heartbeat():
        while not stop:
            started = time.monotonic()
            await asyncio.sleep(0.005)
            delays.append(time.monotonic() - started)

    beat = asyncio.create_task(heartbeat())
    await asyncio.sleep(0.05)
    await run_directory_scan(_BurnCPU(project_root="/tmp"))  # warm the pool
    delays.clear()

    await run_directory_scan(_BurnCPU(project_root="/tmp"))

    stop = True
    beat.cancel()
    await shutdown_scan_pool()
    process_offload._pool_unavailable_reason = None

    assert delays, "the heartbeat never ran — measurement is meaningless"
    return sorted(delays)[len(delays) // 2]


async def test_a_scan_in_a_process_does_not_delay_the_event_loop():
    """The property #12866 is about, measured against the old behaviour.

    Tick *count* does not discriminate: CPython hands the GIL over every switch
    interval, so the loop still runs — it just runs *late*. Measured here, a 5 ms
    sleep takes ~10.7 ms under ``asyncio.to_thread`` and ~5.3 ms under the pool.
    That per-wakeup tax, compounded across a request's awaits, is how a 25 ms
    endpoint became a 12 s one.

    Compared within the test rather than against a fixed threshold, so a loaded
    CI runner shifts both numbers together instead of flaking.
    """
    in_thread = await _median_tick_delay_during_scan(force_thread=True)
    in_process = await _median_tick_delay_during_scan(force_thread=False)

    if process_offload._pool_unavailable_reason:
        pytest.skip(f"process pool unavailable here: {process_offload._pool_unavailable_reason}")

    # Measured ratio is ~0.5; 0.75 leaves headroom while still failing outright
    # if the scan ever stops being isolated.
    assert in_process < in_thread * 0.75, (
        f"a scan still delays the event loop: {in_process * 1000:.1f}ms median tick "
        f"in-process vs {in_thread * 1000:.1f}ms in-thread — expected a clear improvement"
    )
    # And in absolute terms the loop should be barely taxed at all.
    assert in_process < 0.005 * 1.5, (
        f"a 5ms heartbeat took {in_process * 1000:.1f}ms median while a scan ran in "
        "another process — something is still contending for this process"
    )


async def test_run_isolated_forwards_args_and_kwargs():
    """The non-BaseCodeAnalyzer scanners take positional and keyword arguments."""

    result = await run_isolated(
        _FakeAnalyzer, {"project_root": "/tmp/example"}, "analyze_directory", "/tmp/example/sub"
    )
    assert result == ["finding:example", "dir:/tmp/example/sub"]


async def test_a_failed_scan_does_not_poison_every_later_request():
    """A dead child breaks the whole pool — every later submit raises BrokenProcessPool.

    So the pool is dropped on failure and the next request gets a fresh one.
    Without this, one OOM-killed scan bricks code-intelligence until restart.
    """
    with pytest.raises(RuntimeError):
        await run_isolated(_Boom, {}, "analyze_directory")

    analyzer = _FakeAnalyzer(project_root="/tmp/example")
    await run_directory_scan(analyzer)
    assert analyzer.total_files_scanned == 7, "the pool did not recover after a failed scan"


async def test_falls_back_in_thread_when_the_pool_cannot_start():
    """Some sandboxes forbid process creation.

    Failing every code-intelligence endpoint there would be worse than the stalls
    this exists to prevent — but the fallback is logged, never silent.
    """
    await shutdown_scan_pool()
    process_offload._pool_unavailable_reason = "forced for test"

    analyzer = _FakeAnalyzer(project_root="/tmp/example")
    results = await run_directory_scan(analyzer)

    assert results == ["finding:example", "dir:None"]
    assert analyzer.total_files_scanned == 7, "the in-thread path must populate state too"


async def test_shutdown_is_idempotent():
    """Called from the lifespan and again after a failed scan."""
    await run_directory_scan(_FakeAnalyzer(project_root="/tmp/example"))
    await shutdown_scan_pool()
    await shutdown_scan_pool()
    assert process_offload._pool is None
