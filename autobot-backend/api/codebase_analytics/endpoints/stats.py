# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Codebase statistics endpoints
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

from ..scanner import _tasks_sync_lock, indexing_tasks
from ..storage import get_code_collection, get_redis_connection
from .shared import _in_memory_storage

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_stats_metadata(stats_metadata: dict) -> dict:
    """Parse stats from ChromaDB metadata. (Issue #315 - extracted)"""
    stats = {}
    numeric_fields = [
        "total_files",
        "python_files",
        "javascript_files",
        "typescript_files",
        "vue_files",
        "css_files",
        "html_files",
        "config_files",
        "doc_files",
        "other_code_files",
        "other_files",
        "total_lines",
        "total_functions",
        "total_classes",
        "code_lines",
        "comment_lines",
        "docstring_lines",
        "documentation_lines",
        "blank_lines",
    ]
    for field in numeric_fields:
        if field in stats_metadata:
            stats[field] = int(stats_metadata[field])

    if "average_file_size" in stats_metadata:
        stats["average_file_size"] = float(stats_metadata["average_file_size"])

    # Parse category-specific stats (stored as JSON strings in ChromaDB)
    for category_field in ["lines_by_category", "files_by_category"]:
        if category_field in stats_metadata:
            try:
                value = stats_metadata[category_field]
                if isinstance(value, str):
                    stats[category_field] = json.loads(value)
                elif isinstance(value, dict):
                    stats[category_field] = value
            except (json.JSONDecodeError, TypeError):
                pass

    # Parse ratio strings
    for ratio_field in ["comment_ratio", "docstring_ratio", "documentation_ratio"]:
        if ratio_field in stats_metadata:
            stats[ratio_field] = stats_metadata[ratio_field]

    return stats


def _no_data_response(message: str = "No codebase data found. Run indexing first."):
    """Return standardized no-data response. (Issue #315 - extracted)"""
    return JSONResponse({"status": "no_data", "message": message, "stats": None})


# Issue #540: Maximum time (seconds) before a task is considered stale
_STALE_TASK_TIMEOUT_SECONDS = 3600  # 1 hour


def _is_task_stale(task_info: dict) -> bool:
    """
    Check if an indexing task is stale (stuck in running state too long).

    Issue #540: Prevents perpetual "indexing" status from crashed tasks.

    Args:
        task_info: Task dictionary with started_at timestamp.

    Returns:
        True if task has been running longer than _STALE_TASK_TIMEOUT_SECONDS.
    """
    started_at = task_info.get("started_at")
    if not started_at:
        return False

    try:
        from datetime import datetime

        start_time = datetime.fromisoformat(started_at)
        elapsed = (datetime.now() - start_time).total_seconds()
        return elapsed > _STALE_TASK_TIMEOUT_SECONDS
    except (ValueError, TypeError):
        return False


def _get_active_indexing_task() -> Optional[dict]:
    """
    Check if there's an active indexing task and return its info.

    Issue #540: Used to show indexing status in stats endpoint.
    Uses _tasks_sync_lock for thread safety when accessing indexing_tasks.
    Ignores stale tasks that have been running for more than 1 hour.

    Returns:
        Task info dict if indexing is in progress, None otherwise.
    """
    with _tasks_sync_lock:
        for task_id, task_info in indexing_tasks.items():
            if task_info.get("status") == "running":
                # Issue #540: Skip stale tasks (stuck for >1 hour)
                if _is_task_stale(task_info):
                    logger.warning(
                        "Ignoring stale indexing task %s (started: %s)",
                        task_id,
                        task_info.get("started_at"),
                    )
                    continue

                return {
                    "task_id": task_id,
                    "progress": task_info.get("progress", {}),
                    "phases": task_info.get("phases", {}),
                    "stats": task_info.get("stats", {}),
                    "started_at": task_info.get("started_at"),
                }
    return None


