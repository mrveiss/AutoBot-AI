# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pattern Analysis API Endpoints

Issue #208: FastAPI endpoints for code pattern detection and optimization.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from constants.path_constants import PATH
from constants.threshold_constants import QueryDefaults
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pattern Analysis"])

# Global state for tracking analysis tasks
_analysis_tasks: Dict[str, Dict[str, Any]] = {}
# Lock for thread-safe access to _analysis_tasks (Issue #1221)
_analysis_tasks_lock = asyncio.Lock()

# Redis-backed task state for multi-worker visibility (#1179 pattern)
_PATTERN_TASK_REDIS_PREFIX = "pattern_task:"
_PATTERN_TASK_REDIS_TTL = 86400  # 24 hours


async def _save_pattern_task_to_redis(task_id: str) -> None:
    """Persist pattern task state to Redis so all workers can read it."""
    try:
        from ..scanner import get_redis_connection_async

        redis = await get_redis_connection_async()
        if redis:
            state = _analysis_tasks.get(task_id)
            if state:
                # Exclude non-serializable fields
                safe_state = {k: v for k, v in state.items() if k != "request"}
                await redis.set(
                    f"{_PATTERN_TASK_REDIS_PREFIX}{task_id}",
                    json.dumps(safe_state, default=str),
                    ex=_PATTERN_TASK_REDIS_TTL,
                )
    except Exception as e:
        logger.debug("Pattern task Redis save failed (non-fatal): %s", e)


async def _load_pattern_task_from_redis(
    task_id: str,
) -> Optional[Dict[str, Any]]:
    """Load pattern task state from Redis (cross-worker visibility).

    If the task is still 'running' in Redis but absent from the in-memory
    dict, it was orphaned by a backend restart — mark it failed (#1234).
    """
    try:
        from ..scanner import get_redis_connection_async

        redis = await get_redis_connection_async()
        if redis:
            data = await redis.get(f"{_PATTERN_TASK_REDIS_PREFIX}{task_id}")
            if data:
                task = json.loads(data)
                if task.get("status") == "running":
                    task["status"] = "failed"
                    task["error"] = "Task orphaned by backend restart"
                    task["reason"] = "orphaned"
                    task["completed_at"] = datetime.now().isoformat()
                    await redis.set(
                        f"{_PATTERN_TASK_REDIS_PREFIX}{task_id}",
                        json.dumps(task, default=str),
                        ex=_PATTERN_TASK_REDIS_TTL,
                    )
                    logger.info("Marked orphaned Redis task %s as failed", task_id)
                return task
    except Exception as e:
        logger.debug("Pattern task Redis load failed (non-fatal): %s", e)
    return None


async def _clear_orphaned_redis_tasks() -> int:
    """Mark any 'running' tasks in Redis as failed (#1234).

    After a backend restart, in-memory _analysis_tasks is empty but Redis
    may still hold tasks with status='running' that will never complete.
    This scans Redis for such orphans and marks them failed so new
    analyses can start without a false 409 conflict.

    Returns:
        Number of orphaned tasks cleared.
    """
    cleared = 0
    try:
        from ..scanner import get_redis_connection_async

        redis = await get_redis_connection_async()
        if not redis:
            return 0

        # Scan for pattern task keys
        cursor = 0
        while True:
            cursor, keys = await redis.scan(
                cursor,
                match=f"{_PATTERN_TASK_REDIS_PREFIX}*",
                count=100,
            )
            for key in keys:
                data = await redis.get(key)
                if not data:
                    continue
                task = json.loads(data)
                task_id = key.decode() if isinstance(key, bytes) else key
                task_id = task_id.removeprefix(_PATTERN_TASK_REDIS_PREFIX)
                if task.get("status") == "running" and task_id not in _analysis_tasks:
                    task["status"] = "failed"
                    task["error"] = "Task orphaned by backend restart"
                    task["reason"] = "orphaned"
                    task["completed_at"] = datetime.now().isoformat()
                    await redis.set(
                        f"{_PATTERN_TASK_REDIS_PREFIX}{task_id}",
                        json.dumps(task, default=str),
                        ex=_PATTERN_TASK_REDIS_TTL,
                    )
                    cleared += 1
                    logger.info("Cleared orphaned Redis pattern task %s", task_id)
            if cursor == 0:
                break
    except Exception as e:
        logger.debug("Orphaned Redis task scan failed (non-fatal): %s", e)
    return cleared


