# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Codebase statistics endpoints
"""

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_codebase_stats",
    error_code_prefix="CODEBASE",
)
@router.get("/stats")
async def get_codebase_stats():
    """Get real codebase statistics from storage"""
    # Try ChromaDB first
    code_collection = get_code_collection()

    if code_collection:
        try:
            # Query ChromaDB for stats
            results = code_collection.get(ids=["codebase_stats"], include=["metadatas"])

            if results.get("metadatas") and len(results["metadatas"]) > 0:
                stats_metadata = results["metadatas"][0]

                # Extract stats from metadata
                stats = {}
                numeric_fields = [
                    "total_files",
                    "python_files",
                    "javascript_files",
                    "vue_files",
                    "config_files",
                    "other_files",
                    "total_lines",
                    "total_functions",
                    "total_classes",
                ]

                for field in numeric_fields:
                    if field in stats_metadata:
                        stats[field] = int(stats_metadata[field])

                if "average_file_size" in stats_metadata:
                    stats["average_file_size"] = float(
                        stats_metadata["average_file_size"]
                    )

                timestamp = stats_metadata.get("last_indexed", "Never")
                storage_type = "chromadb"

                return JSONResponse(
                    {
                        "status": "success",
                        "stats": stats,
                        "last_indexed": timestamp,
                        "storage_type": storage_type,
                    }
                )
            else:
                return JSONResponse(
                    {
                        "status": "no_data",
                        "message": "No codebase data found. Run indexing first.",
                        "stats": None,
                    }
                )

        except Exception as chroma_error:
            logger.warning(f"ChromaDB stats query failed: {chroma_error}")
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "stats": None,
                }
            )
    else:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "ChromaDB connection failed.",
                "stats": None,
            }
        )


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
        if hardcode_type:
            hardcodes_data = redis_client.get(f"codebase:hardcodes:{hardcode_type}")
            if hardcodes_data:
                all_hardcodes = json.loads(hardcodes_data)
        else:
            for key in redis_client.scan_iter(match="codebase:hardcodes:*"):
                hardcodes_data = redis_client.get(key)
                if hardcodes_data:
                    all_hardcodes.extend(json.loads(hardcodes_data))
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_codebase_problems",
    error_code_prefix="CODEBASE",
)
@router.get("/problems")
async def get_codebase_problems(problem_type: Optional[str] = None):
    """Get real code problems detected during analysis"""
    # Try ChromaDB first
    code_collection = get_code_collection()

    all_problems = []

    if code_collection:
        try:
            # Query ChromaDB for problems
            where_filter = {"type": "problem"}
            if problem_type:
                where_filter["problem_type"] = problem_type

            results = code_collection.get(where=where_filter, include=["metadatas"])

            # Extract problems from metadata
            for metadata in results.get("metadatas", []):
                all_problems.append(
                    {
                        "type": metadata.get("problem_type", ""),
                        "severity": metadata.get("severity", ""),
                        "file_path": metadata.get("file_path", ""),
                        "line_number": (
                            int(metadata.get("line_number", 0))
                            if metadata.get("line_number")
                            else None
                        ),
                        "description": metadata.get("description", ""),
                        "suggestion": metadata.get("suggestion", ""),
                    }
                )

            storage_type = "chromadb"
            logger.info(f"Retrieved {len(all_problems)} problems from ChromaDB")

        except Exception as chroma_error:
            logger.warning(
                f"ChromaDB query failed: {chroma_error}, falling back to Redis"
            ),
            code_collection = None

    # Fallback to Redis if ChromaDB fails
    if not code_collection:
        redis_client = await get_redis_connection()

        if redis_client:
            if problem_type:
                problems_data = redis_client.get(f"codebase:problems:{problem_type}")
                if problems_data:
                    all_problems = json.loads(problems_data)
            else:
                for key in redis_client.scan_iter(match="codebase:problems:*"):
                    problems_data = redis_client.get(key)
                    if problems_data:
                        all_problems.extend(json.loads(problems_data))
            storage_type = "redis"
        else:
            return JSONResponse(
                {
                    "status": "no_data",
                    "message": "No codebase data found. Run indexing first.",
                    "problems": [],
                }
            )

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