def _build_indexing_response(
    message: str,
    active_task: dict,
    stats: Optional[dict] = None,
) -> JSONResponse:
    """
    Build standardized indexing-in-progress response.

    Issue #665: Extracted from get_codebase_stats to reduce code duplication.
    The function previously had 3 similar blocks building indexing responses.

    Args:
        message: Status message to display
        active_task: Active indexing task info
        stats: Optional existing stats to include

    Returns:
        JSONResponse with indexing status
    """
    return JSONResponse(
        {
            "status": "indexing",
            "message": message,
            "indexing": active_task,
            "stats": stats,
        }
    )


@router.get("/stats")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_codebase_stats",
    error_code_prefix="CODEBASE",
)
async def get_codebase_stats():
    """
    Get real codebase statistics from storage.

    Issue #540: Returns indexing status when indexing is in progress,
    along with any available stats from the previous indexing run.
    Issue #665: Refactored to use _build_indexing_response helper.
    """
    # Issue #540: Check if indexing is in progress
    active_task = _get_active_indexing_task()

    code_collection = await asyncio.to_thread(get_code_collection)

    if not code_collection:
        # Issue #540, #665: Even if ChromaDB fails, show indexing status if available
        if active_task:
            return _build_indexing_response(
                "Indexing in progress. ChromaDB connection pending.",
                active_task,
            )
        return _no_data_response("ChromaDB connection failed.")

    try:
        results = code_collection.get(ids=["codebase_stats"], include=["metadatas"])
    except Exception as chroma_error:
        logger.warning("ChromaDB stats query failed: %s", chroma_error)
        # Issue #540, #665: Show indexing status even on query failure
        if active_task:
            return _build_indexing_response("Indexing in progress.", active_task)
        return _no_data_response()

    # Check if we have data
    if not results.get("metadatas") or len(results["metadatas"]) == 0:
        # Issue #540, #665: Show indexing status when no stats yet
        if active_task:
            return _build_indexing_response(
                "Indexing in progress. Stats will be available when complete.",
                active_task,
            )
        return _no_data_response()

    # Parse and return stats (Issue #315 - use extracted helper)
    stats_metadata = results["metadatas"][0]
    stats = _parse_stats_metadata(stats_metadata)

    # Issue #540: Include indexing info if indexing is in progress
    # This shows both the previous stats AND current indexing progress
    response = {
        "status": "indexing" if active_task else "success",
        "stats": stats,
        "last_indexed": stats_metadata.get("last_indexed", "Never"),
        "storage_type": "chromadb",
    }

    if active_task:
        response["message"] = "Showing previous stats. New indexing in progress."
        response["indexing"] = active_task

    return JSONResponse(response)


def _fetch_hardcodes_from_redis(redis_client, hardcode_type: Optional[str]) -> list:
    """
    Fetch hardcoded values from Redis with pipeline batching.

    Issue #620: Extracted from get_hardcoded_values.
    Issue #561: Uses pipeline batching to fix N+1 query pattern.

    Args:
        redis_client: Redis client
        hardcode_type: Optional type filter

    Returns:
        List of hardcoded values
    """
    results = []
    if hardcode_type:
        hardcodes_data = redis_client.get(f"codebase:hardcodes:{hardcode_type}")
        if hardcodes_data:
            results = json.loads(hardcodes_data)
    else:
        keys = list(redis_client.scan_iter(match="codebase:hardcodes:*"))
        if keys:
            pipe = redis_client.pipeline()
            for key in keys:
                pipe.get(key)
            pipe_results = pipe.execute()
            for hardcodes_data in pipe_results:
                if hardcodes_data:
                    results.extend(json.loads(hardcodes_data))
    return results


def _fetch_hardcodes_from_memory(storage, hardcode_type: Optional[str]) -> list:
    """
    Fetch hardcoded values from in-memory storage.

    Issue #620: Extracted from get_hardcoded_values.

    Args:
        storage: In-memory storage dict
        hardcode_type: Optional type filter

    Returns:
        List of hardcoded values
    """
    results = []
    if hardcode_type:
        hardcodes_data = storage.get(f"codebase:hardcodes:{hardcode_type}")
        if hardcodes_data:
            results = json.loads(hardcodes_data)
    else:
        for key in storage.scan_iter("codebase:hardcodes:*"):
            hardcodes_data = storage.get(key)
            if hardcodes_data:
                results.extend(json.loads(hardcodes_data))
    return results