class PatternAnalysisRequest(BaseModel):
    """Request model for pattern analysis."""

    path: str = Field(
        default=str(PATH.PROJECT_ROOT),
        description="Path to analyze (defaults to project root)",
    )
    enable_clone_detection: bool = Field(
        default=True, description="Enable clone/duplicate detection"
    )
    enable_anti_pattern_detection: bool = Field(
        default=True, description="Enable anti-pattern detection"
    )
    enable_regex_detection: bool = Field(
        default=True, description="Enable regex optimization detection"
    )
    enable_complexity_analysis: bool = Field(
        default=True, description="Enable complexity analysis"
    )
    similarity_threshold: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Similarity threshold for clustering"
    )


class PatternAnalysisStatus(BaseModel):
    """Status model for pattern analysis task."""

    task_id: str
    status: str  # pending, running, completed, failed
    progress: float = 0.0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    reason: Optional[str] = None  # orphaned, timeout, manual (#1250)
    result: Optional[Dict[str, Any]] = None


class PatternSummary(BaseModel):
    """Summary of detected patterns."""

    total_patterns: int
    duplicates: int
    regex_opportunities: int
    complexity_hotspots: int
    modularization_suggestions: int
    potential_loc_reduction: int
    complexity_score: str


async def _run_analysis(task_id: str, request: PatternAnalysisRequest) -> None:
    """Run pattern analysis in background.

    Args:
        task_id: Unique task identifier
        request: Analysis request parameters
    """
    try:
        # Import here to avoid circular imports
        from code_intelligence.pattern_analysis import CodePatternAnalyzer

        _analysis_tasks[task_id]["status"] = "running"
        _analysis_tasks[task_id]["started_at"] = datetime.now().isoformat()
        await _save_pattern_task_to_redis(task_id)

        # Create analyzer with request parameters
        analyzer = CodePatternAnalyzer(
            enable_clone_detection=request.enable_clone_detection,
            enable_anti_pattern_detection=request.enable_anti_pattern_detection,
            enable_regex_detection=request.enable_regex_detection,
            enable_complexity_analysis=request.enable_complexity_analysis,
            similarity_threshold=request.similarity_threshold,
        )

        # Run analysis
        report = await analyzer.analyze_directory(request.path)

        # Store result
        _analysis_tasks[task_id]["status"] = "completed"
        _analysis_tasks[task_id]["completed_at"] = datetime.now().isoformat()
        _analysis_tasks[task_id]["result"] = report.to_dict()
        _analysis_tasks[task_id]["progress"] = 100.0
        await _save_pattern_task_to_redis(task_id)

    except Exception as e:
        logger.error("Pattern analysis failed: %s", e)
        _analysis_tasks[task_id]["status"] = "failed"
        _analysis_tasks[task_id]["error"] = str(e)
        _analysis_tasks[task_id]["completed_at"] = datetime.now().isoformat()
        await _save_pattern_task_to_redis(task_id)


def _cleanup_stuck_tasks() -> int:
    """Clean up tasks that have been running too long.

    Returns:
        Number of tasks cleaned up

    Issue #647: Auto-recover from stuck tasks.
    """
    cleaned = 0
    now = datetime.now()

    for task_id, task in list(_analysis_tasks.items()):
        if task.get("status") == "running":
            started_at = task.get("started_at")
            is_stuck = False

            if started_at:
                try:
                    start_time = datetime.fromisoformat(started_at)
                    elapsed = (now - start_time).total_seconds()
                    # Mark as stuck if running longer than timeout
                    is_stuck = elapsed > TASK_TIMEOUT_SECONDS
                except (ValueError, TypeError):
                    is_stuck = True
            else:
                # No start time means task never actually started
                is_stuck = True

            if is_stuck:
                _analysis_tasks[task_id]["status"] = "failed"
                _analysis_tasks[task_id]["error"] = "Task timed out (auto-recovered)"
                _analysis_tasks[task_id]["completed_at"] = now.isoformat()
                cleaned += 1
                logger.warning("Auto-recovered stuck task %s", task_id)

    return cleaned


# Task timeout threshold in seconds (10 minutes)
TASK_TIMEOUT_SECONDS = 600


