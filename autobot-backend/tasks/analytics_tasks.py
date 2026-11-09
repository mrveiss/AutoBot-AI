# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Celery tasks for analytics background work (GH#6505).

Replaces the seven BackgroundTaskManager-based async workers with
canonical Celery tasks.  Each task uses ``bind=True`` so it can call
``self.update_state()`` for granular progress reporting compatible
with the existing ``celery_task_status.celery_result_to_status`` helper.

Async workers are wrapped via ``_run_async`` (the persistent worker loop, #20887).
"""

import asyncio
import contextvars
import functools
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from autobot_shared.logging_manager import get_logger
from autobot_shared.worker_loop import run_in_worker_loop
from celery_app import celery_app

logger = get_logger(__name__)

_PATTERN_CHECKPOINT_PREFIX = "pattern_complete_checkpoint:"
_CHECKPOINT_TTL = 3600  # 1 h — recent-enough to resume from


def _path_checkpoint_key(path: str, source_id: str | None = None) -> str:
    """Issue #12384: fold source_id into the checkpoint key. Without this, two
    different sources resolving to the same scan path (e.g. both default to
    AutoBot's own PATH.PROJECT_ROOT) would return each other's cached
    analysis result -- bypassing the ChromaDB source_id tag entirely on a
    checkpoint-hit retry.
    """
    tag = source_id or "default"
    return f"{_PATTERN_CHECKPOINT_PREFIX}{hashlib.sha256(f'{tag}:{path}'.encode()).hexdigest()[:16]}"


async def _load_path_checkpoint(path: str, source_id: str | None = None) -> dict | None:
    """Return a previously-saved completed analysis result for *path*/*source_id*, or None (GH#8439)."""
    try:
        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client(database="analytics")
        if not redis:
            return None
        raw = await redis.get(_path_checkpoint_key(path, source_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def _save_path_checkpoint(path: str, result: dict, source_id: str | None = None) -> None:
    """Persist *result* as the checkpoint for *path*/*source_id* (GH#8439)."""
    try:
        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client(database="analytics")
        if redis:
            await redis.set(_path_checkpoint_key(path, source_id), json.dumps(result, default=str), ex=_CHECKPOINT_TTL)
    except Exception:
        pass


# One fresh token per ``_drain_after`` call. A task spawned while the coroutine runs inherits it, so the
# drain waits only for its own run's tasks; the worker loop is shared and persistent, and other runs'
# (or other subsystems') tasks live on it too.
_OP: contextvars.ContextVar[object | None] = contextvars.ContextVar("analytics_op", default=None)


async def _drain_after(coro):
    """Await *coro*, then drain the fire-and-forget tasks it spawned (GH#8434), and only those."""
    token = object()
    _OP.set(token)
    result = await coro
    current = asyncio.current_task()
    pending = [
        t for t in asyncio.all_tasks() if t is not current and not t.done() and t.get_context().get(_OP) is token
    ]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    return result


# #20887: Celery keeps the running task's request in thread-local storage, and the
# coroutine now runs on the worker-loop thread. The id is bound on the task thread by
# ``_binds_task_id`` and travels in this ContextVar (call_soon_threadsafe copies the caller's context).
_TASK_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar("analytics_task_id", default=None)


def _binds_task_id(func):
    """Bind ``_TASK_ID`` from ``self.request.id`` for the whole task body, then restore the previous value.

    Without it the first ``_progress`` call, made before ``_run_async``, would address the previous task
    run on this thread.
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        token = _TASK_ID.set(getattr(getattr(self, "request", None), "id", None))
        try:
            return func(self, *args, **kwargs)
        finally:
            _TASK_ID.reset(token)

    return wrapper


def _run_async(coro):
    """Run *coro* on the worker's persistent loop (Celery workers are sync, #20887)."""
    return run_in_worker_loop(_drain_after(coro))


def _progress(self, step: str, pct: float, started_at: str | None = None) -> None:
    """Emit a PROGRESS state update on the bound Celery task *self*."""
    meta: dict = {"step": step, "progress": pct}
    if started_at:
        meta["started_at"] = started_at
    self.update_state(task_id=_TASK_ID.get(), state="PROGRESS", meta=meta)


def _wrap(result: object, started: str) -> dict:
    """Wrap analysis *result* in the standard success envelope."""
    return {
        "result": result,
        "started_at": started,
        "completed_at": datetime.now(tz=timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# 1. Import tree (api/codebase_analytics/endpoints/import_tree.py)
# ---------------------------------------------------------------------------


async def _scan_root_or_refusal(source_id: "str | None") -> "tuple[Path | None, dict | None]":
    """The scan root for *source_id*, or the dict a task should return instead (#17758).

    A source that does not resolve to a checkout -- named but gone, or not named at
    all, as the scheduler dispatches it -- is a refusal, never AutoBot's own
    repository scanned under another project's key (#20513).

    One definition because three tasks need it, and three copies of a scoping
    decision is precisely how #17758 happened: the same shape in three places,
    converted in none. The duplication guard caught my own second and third
    copies here, which is the guard doing its job.
    """
    from api.codebase_analytics.endpoints.shared import UnresolvedSourceError, resolve_scan_root

    try:
        return await resolve_scan_root(source_id), None
    except UnresolvedSourceError as exc:
        return None, {"status": "error", "message": f"{exc.detail}; nothing scanned"}


async def _confirmed_dir_or_refusal(
    source_id: str, path: str, expect: "str | None" = None
) -> "tuple[str | None, dict | None]":
    """The real directory *path* now is inside *source_id*, or the refusal dict a task should return (#20513).

    With *expect*, also refuses when the real directory is no longer that one -- the post-scan check
    that keeps a result produced from a directory swapped mid-scan from being returned or cached.
    """
    from api.codebase_analytics.endpoints.shared import UnresolvedSourceError, confirm_scan_dir_in_source

    try:
        real = await confirm_scan_dir_in_source(source_id, path)
    except (UnresolvedSourceError, ValueError) as exc:
        return None, {"status": "error", "message": f"{getattr(exc, 'detail', exc)}; nothing scanned"}
    if expect is not None and real != expect:
        return None, {"status": "error", "message": "The scan directory changed during the scan; result discarded"}
    return real, None


@celery_app.task(bind=True, name="analytics.run_import_tree_analysis")
@_binds_task_id
def run_import_tree_analysis(self, source_id: "str | None" = None) -> dict:
    """Celery wrapper for import tree background analysis (#6505).

    ``source_id`` scopes the scan (#17758). Before this, the three analytics
    tasks resolved a root three different ways and none of them was
    source-aware, so whichever project triggered a scan got AutoBot's own tree
    analysed and every project's cached read was served from it.
    ``resolve_scan_root`` is the resolver #12330 built for exactly this, and
    these tasks -- living outside ``api/codebase_analytics/`` -- were missed by
    that sweep and the two after it.
    """
    started = datetime.now(tz=timezone.utc).isoformat()
    _progress(self, "Scanning project files", 10.0, started)

    async def _work():
        from typing import Dict, List

        from api.codebase_analytics.endpoints.import_tree import (
            _analyze_file_imports,
            _build_import_tree,
            _build_module_to_file_mapping,
            _build_summary,
        )

        root, refusal = await _scan_root_or_refusal(source_id)
        if refusal is not None:
            return refusal
        project_root = Path(root)
        excluded = {"__pycache__", "node_modules", ".venv", "venv", ".env", "archive", "dist", "build"}
        python_files = await asyncio.to_thread(lambda: list(project_root.rglob("*.py")))
        python_files = [f for f in python_files if not any(ex in f.parts for ex in excluded)]

        file_imports: Dict[str, List[Dict]] = {}
        file_imported_by: Dict[str, List[Dict]] = {}
        module_to_file = _build_module_to_file_mapping(python_files, project_root)

        _progress(self, "Analyzing file imports", 50.0, started)
        for py_file in python_files[:500]:
            await _analyze_file_imports(py_file, project_root, module_to_file, file_imports, file_imported_by)

        _progress(self, "Building import tree", 80.0, started)
        import_tree = _build_import_tree(file_imports, file_imported_by)
        return {"status": "success", "import_tree": import_tree, "summary": _build_summary(import_tree)}

    return _wrap(_run_async(_work()), started)


# ---------------------------------------------------------------------------
# 2. Duplicate code (api/codebase_analytics/endpoints/duplicates.py)
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="analytics.run_duplicate_analysis")
@_binds_task_id
def run_duplicate_analysis(self, source_id: "str | None" = None) -> dict:
    """Celery wrapper for duplicate code background analysis (#6505).

    ``source_id`` scopes the scan (#17758) -- see ``run_import_tree_analysis``.
    """
    started = datetime.now(tz=timezone.utc).isoformat()
    _progress(self, "Running duplicate analysis", 20.0, started)

    async def _work():
        from api.codebase_analytics.endpoints.duplicates import _process_and_cache_analysis, _run_duplicate_analysis

        root, refusal = await _scan_root_or_refusal(source_id)
        if refusal is not None:
            return refusal
        project_root = str(root)
        # background=True: bounded by a runaway limit, not the 120 s request
        # deadline. ScanBusy / ScanTimedOut propagate, so Celery records FAILURE
        # instead of a "completed" task carrying a partial result (#18067).
        analysis = await _run_duplicate_analysis(project_root, 0.5, False, background=True)
        if analysis.files_analyzed == 0:
            # "Examined nothing" is not "found nothing" (#17982).
            return {"status": "error", "message": "no source files found under the scan root; nothing scanned"}
        _progress(self, "Processing results", 80.0, started)
        return _process_and_cache_analysis(analysis, project_root, source_id=source_id)

    return _wrap(_run_async(_work()), started)


# ---------------------------------------------------------------------------
# 3. Dependency analysis (api/codebase_analytics/endpoints/dependencies.py)
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="analytics.run_dependency_analysis")
@_binds_task_id
def run_dependency_analysis(self, source_id: "str | None" = None) -> dict:
    """Celery wrapper for dependency background analysis (#6505).

    ``source_id`` scopes the scan (#17758) -- see ``run_import_tree_analysis``.
    """
    started = datetime.now(tz=timezone.utc).isoformat()
    _progress(self, "Loading ChromaDB modules", 10.0, started)

    async def _work():
        from typing import Dict, List

        from api.codebase_analytics.endpoints.dependencies import (
            _build_module_index,
            _build_visualization_graph,
            _detect_circular_deps,
            _load_modules_from_chromadb,
            _scan_filesystem_imports,
        )
        from api.codebase_analytics.storage import get_code_collection

        code_collection = await asyncio.to_thread(get_code_collection)
        modules: Dict[str, Dict] = {}
        import_relationships: List[Dict] = []
        external_deps: Dict[str, int] = {}
        runtime_rels: List[Dict] = []

        # Resolve the root first: a source without a checkout gets the shared refusal whether or
        # not the collection is reachable (require_source_id would otherwise raise first).
        root, refusal = await _scan_root_or_refusal(source_id)
        if refusal is not None:
            return refusal
        if code_collection:
            # #17758: the indexed read is scoped too -- the filesystem scan and the
            # ChromaDB query are two separate leaks and fixing one leaves the other.
            await _load_modules_from_chromadb(code_collection, modules, source_id)

        _progress(self, "Scanning filesystem imports", 30.0, started)
        # get_project_root() was the hardcoded parents[4] here. #12393 already
        # established that resolves to the install directory in the deployed
        # layout -- not a repository -- so this task scanned the wrong tree in
        # production independently of any scoping question.
        project_root = root
        await _scan_filesystem_imports(project_root, modules, import_relationships, external_deps, runtime_rels)

        _progress(self, "Detecting circular dependencies", 70.0, started)
        module_index = _build_module_index(modules)
        circular_deps = _detect_circular_deps(runtime_rels, module_index)

        _progress(self, "Building visualization", 90.0, started)
        return _build_visualization_graph(modules, import_relationships, external_deps, circular_deps)

    return _wrap(_run_async(_work()), started)


# ---------------------------------------------------------------------------
# 4. Pattern analysis (api/codebase_analytics/endpoints/pattern_analysis.py)
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="analytics.run_pattern_analysis")
@_binds_task_id
def run_pattern_analysis(self, request_data: dict) -> dict:
    """Celery wrapper for pattern analysis background job (#6505, GH#8439).

    GH#8439: saves a path-scoped checkpoint after successful completion so
    that a retry (new task ID, same path) can resume from the cached result
    instead of restarting from zero.
    """
    from api.codebase_analytics.endpoints.pattern_analysis import (
        _ANALYSIS_TIMEOUT,
        PatternAnalysisRequest,
    )

    started = datetime.now(tz=timezone.utc).isoformat()
    request = PatternAnalysisRequest(**request_data)
    _progress(self, "Initializing", 0.0, started)

    async def _work():
        from code_intelligence.pattern_analysis import CodePatternAnalyzer

        # The route validated the directory at queue time; confirm it again now, before anything
        # (including a cached result) is served, and key the checkpoint on the confirmed path (#20513).
        scan_dir, refusal = await _confirmed_dir_or_refusal(request.source_id, request.path)
        if refusal is not None:
            return refusal

        # Resume from checkpoint if analysis for this path was recently completed.
        saved = await _load_path_checkpoint(scan_dir, request.source_id)
        if saved:
            logger.info("run_pattern_analysis: resuming from checkpoint for path %s", scan_dir)
            _progress(self, "Loaded from checkpoint", 100.0, started)
            return saved

        async def _on_progress(step: str, progress: float) -> None:
            _progress(self, step, progress, started)

        analyzer = CodePatternAnalyzer(
            enable_clone_detection=request.enable_clone_detection,
            enable_anti_pattern_detection=request.enable_anti_pattern_detection,
            enable_regex_detection=request.enable_regex_detection,
            enable_complexity_analysis=request.enable_complexity_analysis,
            similarity_threshold=request.similarity_threshold,
            # Issue #12384: tag every stored pattern with the requester's
            # source_id so the read-side endpoints can scope queries to it.
            source_id=request.source_id,
        )
        report = await asyncio.wait_for(
            analyzer.analyze_directory(scan_dir, progress_callback=_on_progress),
            timeout=_ANALYSIS_TIMEOUT,
        )
        _, moved = await _confirmed_dir_or_refusal(request.source_id, scan_dir, expect=scan_dir)
        if moved is not None:
            return moved
        result = report.to_dict()
        await _save_path_checkpoint(scan_dir, result, request.source_id)
        return result

    return _wrap(_run_async(_work()), started)


# ---------------------------------------------------------------------------
# 5. Bug prediction (api/analytics_bug_prediction.py)
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="analytics.run_bug_prediction_analysis")
@_binds_task_id
def run_bug_prediction_analysis(self, path: str, include_pattern: str, limit: int) -> dict:
    """Celery wrapper for bug prediction background analysis (#6505)."""
    started = datetime.now(tz=timezone.utc).isoformat()
    _progress(self, "Gathering file data", 5.0, started)

    async def _work():
        from api.analytics_bug_prediction import _run_bug_analysis

        _progress(self, "Analyzing files", 10.0, started)
        result = await _run_bug_analysis(path, include_pattern, limit)
        _progress(self, "Finalizing results", 95.0, started)
        return result

    return _wrap(_run_async(_work()), started)


# ---------------------------------------------------------------------------
# 6. Security score (api/code_intelligence.py)
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="analytics.run_security_analysis")
@_binds_task_id
def run_security_analysis(self, path: str) -> dict:
    """Celery wrapper for security score background analysis (#6505)."""
    started = datetime.now(tz=timezone.utc).isoformat()
    _progress(self, "Initializing security analyzer", 10.0, started)

    async def _work():
        from api.code_intelligence import _get_security_status_message
        from code_intelligence.security import SecurityAnalyzer
        from code_intelligence.shared.scoring import get_grade_from_score

        analyzer = SecurityAnalyzer(project_root=path)
        _progress(self, "Scanning for vulnerabilities", 30.0, started)
        await asyncio.to_thread(analyzer.analyze_directory)
        _progress(self, "Calculating security score", 80.0, started)
        summary = analyzer.get_summary()
        score = summary["security_score"]
        return {
            "status": "success",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "path": path,
            "security_score": score,
            "grade": get_grade_from_score(score),
            "risk_level": summary["risk_level"],
            "status_message": _get_security_status_message(score),
            "total_findings": summary["total_findings"],
            "critical_issues": summary["critical_issues"],
            "high_issues": summary["high_issues"],
            "files_analyzed": summary["files_analyzed"],
            "severity_breakdown": summary["by_severity"],
            "owasp_breakdown": summary["by_owasp_category"],
        }

    return _wrap(_run_async(_work()), started)