@router.get("/hardcodes")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_hardcoded_values",
    error_code_prefix="CODEBASE",
)
async def get_hardcoded_values(hardcode_type: Optional[str] = None):
    """
    Get real hardcoded values found in the codebase.

    Issue #620: Refactored to use helper functions.
    """
    redis_client = await get_redis_connection()

    if redis_client:
        # Issue #620: Use helper for Redis fetch
        all_hardcodes = await asyncio.to_thread(
            _fetch_hardcodes_from_redis, redis_client, hardcode_type
        )
        storage_type = "redis"
    elif _in_memory_storage:
        # Issue #620: Use helper for memory fetch
        all_hardcodes = _fetch_hardcodes_from_memory(_in_memory_storage, hardcode_type)
        storage_type = "memory"
    else:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "No codebase data found. Run indexing first.",
                "hardcodes": [],
            }
        )

    # Sort by file and line number
    all_hardcodes.sort(key=lambda x: (x.get("file_path", ""), x.get("line", 0)))

    return JSONResponse(
        {
            "status": "success",
            "hardcodes": all_hardcodes,
            "total_count": len(all_hardcodes),
            "hardcode_types": list(
                set(h.get("type", "unknown") for h in all_hardcodes)
            ),
            "storage_type": storage_type,
        }
    )


def _parse_problem_metadata(metadata: dict) -> dict:
    """Parse problem from metadata. (Issue #315 - extracted)"""
    line_num = metadata.get("line_number")
    return {
        "type": metadata.get("problem_type", ""),
        "severity": metadata.get("severity", ""),
        "file_path": metadata.get("file_path", ""),
        "file_category": metadata.get("file_category", "code"),
        "line_number": int(line_num) if line_num else None,
        "description": metadata.get("description", ""),
        "suggestion": metadata.get("suggestion", ""),
    }


def _fetch_problems_from_chromadb(code_collection, problem_type: Optional[str]) -> list:
    """Fetch problems from ChromaDB. (Issue #315 - extracted)"""
    where_filter = {"type": "problem"}
    if problem_type:
        where_filter["problem_type"] = problem_type

    results = code_collection.get(where=where_filter, include=["metadatas"])
    return [_parse_problem_metadata(m) for m in results.get("metadatas", [])]


async def _fetch_problems_from_redis(problem_type: Optional[str]) -> tuple:
    """Fetch problems from Redis. Returns (problems, success).

    Issue #315: Extracted helper.
    Issue #361: Avoid blocking with asyncio.to_thread.
    Issue #561: Fixed N+1 query pattern with pipeline batching.
    """
    redis_client = await get_redis_connection()
    if not redis_client:
        return [], False

    # Issue #361 - avoid blocking - wrap Redis ops in thread pool
    # Issue #561 - fix N+1 query pattern with pipeline batching
    def _fetch_problems():
        results = []
        if problem_type:
            problems_data = redis_client.get(f"codebase:problems:{problem_type}")
            if problems_data:
                results = json.loads(problems_data)
        else:
            # Issue #561: Collect keys first, then batch fetch with pipeline
            keys = list(redis_client.scan_iter(match="codebase:problems:*"))
            if keys:
                pipe = redis_client.pipeline()
                for key in keys:
                    pipe.get(key)
                pipe_results = pipe.execute()
                for problems_data in pipe_results:
                    if problems_data:
                        results.extend(json.loads(problems_data))
        return results

    problems = await asyncio.to_thread(_fetch_problems)
    return problems, True