@router.post("/patterns/analyze", response_model=PatternAnalysisStatus)
async def start_pattern_analysis(
    request: PatternAnalysisRequest,
    background_tasks: BackgroundTasks,
) -> PatternAnalysisStatus:
    """Start code pattern analysis.

    This endpoint initiates a background analysis task and returns
    a task ID that can be used to check status and retrieve results.

    Issue #208: Code Pattern Detection & Optimization System
    Issue #647: Auto-recover from stuck tasks before checking for running tasks.
    """
    import uuid

    # Generate task ID
    task_id = str(uuid.uuid4())[:8]

    # Thread-safe check+insert under lock (Issue #1221)
    async with _analysis_tasks_lock:
        # Auto-cleanup any stuck tasks before checking (Issue #647)
        cleaned = _cleanup_stuck_tasks()
        if cleaned > 0:
            logger.info(
                "Auto-recovered %d stuck task(s) before starting new analysis",
                cleaned,
            )

        # Also clear orphaned Redis tasks that survived a restart (#1234)
        await _clear_orphaned_redis_tasks()

        # Check if another analysis is genuinely running
        running_tasks = [
            t for t in _analysis_tasks.values() if t.get("status") == "running"
        ]
        if running_tasks:
            raise HTTPException(
                status_code=409,
                detail="Another pattern analysis is already running. "
                "Please wait or cancel it.",
            )

        # Initialize task state
        _analysis_tasks[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "progress": 0.0,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "result": None,
            "request": request.model_dump(),
        }

    # Start background task (outside lock — doesn't modify dict)
    background_tasks.add_task(_run_analysis, task_id, request)

    return PatternAnalysisStatus(
        task_id=task_id,
        status="pending",
        progress=0.0,
    )


@router.get("/patterns/status/{task_id}", response_model=PatternAnalysisStatus)
async def get_analysis_status(task_id: str) -> PatternAnalysisStatus:
    """Get status of a pattern analysis task.

    Args:
        task_id: The task ID returned from start_pattern_analysis

    Returns:
        PatternAnalysisStatus with current status and results if complete
    """
    # #1179 pattern: check local memory first, fall back to Redis
    task = _analysis_tasks.get(task_id)
    if task is None:
        task = await _load_pattern_task_from_redis(task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Analysis task {task_id} not found",
        )

    return PatternAnalysisStatus(
        task_id=task_id,
        status=task["status"],
        progress=task.get("progress", 0.0),
        started_at=task.get("started_at"),
        completed_at=task.get("completed_at"),
        error=task.get("error"),
        reason=task.get("reason"),
        result=task.get("result"),
    )


@router.get("/patterns/result/{task_id}")
async def get_analysis_result(task_id: str) -> Dict[str, Any]:
    """Get full results of a completed pattern analysis.

    Args:
        task_id: The task ID returned from start_pattern_analysis

    Returns:
        Full analysis report as dictionary
    """
    task = _analysis_tasks.get(task_id)
    if task is None:
        task = await _load_pattern_task_from_redis(task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Analysis task {task_id} not found",
        )

    if task["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Analysis not complete. Current status: {task['status']}",
        )

    return task.get("result", {})


@router.delete("/patterns/task/{task_id}")
async def cancel_analysis(task_id: str) -> Dict[str, str]:
    """Cancel or delete a pattern analysis task.

    Args:
        task_id: The task ID to cancel/delete

    Returns:
        Confirmation message
    """
    async with _analysis_tasks_lock:
        if task_id not in _analysis_tasks:
            raise HTTPException(
                status_code=404,
                detail=f"Analysis task {task_id} not found",
            )

        # Remove task (note: this doesn't actually stop a running task)
        del _analysis_tasks[task_id]

    return {"message": f"Task {task_id} removed"}


@router.get("/patterns/tasks")
async def list_analysis_tasks() -> Dict[str, Any]:
    """List all pattern analysis tasks.

    Returns:
        Dictionary with all tasks and their status

    Issue #647: Added endpoint to view all tasks for debugging stuck analyses.
    """
    tasks = []
    for task_id, task in _analysis_tasks.items():
        tasks.append(
            {
                "task_id": task_id,
                "status": task.get("status"),
                "progress": task.get("progress", 0.0),
                "started_at": task.get("started_at"),
                "completed_at": task.get("completed_at"),
                "error": task.get("error"),
            }
        )

    return {
        "total": len(tasks),
        "running": len([t for t in tasks if t["status"] == "running"]),
        "tasks": tasks,
    }


