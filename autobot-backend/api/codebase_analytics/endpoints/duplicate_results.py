# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Result shaping and config-duplicate helpers for the duplicate endpoints.

Moved out of ``duplicates.py`` unchanged (#18013): that file is grandfathered at
its size ceiling and may not grow, and the scan-outcome handling this change adds
belongs next to the scan, not to the formatting.
"""

import asyncio
from pathlib import Path

from autobot_shared.logging_manager import get_logger
from utils.chromadb_client import get_all_paginated

from ..storage import get_code_collection

logger = get_logger(__name__)


def _convert_analysis_to_result(analysis, project_root: str) -> dict:
    """
    Convert analysis result to frontend-compatible format.

    Args:
        analysis: DuplicateAnalysis result
        project_root: Project root for relative paths

    Returns:
        Frontend-compatible result dict
    """
    duplicates_for_frontend = []
    for dup in analysis.duplicates:
        duplicates_for_frontend.append(
            {
                "file1": _make_relative_path(dup.file1, project_root),
                "file2": _make_relative_path(dup.file2, project_root),
                "start_line1": dup.start_line1,
                "end_line1": dup.end_line1,
                "start_line2": dup.start_line2,
                "end_line2": dup.end_line2,
                "similarity": round(dup.similarity * 100, 1),
                "lines": dup.line_count,
                "code_snippet": dup.code_snippet[:200] if dup.code_snippet else "",
            }
        )

    return {
        "status": "success",
        "duplicates": duplicates_for_frontend,
        "total_count": analysis.total_duplicates,
        "returned_count": len(duplicates_for_frontend),
        "truncated": analysis.truncated,
        "high_similarity_count": analysis.high_similarity_count,
        "medium_similarity_count": analysis.medium_similarity_count,
        "low_similarity_count": analysis.low_similarity_count,
        "total_duplicate_lines": analysis.total_duplicate_lines,
        "files_analyzed": analysis.files_analyzed,
        "scan_timestamp": analysis.scan_timestamp,
        "storage_type": "live_analysis",
    }


def _make_relative_path(path: str, project_root: str) -> str:
    """Convert absolute path to relative path for cleaner display."""
    try:
        return str(Path(path).relative_to(project_root))
    except ValueError:
        return path


def _get_chromadb_fallback(error_msg: str, source_id: str | None = None) -> dict | None:
    """
    Get cached duplicates from ChromaDB as fallback.

    Issue #1772: source_id filters to per-project data.

    Args:
        error_msg: Error message to include in warning
        source_id: Optional source ID for per-project scoping

    Returns:
        Fallback result dict or None if unavailable
    """
    code_collection = get_code_collection()
    if not code_collection:
        return None

    try:
        if source_id:
            where_filter = {
                "$and": [
                    {"type": "duplicate"},
                    {"source_id": source_id},
                ]
            }
        else:
            where_filter = {"type": "duplicate"}
        results = get_all_paginated(code_collection, where=where_filter, include=["metadatas"])

        all_duplicates = []
        for metadata in results.get("metadatas", []):
            all_duplicates.append(
                {
                    "file1": metadata.get("file1", ""),
                    "file2": metadata.get("file2", ""),
                    "similarity": float(metadata.get("similarity", 0)),
                    "lines": int(metadata.get("lines", 0)),
                    "code_snippet": metadata.get("code_snippet", ""),
                }
            )

        return {
            "status": "success",
            "duplicates": all_duplicates,
            "total_count": len(all_duplicates),
            "storage_type": "chromadb_fallback",
            "warning": f"Live analysis failed, showing cached results: {error_msg}",
        }
    except Exception:
        return None


def _build_detection_error_response() -> dict:
    """
    Build error response for duplicate detection failure.

    Issue #620: Extracted from get_duplicate_code to reduce function length.

    Returns:
        JSONResponse-compatible dict for error scenario
    """
    return {
        "status": "error",
        "message": "Duplicate detection failed",
        "duplicates": [],
        "total_count": 0,
    }


async def _run_semantic_config_detection(project_root: Path) -> dict | None:
    """
    Run semantic config duplicate detection.

    Issue #620: Extracted from detect_config_duplicates_endpoint.

    Args:
        project_root: Project root path

    Returns:
        Detection result dict or None if failed
    """
    from ..config_duplication_detector import ConfigDuplicationDetector

    try:
        detector = ConfigDuplicationDetector(
            str(project_root),
            use_semantic_analysis=True,
        )
        await asyncio.to_thread(detector.scan_directory)
        result = {
            "duplicates_found": 0,
            "duplicates": await detector.find_duplicates_async(),
            "report": await asyncio.to_thread(detector.generate_report),
            "files_scanned": detector.files_scanned,
            "files_failed": detector.files_failed,
        }
        result["duplicates_found"] = len(result["duplicates"])
        logger.info("Semantic config duplicate analysis complete")
        return result
    except Exception as e:
        logger.warning("Semantic analysis failed, falling back to standard: %s", e)
        return None


async def _run_standard_config_detection(project_root: Path) -> dict:
    """
    Run standard config duplicate detection.

    Issue #620: Extracted from detect_config_duplicates_endpoint.

    Args:
        project_root: Project root path

    Returns:
        Detection result dict
    """
    from ..config_duplication_detector import detect_config_duplicates

    return await asyncio.to_thread(detect_config_duplicates, str(project_root))


def _convert_config_duplicates_to_array(duplicates_dict: dict) -> list:
    """
    Convert duplicates dict to frontend-compatible array format.

    Issue #620: Extracted from detect_config_duplicates_endpoint.

    Args:
        duplicates_dict: Backend format {value: {value, count, sources, duplicates}}

    Returns:
        Frontend format [{value, count, locations: [{file, line}]}]
    """
    duplicates_array = []
    for value, details in duplicates_dict.items():
        all_locations = details.get("sources", []) + details.get("duplicates", [])
        duplicates_array.append(
            {
                "value": value,
                "count": details.get("count", len(all_locations)),
                "locations": [{"file": loc["file"], "line": loc["line"]} for loc in all_locations],
            }
        )
    return duplicates_array