@router.get("/embedding-stats")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_embedding_stats",
    error_code_prefix="CODEBASE",
)
async def get_embedding_stats() -> JSONResponse:
    """
    Get NPU embedding generation statistics.

    Issue #681: Provides visibility into NPU vs fallback embedding usage
    for codebase indexing. Shows throughput, timing, and error metrics.

    Returns:
        JSONResponse with embedding statistics including:
        - total_embeddings: Total embeddings generated
        - npu_embeddings: Count generated via NPU worker
        - fallback_embeddings: Count generated via local model
        - npu_percentage: Percentage using NPU acceleration
        - timing metrics (total, npu, fallback)
        - error count
    """
    try:
        from ..npu_embeddings import get_embedding_stats as get_npu_stats

        stats = get_npu_stats()
        total = stats.get("total_embeddings", 0)
        npu_count = stats.get("npu_embeddings", 0)

        # Determine NPU availability based on actual usage:
        # - None if no embeddings generated yet (unknown status)
        # - True if NPU was used for any embeddings
        # - False if only fallback was used
        npu_available = None if total == 0 else npu_count > 0

        return JSONResponse(
            {
                "status": "success",
                "embedding_stats": stats,
                "npu_available": npu_available,
            }
        )
    except ImportError as e:
        logger.warning("NPU embeddings module not available: %s", e)
        return JSONResponse(
            {
                "status": "unavailable",
                "message": "NPU embeddings module not loaded",
                "embedding_stats": None,
            }
        )
    except Exception as e:
        logger.error("Failed to get embedding stats: %s", e)
        return JSONResponse(
            {
                "status": "error",
                "message": str(e),
                "embedding_stats": None,
            }
        )


@router.post("/embedding-stats/reset")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reset_embedding_stats",
    error_code_prefix="CODEBASE",
)
async def reset_embedding_stats_endpoint() -> JSONResponse:
    """
    Reset NPU embedding statistics.

    Issue #681: Allows clearing metrics for benchmarking or after
    configuration changes.

    Returns:
        JSONResponse confirming reset.
    """
    try:
        from ..npu_embeddings import reset_embedding_stats

        await reset_embedding_stats()
        return JSONResponse(
            {
                "status": "success",
                "message": "Embedding statistics reset successfully",
            }
        )
    except ImportError as e:
        logger.warning("NPU embeddings module not available: %s", e)
        return JSONResponse(
            {
                "status": "unavailable",
                "message": "NPU embeddings module not loaded",
            }
        )
    except Exception as e:
        logger.error("Failed to reset embedding stats: %s", e)
        return JSONResponse(
            {
                "status": "error",
                "message": str(e),
            }
        )


@router.get("/problems")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_codebase_problems",
    error_code_prefix="CODEBASE",
)
async def get_codebase_problems(problem_type: Optional[str] = None):
    """Get real code problems detected during analysis"""
    code_collection = await asyncio.to_thread(get_code_collection)
    all_problems = []
    storage_type = "chromadb"

    # Try ChromaDB first (Issue #315 - use extracted helpers)
    if code_collection:
        try:
            all_problems = _fetch_problems_from_chromadb(code_collection, problem_type)
            logger.info("Retrieved %s problems from ChromaDB", len(all_problems))
        except Exception as chroma_error:
            logger.warning(
                "ChromaDB query failed: %s, falling back to Redis", chroma_error
            )
            code_collection = None

    # Fallback to Redis if ChromaDB fails
    if not code_collection:
        all_problems, success = await _fetch_problems_from_redis(problem_type)
        if not success:
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "problems": [],
                }
            )
        storage_type = "redis"

    # Sort by severity (high, medium, low)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    all_problems.sort(
        key=lambda x: (
            severity_order.get(x.get("severity", "low"), 3),
            x.get("file_path", ""),
        )
    )

    return JSONResponse(
        {
            "status": "success",
            "problems": all_problems,
            "total_count": len(all_problems),
            "problem_types": list(set(p.get("type", "unknown") for p in all_problems)),
            "storage_type": storage_type,
        }
    )
