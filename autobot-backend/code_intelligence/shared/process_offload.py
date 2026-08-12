# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Run a whole-tree analyzer scan in a separate PROCESS (#12866).

``asyncio.to_thread`` moves work off the event *loop* but not off the *GIL*.
``BaseCodeAnalyzer.analyze_directory`` is pure-Python `re` and `ast` over every
file in the tree, and neither releases the GIL — so the worker thread holds it in
long stretches and the loop cannot run. With ``uvicorn --workers 1`` (the
canonical unit) there is no second worker to absorb requests, so *every* client
stalls together.

Measured on an idle single-box host, 40 samples of ``/api/service-monitor/vms/status``
at 4 s intervals:

    min=0.09s   p50=0.85s   p90=12.00s   max=>=12.00s (client ceiling)
    >2s: 15/40      >5s: 11/40 = 27.5%

while a calm window minutes later served 12/12 in 0.020-0.036 s. The endpoint is
not slow; the process stalls in bursts. ``py-spy`` caught the cause mid-stall:

    _check_sql_injection (code_intelligence/security/analyzer.py)
    _regex_analysis      (code_intelligence/shared/analysis_base.py)
    analyze_directory    (code_intelligence/shared/analysis_base.py)
    run                  (concurrent/futures/thread.py)

A separate process has its own GIL, so the API process stays responsive for the
whole scan. That fixes every endpoint at once, with no change to any response
shape — the alternative (a Celery task per endpoint) would turn five synchronous
findings responses into enqueue-and-poll and require matching frontend work.

The scan is reconstructed in the child rather than pickled: an analyzer instance
can hold Redis/ChromaDB handles from semantic analysis, which are not picklable
and have no business in a scan worker. ``analyze_directory`` is purely regex+AST
anyway — semantic work lives in ``analyze_directory_async`` — so the child is
given only ``project_root`` and ``exclude_patterns``.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from typing import Any, List, Tuple, Type

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

__all__ = ["run_directory_scan", "run_isolated", "shutdown_scan_pool"]

# One worker is enough to keep the API process free; the point is isolation from
# the GIL, not parallelism within a scan. More workers would multiply RSS (a scan
# was measured growing the parent 1.58 GB -> 3.14 GB) for no latency win, since
# analyze_directory is single-threaded.
_MAX_WORKERS = max(1, int(os.getenv("AUTOBOT_CODE_ANALYSIS_POOL_WORKERS", "2")))

# Recycle workers so a leaked reference inside a scan cannot accumulate across
# requests. The scans are seconds long, so the respawn cost is noise.
_MAX_TASKS_PER_CHILD = max(1, int(os.getenv("AUTOBOT_CODE_ANALYSIS_POOL_MAX_TASKS", "8")))

_pool: ProcessPoolExecutor | None = None
_pool_lock = asyncio.Lock()

#: Set when the pool could not be created. Some container/sandbox configurations
#: forbid process creation entirely; failing every code-intelligence endpoint
#: there would be a worse outcome than the stalls this exists to prevent, so the
#: scan runs in-thread instead. Logged at WARNING once, never silent — a host in
#: this state still has the #12866 stalls and the log is how that is known.
_pool_unavailable_reason: str | None = None


def _scan_in_child(
    analyzer_cls: Type[Any],
    project_root: str | None,
    exclude_patterns: List[str] | None,
    directory: str | None,
) -> Tuple[List[Any], int]:
    """Reconstruct the analyzer in this process and run the scan.

    Returns ``(results, total_files_scanned)``. Both are needed: the caller's
    ``get_summary()`` reads ``self.results`` *and* ``self.total_files_scanned``,
    so returning findings alone would silently report ``files_analyzed`` as the
    count of distinct files that happened to have a finding.
    """
    analyzer = analyzer_cls(
        project_root=project_root,
        exclude_patterns=exclude_patterns,
        use_semantic_analysis=False,
    )
    results = analyzer.analyze_directory(directory)
    return results, analyzer.total_files_scanned


