# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Celery tasks for analytics background work (GH#6505).

Replaces the seven BackgroundTaskManager-based async workers with
canonical Celery tasks.  Each task uses ``bind=True`` so it can call
``self.update_state()`` for granular progress reporting compatible
with the existing ``celery_task_status.celery_result_to_status`` helper.

Async workers are wrapped via ``_run_async`` (new event loop per task).
"""

import asyncio
import hashlib
import json
from datetime import datetime, timezone

from autobot_shared.logging_manager import get_logger
from celery_app import celery_app

logger = get_logger(__name__)

_PATTERN_CHECKPOINT_PREFIX = "pattern_complete_checkpoint:"
_CHECKPOINT_TTL = 3600  # 1 h — recent-enough to resume from


def _path_checkpoint_key(path: str) -> str:
    return f"{_PATTERN_CHECKPOINT_PREFIX}{hashlib.sha256(path.encode()).hexdigest()[:16]}"


async def _load_path_checkpoint(path: str) -> dict | None:
    """Return a previously-saved completed analysis result for *path*, or None (GH#8439)."""
    try:
        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client(database="analytics")
        if not redis:
            return None
        raw = await redis.get(_path_checkpoint_key(path))
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def _save_path_checkpoint(path: str, result: dict) -> None:
    """Persist *result* as the checkpoint for *path* (GH#8439)."""
    try:
        from autobot_shared.redis_client import get_async_redis_client

        redis = await get_async_redis_client(database="analytics")
        if redis:
            await redis.set(_path_checkpoint_key(path), json.dumps(result, default=str), ex=_CHECKPOINT_TTL)
    except Exception:
        pass


def _run_async(coro):
    """Run *coro* in a fresh event loop (Celery workers are sync).

    GH#8434: drain any fire-and-forget tasks (asyncio.create_task) spawned
    inside *coro* before closing the loop so they are not orphaned.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(coro)
        pending = asyncio.all_tasks(loop)
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        return result
    finally:
        loop.close()


def _progress(self, step: str, pct: float, started_at: str | None = None) -> None:
    """Emit a PROGRESS state update on the bound Celery task *self*."""
    meta: dict = {"step": step, "progress": pct}
    if started_at:
        meta["started_at"] = started_at
    self.update_state(state="PROGRESS", meta=meta)


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


@celery_app.task(bind=True, name="analytics.run_import_tree_analysis")
def run_import_tree_analysis(self) -> dict:
    """Celery wrapper for import tree background analysis (#6505)."""
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
        from api.codebase_analytics.endpoints.shared import get_project_root

        project_root = get_project_root()
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
def run_duplicate_analysis(self) -> dict:
    """Celery wrapper for duplicate code background analysis (#6505)."""
    started = datetime.now(tz=timezone.utc).isoformat()
    _progress(self, "Running duplicate analysis", 20.0, started)

    async def _work():
        from api.codebase_analytics.endpoints.duplicates import (
            _build_timeout_response,
            _get_project_root,
            _process_and_cache_analysis,
            _run_duplicate_analysis,
        )

        project_root = _get_project_root()
        analysis = await _run_duplicate_analysis(project_root, 0.5, False)
        if analysis is None:
            return _build_timeout_response()
        _progress(self, "Processing results", 80.0, started)
        return _process_and_cache_analysis(analysis, project_root)

    return _wrap(_run_async(_work()), started)


# ---------------------------------------------------------------------------
# 3. Dependency analysis (api/codebase_analytics/endpoints/dependencies.py)
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="analytics.run_dependency_analysis")
def run_dependency_analysis(self) -> dict:
    """Celery wrapper for dependency background analysis (#6505)."""
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
        from api.codebase_analytics.endpoints.shared import get_project_root
        from api.codebase_analytics.storage import get_code_collection

        code_collection = await asyncio.to_thread(get_code_collection)
        modules: Dict[str, Dict] = {}
        import_relationships: List[Dict] = []
        external_deps: Dict[str, int] = {}
        runtime_rels: List[Dict] = []

        if code_collection:
            await _load_modules_from_chromadb(code_collection, modules)

        _progress(self, "Scanning filesystem imports", 30.0, started)
        project_root = get_project_root()
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
        # Resume from checkpoint if analysis for this path was recently completed.
        saved = await _load_path_checkpoint(request.path)
        if saved:
            logger.info("run_pattern_analysis: resuming from checkpoint for path %s", request.path)
            _progress(self, "Loaded from checkpoint", 100.0, started)
            return saved

        from code_intelligence.pattern_analysis import CodePatternAnalyzer

        async def _on_progress(step: str, progress: float) -> None:
            _progress(self, step, progress, started)

        analyzer = CodePatternAnalyzer(
            enable_clone_detection=request.enable_clone_detection,
            enable_anti_pattern_detection=request.enable_anti_pattern_detection,
            enable_regex_detection=request.enable_regex_detection,
            enable_complexity_analysis=request.enable_complexity_analysis,
            similarity_threshold=request.similarity_threshold,
        )
        report = await asyncio.wait_for(
            analyzer.analyze_directory(request.path, progress_callback=_on_progress),
            timeout=_ANALYSIS_TIMEOUT,
        )
        result = report.to_dict()
        await _save_path_checkpoint(request.path, result)
        return result

    return _wrap(_run_async(_work()), started)


# ---------------------------------------------------------------------------
# 5. Bug prediction (api/analytics_bug_prediction.py)
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="analytics.run_bug_prediction_analysis")
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
def run_security_analysis(self, path: str) -> dict:
    """Celery wrapper for security score background analysis (#6505)."""
    started = datetime.now(tz=timezone.utc).isoformat()
    _progress(self, "Initializing security analyzer", 10.0, started)

    async def _work():
        from api.code_intelligence import _calculate_grade_from_score, _get_security_status_message
        from code_intelligence.security_analyzer import SecurityAnalyzer

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
            "grade": _calculate_grade_from_score(score),
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
# 7. Dashboard overview (api/analytics.py)
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, name="analytics.run_dashboard_analysis")
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
            hardware_monitor,
        )

        results = await asyncio.gather(
            hardware_monitor.get_system_health(),
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
def run_pattern_summary_analysis(self, path: str) -> dict:
    """Celery wrapper for pattern summary background job (#6505)."""
    from api.codebase_analytics.endpoints.pattern_analysis import _ANALYSIS_TIMEOUT

    started = datetime.now(tz=timezone.utc).isoformat()
    _progress(self, "Initializing analyzer", 10.0, started)

    async def _work():
        from code_intelligence.pattern_analysis import CodePatternAnalyzer

        analyzer = CodePatternAnalyzer(enable_embedding_storage=False)

        async def _on_progress(step: str, progress: float) -> None:
            scaled = 30.0 + (progress / 100.0) * 50.0
            _progress(self, step, scaled, started)

        report = await asyncio.wait_for(
            analyzer.analyze_directory(path, progress_callback=_on_progress),
            timeout=_ANALYSIS_TIMEOUT,
        )
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
