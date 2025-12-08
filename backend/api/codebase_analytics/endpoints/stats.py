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

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from ..storage import get_redis_connection, get_code_collection
from .shared import _in_memory_storage

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_stats_metadata(stats_metadata: dict) -> dict:
    """Parse stats from ChromaDB metadata. (Issue #315 - extracted)"""
    stats = {}
    numeric_fields = [
        "total_files", "python_files", "javascript_files", "vue_files",
        "config_files", "other_files", "total_lines", "total_functions", "total_classes",
    ]
    for field in numeric_fields:
        if field in stats_metadata:
            stats[field] = int(stats_metadata[field])

    if "average_file_size" in stats_metadata:
        stats["average_file_size"] = float(stats_metadata["average_file_size"])

    return stats


def _no_data_response(message: str = "No codebase data found. Run indexing first."):
    """Return standardized no-data response. (Issue #315 - extracted)"""
    return JSONResponse({"status": "no_data", "message": message, "stats": None})


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_codebase_stats",
    error_code_prefix="CODEBASE",
)
@router.get("/stats")
async def get_codebase_stats():
    """Get real codebase statistics from storage"""
    code_collection = get_code_collection()

    if not code_collection:
        return _no_data_response("ChromaDB connection failed.")

    try:
        results = code_collection.get(ids=["codebase_stats"], include=["metadatas"])
    except Exception as chroma_error:
        logger.warning(f"ChromaDB stats query failed: {chroma_error}")
        return _no_data_response()

    # Check if we have data
    if not results.get("metadatas") or len(results["metadatas"]) == 0:
        return _no_data_response()

    # Parse and return stats (Issue #315 - use extracted helper)
    stats_metadata = results["metadatas"][0]
    stats = _parse_stats_metadata(stats_metadata)

    return JSONResponse({
        "status": "success",
        "stats": stats,
        "last_indexed": stats_metadata.get("last_indexed", "Never"),
        "storage_type": "chromadb",
    })


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_hardcoded_values",
    error_code_prefix="CODEBASE",
)
@router.get("/hardcodes")
async def get_hardcoded_values(hardcode_type: Optional[str] = None):
    """Get real hardcoded values found in the codebase"""
    redis_client = await get_redis_connection()

    all_hardcodes = []

    if redis_client:
        # Issue #361 - avoid blocking - wrap Redis ops in thread pool
        def _fetch_hardcodes():
            results = []
            if hardcode_type:
                hardcodes_data = redis_client.get(f"codebase:hardcodes:{hardcode_type}")
                if hardcodes_data:
                    results = json.loads(hardcodes_data)
            else:
                for key in redis_client.scan_iter(match="codebase:hardcodes:*"):
                    hardcodes_data = redis_client.get(key)
                    if hardcodes_data:
                        results.extend(json.loads(hardcodes_data))
            return results

        all_hardcodes = await asyncio.to_thread(_fetch_hardcodes)
        storage_type = "redis"
    else:
        if not _in_memory_storage:
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "hardcodes": [],
                }
            )

        storage = _in_memory_storage
        if hardcode_type:
            hardcodes_data = storage.get(f"codebase:hardcodes:{hardcode_type}")
            if hardcodes_data:
                all_hardcodes = json.loads(hardcodes_data)
        else:
            for key in storage.scan_iter("codebase:hardcodes:*"):
                hardcodes_data = storage.get(key)
                if hardcodes_data:
                    all_hardcodes.extend(json.loads(hardcodes_data))
        storage_type = "memory"

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
    """Fetch problems from Redis. Returns (problems, success). (Issue #315 - extracted)"""
    redis_client = await get_redis_connection()
    if not redis_client:
        return [], False

    # Issue #361 - avoid blocking - wrap Redis ops in thread pool
    def _fetch_problems():
        results = []
        if problem_type:
            problems_data = redis_client.get(f"codebase:problems:{problem_type}")
            if problems_data:
                results = json.loads(problems_data)
        else:
            for key in redis_client.scan_iter(match="codebase:problems:*"):
                problems_data = redis_client.get(key)
                if problems_data:
                    results.extend(json.loads(problems_data))
        return results

    problems = await asyncio.to_thread(_fetch_problems)
    return problems, True


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_codebase_problems",
    error_code_prefix="CODEBASE",
)
@router.get("/problems")
async def get_codebase_problems(problem_type: Optional[str] = None):
    """Get real code problems detected during analysis"""
    code_collection = get_code_collection()
    all_problems = []
    storage_type = "chromadb"

    # Try ChromaDB first (Issue #315 - use extracted helpers)
    if code_collection:
        try:
            all_problems = _fetch_problems_from_chromadb(code_collection, problem_type)
            logger.info(f"Retrieved {len(all_problems)} problems from ChromaDB")
        except Exception as chroma_error:
            logger.warning(f"ChromaDB query failed: {chroma_error}, falling back to Redis")
            code_collection = None

    # Fallback to Redis if ChromaDB fails
    if not code_collection:
        all_problems, success = await _fetch_problems_from_redis(problem_type)
        if not success:
            return JSONResponse({
                "status": "no_data",
                "message": "No codebase data found. Run indexing first.",
                "problems": [],
            })
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