@router.post("/patterns/tasks/clear-stuck")
async def clear_stuck_tasks(
    force: bool = Query(
        default=False,
        description="Force clear ALL running tasks, not just timed-out ones",
    )
) -> Dict[str, Any]:
    """Clear tasks that are stuck in 'running' status.

    This marks long-running tasks as failed and allows new analyses to start.
    Tasks running longer than TASK_TIMEOUT_SECONDS are considered stuck.

    Args:
        force: If True, clears ALL running tasks regardless of how long they've been running

    Returns:
        Summary of cleared tasks

    Issue #647: Added endpoint to clear stuck analysis tasks.
    """
    cleared = []
    now = datetime.now()

    async with _analysis_tasks_lock:
        for task_id, task in list(_analysis_tasks.items()):
            if task.get("status") == "running":
                should_clear = force  # Force mode clears all

                if not force:
                    # Normal mode: only clear timed-out tasks
                    started_at = task.get("started_at")
                    if started_at:
                        try:
                            start_time = datetime.fromisoformat(started_at)
                            elapsed = (now - start_time).total_seconds()
                            should_clear = elapsed > TASK_TIMEOUT_SECONDS
                        except (ValueError, TypeError):
                            should_clear = True
                    else:
                        should_clear = True

                if should_clear:
                    _analysis_tasks[task_id]["status"] = "failed"
                    _analysis_tasks[task_id]["error"] = (
                        "Task cleared manually"
                        if force
                        else "Task timed out or was stuck"
                    )
                    _analysis_tasks[task_id]["completed_at"] = now.isoformat()
                    cleared.append(task_id)
                    await _save_pattern_task_to_redis(task_id)
                    logger.info(
                        "Cleared %s task %s",
                        "forced" if force else "stuck",
                        task_id,
                    )

    return {
        "cleared_count": len(cleared),
        "cleared_task_ids": cleared,
        "message": f"Cleared {len(cleared)} task(s)" + (" (forced)" if force else ""),
    }


@router.post("/patterns/tasks/clear-all")
async def clear_all_tasks() -> Dict[str, str]:
    """Clear all pattern analysis tasks from memory and Redis.

    Returns:
        Confirmation message

    Issue #647: Added endpoint to clear all tasks.
    Issue #1234: Also clear Redis-persisted task state.
    """
    async with _analysis_tasks_lock:
        task_ids = list(_analysis_tasks.keys())
        count = len(task_ids)
        _analysis_tasks.clear()

    # Clear from Redis — scan for ALL pattern task keys (#1250)
    # After restart, in-memory dict is empty so task_ids would be empty.
    # Must scan Redis directly to find orphaned keys.
    try:
        from ..scanner import get_redis_connection_async

        redis = await get_redis_connection_async()
        if redis:
            cursor = 0
            while True:
                cursor, keys = await redis.scan(
                    cursor,
                    match=f"{_PATTERN_TASK_REDIS_PREFIX}*",
                    count=100,
                )
                for key in keys:
                    await redis.delete(key)
                    count += 1
                if cursor == 0:
                    break
    except Exception as e:
        logger.debug("Redis task cleanup failed (non-fatal): %s", e)

    return {"message": f"Cleared {count} task(s)"}


@router.get("/patterns/summary", response_model=PatternSummary)
async def get_pattern_summary(
    path: str = Query(default=str(PATH.PROJECT_ROOT), description="Path to analyze"),
) -> PatternSummary:
    """Get a quick summary of patterns in the codebase.

    This is a lighter-weight analysis that returns just the counts
    without full pattern details.
    """
    try:
        from code_intelligence.pattern_analysis import CodePatternAnalyzer

        analyzer = CodePatternAnalyzer(
            enable_embedding_storage=False,  # Skip storage for quick summary
        )

        report = await analyzer.analyze_directory(path)

        return PatternSummary(
            total_patterns=report.total_patterns,
            duplicates=len(report.duplicate_patterns),
            regex_opportunities=len(report.regex_opportunities),
            complexity_hotspots=len(report.complexity_hotspots),
            modularization_suggestions=len(report.modularization_suggestions),
            potential_loc_reduction=report.potential_loc_reduction,
            complexity_score=report.complexity_score,
        )

    except Exception as e:
        logger.error("Pattern summary failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/duplicates")
