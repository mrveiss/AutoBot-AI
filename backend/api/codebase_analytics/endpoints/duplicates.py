# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Duplicate code detection endpoints
"""

import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from ..storage import get_code_collection

logger = logging.getLogger(__name__)

router = APIRouter()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_duplicate_code",
    error_code_prefix="CODEBASE",
)
@router.get("/duplicates")
async def get_duplicate_code():
    """Get duplicate code detected during analysis (using semantic similarity in ChromaDB)"""
    # Try ChromaDB first
    code_collection = get_code_collection()

    all_duplicates = []

    if code_collection:
        try:
            # Query ChromaDB for duplicate markers
            # Note: Duplicates will be detected via semantic similarity when we regenerate
            results = code_collection.get(
                where={"type": "duplicate"}, include=["metadatas"]
            )

            # Extract duplicates from metadata
            for metadata in results.get("metadatas", []):
                duplicate = {
                    "code_snippet": metadata.get("code_snippet", ""),
                    "files": (
                        metadata.get("files", "").split(",")
                        if metadata.get("files")
                        else []
                    ),
                    "similarity_score": (
                        float(metadata.get("similarity_score", 0.0))
                        if metadata.get("similarity_score")
                        else 0.0
                    ),
                    "line_numbers": metadata.get("line_numbers", ""),
                }
                all_duplicates.append(duplicate)

            storage_type = "chromadb"
            logger.info(f"Retrieved {len(all_duplicates)} duplicates from ChromaDB")

        except Exception as chroma_error:
            logger.warning(
                f"ChromaDB query failed: {chroma_error}, returning empty duplicates"
            )
            # Duplicates don't exist yet, will be generated during reindexing
            storage_type = "chromadb"

    else:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "No codebase data found. Run indexing first.",
                "duplicates": [],
            }
        )

    # Sort by number of files affected (most duplicated first)
    all_duplicates.sort(key=lambda x: len(x.get("files", [])), reverse=True)

    return JSONResponse(
        {
            "status": "success",
            "duplicates": all_duplicates,
            "total_count": len(all_duplicates),
            "storage_type": storage_type,
        }
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="detect_config_duplicates",
    error_code_prefix="CODEBASE",
)
@router.get("/config-duplicates")
async def detect_config_duplicates_endpoint():
    """
    Detect configuration value duplicates across codebase (Issue #341).

    Returns configuration values that appear in multiple files,
    helping enforce single-source-of-truth principle.

    Returns:
        JSONResponse with duplicate detection results
    """
    from ..config_duplication_detector import detect_config_duplicates

    # Get project root (4 levels up from this file: endpoints -> codebase_analytics -> api -> backend -> root)
    project_root = Path(__file__).resolve().parents[4]

    # Run detection
    result = detect_config_duplicates(str(project_root))

    return JSONResponse(
        {
            "status": "success",
            "duplicates_found": result["duplicates_found"],
            "duplicates": result["duplicates"],
            "report": result["report"],
        }
    )