# ---------------------------------------------------------------------------
# 6b. Anti-pattern detection (api/anti_pattern.py) — Issue #12365
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="analytics.run_anti_pattern_analysis")
@_binds_task_id
def run_anti_pattern_analysis(self, root_path: str) -> dict:
    """Celery wrapper for anti-pattern background analysis (#12365).

    Unlike the other analytics tasks above, ``AntiPatternDetector.analyze()``
    writes its own result directly into its Redis cache (keyed
    ``anti_pattern_analysis:latest``) as part of the call -- no separate
    store-write step is needed here, matching what ``POST /api/anti-pattern/
    analyze`` already does synchronously today.
    """
    started = datetime.now(tz=timezone.utc).isoformat()
    _progress(self, "Starting anti-pattern analysis", 10.0, started)

    async def _work():
        from api.anti_pattern import _get_detector

        detector = await _get_detector()
        _progress(self, "Analyzing codebase", 40.0, started)
        report = await detector.analyze(root_path=root_path)
        return report.to_dict()

    return _wrap(_run_async(_work()), started)


# ---------------------------------------------------------------------------
# 7. Dashboard overview (api/analytics.py)
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="analytics.run_dashboard_analysis")
@_binds_task_id
def run_dashboard_analysis(self) -> dict:
    """Celery wrapper for dashboard overview background analysis (#6505)."""
    started = datetime.now(tz=timezone.utc).isoformat()
    _progress(self, "Collecting system health", 10.0, started)

    async def _work():
        from api.analytics import (
            _get_code_analysis_status,
            _get_realtime_metrics,
            _handle_task_exception,
            analytics_controller,
            local_hardware_monitor,
        )

        results = await asyncio.gather(
            local_hardware_monitor.get_system_health(),
            analytics_controller.collect_performance_metrics(),
            analytics_controller.analyze_communication_patterns(),
            analytics_controller.get_usage_statistics(),
            analytics_controller.detect_trends(),
            return_exceptions=True,
        )
        _progress(self, "Processing metrics", 60.0, started)
        system_health = _handle_task_exception(results[0], "system_health")
        performance = _handle_task_exception(results[1], "performance")
        communication = _handle_task_exception(results[2], "communication")
        usage = _handle_task_exception(results[3], "usage")
        trends = _handle_task_exception(results[4], "trends")
        _progress(self, "Building overview", 80.0, started)
        code_status = await _get_code_analysis_status()
        realtime = await _get_realtime_metrics()
        return {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "system_health": system_health,
            "performance_metrics": performance,
            "communication_patterns": communication,
            "code_analysis_status": code_status,
            "usage_statistics": usage,
            "realtime_metrics": realtime,
            "trends": trends,
        }

    result = _run_async(_work())
    return _wrap(result, started)