async def get_duplicate_patterns(
    path: str = Query(default=str(PATH.PROJECT_ROOT), description="Path to analyze"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
) -> List[Dict[str, Any]]:
    """Get duplicate code patterns in the codebase.

    This endpoint specifically analyzes for code duplication.
    """
    try:
        from code_intelligence.pattern_analysis import CodePatternAnalyzer

        analyzer = CodePatternAnalyzer(
            enable_clone_detection=True,
            enable_anti_pattern_detection=False,
            enable_regex_detection=False,
            enable_complexity_analysis=False,
            enable_embedding_storage=False,
        )

        report = await analyzer.analyze_directory(path)

        return [dp.to_dict() for dp in report.duplicate_patterns[:limit]]

    except Exception as e:
        logger.error("Duplicate detection failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/regex-opportunities")
async def get_regex_opportunities(
    path: str = Query(default=str(PATH.PROJECT_ROOT), description="Path to analyze"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
) -> List[Dict[str, Any]]:
    """Get regex optimization opportunities.

    Identifies string operations that could be replaced with regex.
    """
    try:
        from code_intelligence.pattern_analysis import CodePatternAnalyzer

        analyzer = CodePatternAnalyzer(
            enable_clone_detection=False,
            enable_anti_pattern_detection=False,
            enable_regex_detection=True,
            enable_complexity_analysis=False,
            enable_embedding_storage=False,
        )

        report = await analyzer.analyze_directory(path)

        return [ro.to_dict() for ro in report.regex_opportunities[:limit]]

    except Exception as e:
        logger.error("Regex detection failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/complexity-hotspots")
async def get_complexity_hotspots(
    path: str = Query(default=str(PATH.PROJECT_ROOT), description="Path to analyze"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
    min_complexity: int = Query(
        default=QueryDefaults.DEFAULT_SEARCH_LIMIT,
        ge=1,
        description="Minimum cyclomatic complexity",
    ),
) -> List[Dict[str, Any]]:
    """Get complexity hotspots in the codebase.

    Identifies functions with high cyclomatic or cognitive complexity.
    """
    try:
        from code_intelligence.pattern_analysis import CodePatternAnalyzer

        analyzer = CodePatternAnalyzer(
            enable_clone_detection=False,
            enable_anti_pattern_detection=False,
            enable_regex_detection=False,
            enable_complexity_analysis=True,
            enable_embedding_storage=False,
            cc_threshold=min_complexity,
        )

        report = await analyzer.analyze_directory(path)

        # Filter by minimum complexity
        filtered = [
            h
            for h in report.complexity_hotspots
            if h.cyclomatic_complexity >= min_complexity
        ]

        return [ch.to_dict() for ch in filtered[:limit]]

    except Exception as e:
        logger.error("Complexity analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/refactoring-suggestions")
async def get_refactoring_suggestions(
    path: str = Query(default=str(PATH.PROJECT_ROOT), description="Path to analyze"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
) -> List[Dict[str, Any]]:
    """Get prioritized refactoring suggestions.

    Analyzes the codebase and generates actionable refactoring proposals.
    """
    try:
        from code_intelligence.pattern_analysis import (
            CodePatternAnalyzer,
            RefactoringSuggestionGenerator,
        )

        analyzer = CodePatternAnalyzer(enable_embedding_storage=False)
        report = await analyzer.analyze_directory(path)

        # Generate refactoring suggestions
        generator = RefactoringSuggestionGenerator()
        all_patterns = (
            report.duplicate_patterns
            + report.regex_opportunities
            + report.complexity_hotspots
        )
        suggestions = generator.generate_suggestions(all_patterns)

        return [s.to_dict() for s in suggestions[:limit]]

    except Exception as e:
        logger.error("Refactoring suggestions failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/report")
async def get_pattern_report(
    path: str = Query(default=str(PATH.PROJECT_ROOT), description="Path to analyze"),
    format: str = Query(default="json", description="Output format: json or markdown"),
) -> Any:
    """Generate a comprehensive pattern analysis report.

    Returns either JSON or Markdown format based on the format parameter.
    """
    try:
        from code_intelligence.pattern_analysis import CodePatternAnalyzer

        analyzer = CodePatternAnalyzer(enable_embedding_storage=False)
        report = await analyzer.analyze_directory(path)

        if format.lower() == "markdown":
            from fastapi.responses import PlainTextResponse

            return PlainTextResponse(
                content=report.to_markdown(),
                media_type="text/markdown",
            )

        return report.to_dict()

    except Exception as e:
        logger.error("Report generation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/storage/stats")
async def get_pattern_storage_stats() -> Dict[str, Any]:
    """Get statistics about stored patterns in ChromaDB.

    Returns information about the code_patterns collection.
    """
    try:
        from code_intelligence.pattern_analysis.storage import get_pattern_stats

        return await get_pattern_stats()

    except Exception as e:
        logger.error("Storage stats failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _build_empty_pattern_summary() -> Dict[str, Any]:
    """
    Build empty pattern summary response.

    Issue #665: Extracted from get_cached_pattern_summary to reduce duplication.
    """
    return {
        "status": "empty",
        "total_patterns": 0,
        "severity_distribution": {},
        "pattern_type_distribution": {},
        "has_cached_data": False,
    }


def _aggregate_pattern_metadata(metadatas: List[Dict]) -> Dict[str, Any]:
    """
    Aggregate statistics from pattern metadata.

    Issue #665: Extracted from get_cached_pattern_summary for maintainability.

    Args:
        metadatas: List of metadata dictionaries from ChromaDB

    Returns:
        Aggregated statistics dict with type counts, severity counts,
        LOC reduction, and file count.
    """
    type_counts: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {}
    total_loc_reduction = 0
    files_seen: set = set()

    for meta in metadatas:
        # Count pattern types
        ptype = meta.get("pattern_type", "unknown")
        type_counts[ptype] = type_counts.get(ptype, 0) + 1

        # Count severities
        severity = meta.get("severity", "info")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

        # Track LOC reduction potential
        if "code_reduction_potential" in meta:
            try:
                total_loc_reduction += int(meta["code_reduction_potential"])
            except (ValueError, TypeError):
                pass

        # Track unique files
        if "file_path" in meta:
            files_seen.add(meta["file_path"])

    return {
        "type_counts": type_counts,
        "severity_counts": severity_counts,
        "total_loc_reduction": total_loc_reduction,
        "files_count": len(files_seen),
    }


@router.get("/patterns/cached-summary")
async def get_cached_pattern_summary() -> Dict[str, Any]:
    """Get cached pattern summary from ChromaDB without re-analyzing.

    Issue #208: Fast loading endpoint for already indexed patterns.
    Issue #665: Refactored to use extracted helpers.
    Returns summary data from stored patterns, not requiring full analysis.
    """
    try:
        from code_intelligence.pattern_analysis.storage import (
            get_pattern_collection_async,
        )

        collection = await get_pattern_collection_async()
        if collection is None:
            return _build_empty_pattern_summary()

        count = await collection.count()
        if count == 0:
            return _build_empty_pattern_summary()

        # Get all metadata for aggregation (limit to 2000 for performance)
        sample_size = min(count, 2000)
        sample = await collection.get(
            limit=sample_size,
            include=["metadatas"],
        )

        # Aggregate statistics (Issue #665: use helper)
        if not sample.get("metadatas"):
            return _build_empty_pattern_summary()

        stats = _aggregate_pattern_metadata(sample["metadatas"])

        return {
            "status": "success",
            "total_patterns": count,
            "sampled_patterns": sample_size,
            "severity_distribution": stats["severity_counts"],
            "pattern_type_distribution": stats["type_counts"],
            "potential_loc_reduction": stats["total_loc_reduction"],
            "files_analyzed": stats["files_count"],
            "has_cached_data": True,
        }

    except Exception as e:
        logger.error("Cached summary failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _build_empty_patterns_response() -> Dict[str, Any]:
    """
    Build empty patterns response for when no data exists.

    Issue #665: Extracted from get_cached_patterns to reduce duplication.

    Returns:
        Empty patterns response dictionary.
    """
    return {
        "status": "empty",
        "patterns": [],
        "total": 0,
    }


def _build_chromadb_where_filter(
    pattern_type: Optional[str],
    severity: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Build ChromaDB where filter from optional parameters.

    Issue #665: Extracted from get_cached_patterns to improve maintainability.

    Args:
        pattern_type: Optional pattern type filter.
        severity: Optional severity filter.

    Returns:
        ChromaDB-compatible where filter dict, or None if no filters.
    """
    if not pattern_type and not severity:
        return None

    conditions = []
    if pattern_type:
        conditions.append({"pattern_type": pattern_type})
    if severity:
        conditions.append({"severity": severity})

    if len(conditions) == 1:
        return conditions[0]

    return {"$and": conditions}


def _format_pattern_results(
    results: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Format ChromaDB results into pattern response list.

    Issue #665: Extracted from get_cached_patterns to improve maintainability.

    Args:
        results: Raw ChromaDB query results with ids, metadatas, documents.

    Returns:
        List of formatted pattern dictionaries.
    """
    patterns = []
    if not results.get("ids"):
        return patterns

    for i, pattern_id in enumerate(results["ids"]):
        pattern = {
            "id": pattern_id,
            "metadata": results["metadatas"][i] if results.get("metadatas") else {},
            "code_snippet": (
                results["documents"][i][:500] if results.get("documents") else ""
            ),
        }
        patterns.append(pattern)

    return patterns


@router.get("/patterns/cached-patterns")
async def get_cached_patterns(
    pattern_type: Optional[str] = Query(None, description="Filter by pattern type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    limit: int = Query(
        default=QueryDefaults.DEFAULT_PAGE_SIZE,
        ge=1,
        le=200,
        description="Maximum results",
    ),
    offset: int = Query(
        default=QueryDefaults.DEFAULT_OFFSET, ge=0, description="Offset for pagination"
    ),
) -> Dict[str, Any]:
    """Get cached patterns from ChromaDB with filtering and pagination.

    Issue #208: Fast loading of already indexed patterns without re-analysis.
    Issue #665: Refactored to use extracted helpers.
    Supports filtering by pattern_type and severity, with pagination.
    """
    try:
        from code_intelligence.pattern_analysis.storage import (
            get_pattern_collection_async,
        )

        collection = await get_pattern_collection_async()
        if collection is None:
            return _build_empty_patterns_response()

        count = await collection.count()
        if count == 0:
            return _build_empty_patterns_response()

        # Build where filter (Issue #665: use extracted helper)
        where_filter = _build_chromadb_where_filter(pattern_type, severity)

        # Query with filters
        results = await collection.get(
            limit=limit,
            offset=offset,
            where=where_filter,
            include=["metadatas", "documents"],
        )

        # Format results (Issue #665: use extracted helper)
        patterns = _format_pattern_results(results)

        return {
            "status": "success",
            "patterns": patterns,
            "total": count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(patterns) < count,
        }

    except Exception as e:
        logger.error("Cached patterns fetch failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/patterns/storage/clear")
async def clear_pattern_storage() -> Dict[str, str]:
    """Clear all stored patterns from ChromaDB.

    WARNING: This is destructive and cannot be undone.
    """
    try:
        from code_intelligence.pattern_analysis.storage import clear_patterns

        success = await clear_patterns()

        if success:
            return {"message": "Pattern storage cleared successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear storage")

    except Exception as e:
        logger.error("Storage clear failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/patterns/similar")
async def search_similar_patterns_endpoint(
    code: str = Query(..., description="Code snippet to find similar patterns for"),
    pattern_type: Optional[str] = Query(None, description="Filter by pattern type"),
    limit: int = Query(
        default=QueryDefaults.DEFAULT_SEARCH_LIMIT,
        ge=1,
        le=50,
        description="Maximum results",
    ),
) -> List[Dict[str, Any]]:
    """Search for similar patterns using vector similarity.

    This endpoint uses ChromaDB to find patterns similar to the provided code.
    """
    try:
        # Generate embedding for query code
        # (Using the analyzer's embedding method)
        from code_intelligence.pattern_analysis import CodePatternAnalyzer
        from code_intelligence.pattern_analysis.storage import search_similar_patterns

        analyzer = CodePatternAnalyzer()
        query_embedding = await analyzer._generate_embedding(code)

        # Search for similar patterns
        results = await search_similar_patterns(
            query_embedding=query_embedding,
            pattern_type=pattern_type,
            n_results=limit,
        )

        return results

    except Exception as e:
        logger.error("Similar pattern search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