async def _get_pool() -> ProcessPoolExecutor | None:
    """Lazily create the shared pool; ``None`` means run in-thread instead."""
    global _pool, _pool_unavailable_reason

    if _pool is not None:
        return _pool
    if _pool_unavailable_reason is not None:
        return None

    async with _pool_lock:
        if _pool is not None:
            return _pool
        if _pool_unavailable_reason is not None:
            return None

        try:
            kwargs: dict[str, Any] = {
                "max_workers": _MAX_WORKERS,
                # "spawn", never "fork": forking a process that already has an
                # event loop and worker threads copies their state into a child
                # that never runs them, which deadlocks on any lock held at the
                # moment of the fork.
                "mp_context": multiprocessing.get_context("spawn"),
            }
            if "max_tasks_per_child" in ProcessPoolExecutor.__init__.__code__.co_varnames:
                kwargs["max_tasks_per_child"] = _MAX_TASKS_PER_CHILD
            _pool = ProcessPoolExecutor(**kwargs)
            logger.info(
                "Code-analysis process pool started (workers=%d, max_tasks_per_child=%s)",
                _MAX_WORKERS,
                kwargs.get("max_tasks_per_child", "unsupported"),
            )
            return _pool
        except (OSError, ValueError, ImportError) as exc:
            _pool_unavailable_reason = str(exc)
            logger.warning(
                "Code-analysis process pool unavailable (%s); falling back to a worker "
                "thread. Scans will hold the GIL and stall this process for their "
                "duration — the #12866 symptom is expected on this host.",
                exc,
            )
            return None


def _call_in_child(
    cls: Type[Any],
    init_kwargs: dict,
    method_name: str,
    args: tuple,
    kwargs: dict,
) -> Any:
    """Construct ``cls`` in this process and return one method call's result."""
    return getattr(cls(**init_kwargs), method_name)(*args, **kwargs)


async def run_isolated(
    cls: Type[Any],
    init_kwargs: dict,
    method_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run one scan method of a freshly constructed ``cls`` in a separate process.

    For scanners that are not ``BaseCodeAnalyzer`` subclasses (``AntiPatternDetector``,
    ``RedisOptimizer``) and whose callers use only the return value — so there is
    no instance state to carry back across the process boundary.

    Everything passed must be picklable, which is why the class and its
    constructor arguments are passed rather than an instance: a live scanner can
    hold handles that are not.
    """
    pool = await _get_pool()
    target = getattr(cls(**init_kwargs), method_name) if pool is None else None

    if pool is None:
        return await asyncio.to_thread(lambda: target(*args, **kwargs))

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(pool, _call_in_child, cls, init_kwargs, method_name, args, kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.error("Isolated %s.%s failed in the worker process: %s", cls.__name__, method_name, exc)
        await shutdown_scan_pool()
        raise


async def run_directory_scan(analyzer: Any, directory: str | None = None) -> List[Any]:
    """Scan a tree without stalling the event loop, and populate ``analyzer``.

    Drop-in for ``await asyncio.to_thread(analyzer.analyze_directory)``: the
    caller keeps using ``analyzer.get_summary()`` and the returned findings
    exactly as before.
    """
    pool = await _get_pool()

    if pool is None:
        return await asyncio.to_thread(analyzer.analyze_directory, directory)

    loop = asyncio.get_running_loop()
    try:
        results, files_scanned = await loop.run_in_executor(
            pool,
            _scan_in_child,
            type(analyzer),
            str(analyzer.project_root),
            list(analyzer.exclude_patterns),
            directory,
        )
    except Exception as exc:  # noqa: BLE001
        # A child that dies (OOM kill, segfault in a C extension) breaks the
        # whole pool: every later submission raises BrokenProcessPool. Drop it so
        # the next request gets a fresh one instead of failing forever.
        logger.error("Code-analysis scan failed in the worker process: %s", exc)
        await shutdown_scan_pool()
        raise

    # The child's analyzer is gone; the caller's must carry its state, or
    # get_summary() reports an empty scan of a tree that was fully scanned.
    analyzer.results = results
    analyzer.total_files_scanned = files_scanned
    return results


async def shutdown_scan_pool() -> None:
    """Tear the pool down (app shutdown, or after a worker died)."""
    global _pool

    async with _pool_lock:
        if _pool is None:
            return
        pool, _pool = _pool, None

    # shutdown() joins the worker processes, which blocks — keep it off the loop.
    await asyncio.to_thread(pool.shutdown, wait=False, cancel_futures=True)
    logger.info("Code-analysis process pool shut down")
