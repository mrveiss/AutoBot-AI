# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pattern Analysis API Endpoints

Issue #208: FastAPI endpoints for code pattern detection and optimization.
Issue #1304: Migrated to shared BackgroundTaskManager.
"""

import logging
from typing import Any, Dict, List, Optional

from constants.path_constants import PATH
from constants.threshold_constants import QueryDefaults
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field
from utils.background_task_manager import BackgroundTaskManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Pattern Analysis"])

# Shared background task manager (#1304)
_manager = BackgroundTaskManager(redis_prefix="pattern_task:")


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
    current_step: Optional[str] = None
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
    """Run pattern analysis in background (#1304)."""
    try:
        from code_intelligence.pattern_analysis import CodePatternAnalyzer

        await _manager.update_progress(task_id, "Initializing", 0.0)

        async def _on_progress(step: str, progress: float) -> None:
            await _manager.update_progress(task_id, step, progress)

        analyzer = CodePatternAnalyzer(
            enable_clone_detection=request.enable_clone_detection,
            enable_anti_pattern_detection=request.enable_anti_pattern_detection,
            enable_regex_detection=request.enable_regex_detection,
            enable_complexity_analysis=request.enable_complexity_analysis,
            similarity_threshold=request.similarity_threshold,
        )

        report = await analyzer.analyze_directory(
            request.path, progress_callback=_on_progress
        )

        await _manager.complete_task(task_id, report.to_dict())

    except Exception as e:
        logger.error("Pattern analysis failed: %s", e)
        await _manager.fail_task(task_id, str(e))


@router.post("/patterns/analyze", response_model=PatternAnalysisStatus)
async def start_pattern_analysis(
    request: PatternAnalysisRequest,
    background_tasks: BackgroundTasks,
) -> PatternAnalysisStatus:
    """Start code pattern analysis (#208, #647, #1304)."""
    task_id = await _manager.create_task(params=request.model_dump())
    background_tasks.add_task(_run_analysis, task_id, request)
    return PatternAnalysisStatus(task_id=task_id, status="pending", progress=0.0)


@router.get(
    "/patterns/status/{task_id}",
    response_model=PatternAnalysisStatus,
)
async def get_analysis_status(task_id: str) -> PatternAnalysisStatus:
    """Get status of a pattern analysis task."""
    task = await _manager.get_status(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Analysis task {task_id} not found",
        )
    return PatternAnalysisStatus(
        task_id=task_id,
        status=task["status"],
        progress=task.get("progress", 0.0),
        current_step=task.get("current_step"),
        started_at=task.get("started_at"),
        completed_at=task.get("completed_at"),
        error=task.get("error"),
        reason=task.get("reason"),
        result=task.get("result"),
    )


@router.get("/patterns/result/{task_id}")
async def get_analysis_result(task_id: str) -> Dict[str, Any]:
    """Get full results of a completed pattern analysis."""
    task = await _manager.get_status(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Analysis task {task_id} not found",
        )
    if task["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Analysis not complete. Status: {task['status']}",
        )
    return task.get("result", {})


@router.delete("/patterns/task/{task_id}")
async def cancel_analysis(task_id: str) -> Dict[str, str]:
    """Cancel or delete a pattern analysis task."""
    deleted = await _manager.delete_task(task_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Analysis task {task_id} not found",
        )
    return {"message": f"Task {task_id} removed"}


@router.get("/patterns/tasks")
async def list_analysis_tasks() -> Dict[str, Any]:
    """List all pattern analysis tasks (#647)."""
    return await _manager.list_tasks()


@router.post("/patterns/tasks/clear-stuck")
async def clear_stuck_tasks(
    force: bool = Query(
        default=False,
        description="Force clear ALL running tasks",
    ),
) -> Dict[str, Any]:
    """Clear stuck tasks (#647)."""
    cleaned = await _manager.clear_stuck(force=force)
    return {
        "cleared_count": cleaned,
        "message": f"Cleared {cleaned} task(s)" + (" (forced)" if force else ""),
    }


@router.post("/patterns/tasks/clear-all")
async def clear_all_tasks() -> Dict[str, str]:
    """Clear all tasks (#647, #1234)."""
    count = await _manager.clear_all()
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


# Background task manager for pattern summary (#1304)
_summary_manager = BackgroundTaskManager(redis_prefix="patsummary_task:")


async def _run_summary_analysis(task_id: str, path: str) -> None:
    """Background worker for pattern summary (#1304)."""
    try:
        from code_intelligence.pattern_analysis import CodePatternAnalyzer

        await _summary_manager.update_progress(task_id, "Initializing analyzer", 10.0)
        analyzer = CodePatternAnalyzer(
            enable_embedding_storage=False,
        )

        await _summary_manager.update_progress(task_id, "Analyzing patterns", 30.0)
        report = await analyzer.analyze_directory(path)

        await _summary_manager.update_progress(task_id, "Building summary", 80.0)
        result = {
            "total_patterns": report.total_patterns,
            "duplicates": len(report.duplicate_patterns),
            "regex_opportunities": len(report.regex_opportunities),
            "complexity_hotspots": len(report.complexity_hotspots),
            "modularization_suggestions": len(report.modularization_suggestions),
            "potential_loc_reduction": (report.potential_loc_reduction),
            "complexity_score": report.complexity_score,
        }
        await _summary_manager.complete_task(task_id, result)
    except Exception as e:
        logger.error("Pattern summary analysis failed: %s", e)
        await _summary_manager.fail_task(task_id, str(e))


@router.post("/patterns/summary/analyze")
async def start_pattern_summary_analysis(
    background_tasks: BackgroundTasks,
    path: str = Query(
        default=str(PATH.PROJECT_ROOT),
        description="Path to analyze",
    ),
):
    """Start background pattern summary analysis (#1304)."""
    task_id = await _summary_manager.create_task(params={"path": path})
    background_tasks.add_task(_run_summary_analysis, task_id, path)
    return {"task_id": task_id, "status": "pending"}


@router.get("/patterns/summary/status/{task_id}")
async def get_pattern_summary_status(task_id: str):
    """Get pattern summary task status (#1304)."""
    task = await _summary_manager.get_status(task_id)
    if task is None:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )
    return task


@router.post("/patterns/summary/tasks/clear-stuck")
async def clear_stuck_summary_tasks(
    force: bool = Query(
        default=False,
        description="Force clear ALL running tasks",
    ),
):
    """Clear stuck pattern summary tasks (#1304)."""
    cleaned = await _summary_manager.clear_stuck(force=force)
    return {
        "cleared_count": cleaned,
        "message": f"Cleared {cleaned} task(s)" + (" (forced)" if force else ""),
    }


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