# ---------------------------------------------------------------------------
# 4b. Pattern summary (api/codebase_analytics/endpoints/pattern_analysis.py)
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="analytics.run_pattern_summary_analysis")
@_binds_task_id
def run_pattern_summary_analysis(self, path: str, source_id: str) -> dict:
    """Celery wrapper for pattern summary background job (#6505).

    ``source_id`` is the source *path* belongs to; the directory is confirmed inside it again
    when the task runs (#20513).
    """
    from api.codebase_analytics.endpoints.pattern_analysis import _ANALYSIS_TIMEOUT

    started = datetime.now(tz=timezone.utc).isoformat()
    _progress(self, "Initializing analyzer", 10.0, started)

    async def _work():
        from code_intelligence.pattern_analysis import CodePatternAnalyzer

        scan_dir, refusal = await _confirmed_dir_or_refusal(source_id, path)
        if refusal is not None:
            return refusal
        analyzer = CodePatternAnalyzer(enable_embedding_storage=False)

        async def _on_progress(step: str, progress: float) -> None:
            scaled = 30.0 + (progress / 100.0) * 50.0
            _progress(self, step, scaled, started)

        report = await asyncio.wait_for(
            analyzer.analyze_directory(scan_dir, progress_callback=_on_progress),
            timeout=_ANALYSIS_TIMEOUT,
        )
        _, moved = await _confirmed_dir_or_refusal(source_id, scan_dir, expect=scan_dir)
        if moved is not None:
            return moved
        _progress(self, "Building summary", 80.0, started)
        return {
            "total_patterns": report.total_patterns,
            "duplicates": len(report.duplicate_patterns),
            "regex_opportunities": len(report.regex_opportunities),
            "complexity_hotspots": len(report.complexity_hotspots),
            "modularization_suggestions": len(report.modularization_suggestions),
            "potential_loc_reduction": report.potential_loc_reduction,
            "complexity_score": report.complexity_score,
        }

    return _wrap(_run_async(_work()), started)
