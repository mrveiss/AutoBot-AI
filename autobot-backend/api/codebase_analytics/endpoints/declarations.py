# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Code declarations endpoints
"""

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from utils.chromadb_client import get_all_paginated

from ..storage import get_code_collection

logger = get_logger(__name__)

router = APIRouter()


def _query_chromadb_declarations(code_collection, source_id: str | None = None) -> tuple:
    """Helper for get_code_declarations (#1088, #1710: per-source filter).

    Returns:
        Tuple of (declarations_list, storage_type_str)
    """
    all_declarations = []
    storage_type = "chromadb"
    try:
        if source_id:
            where_filter = {
                "$and": [
                    {"type": {"$in": ["function", "class"]}},
                    {"source_id": source_id},
                ]
            }
        else:
            where_filter = {"type": {"$in": ["function", "class"]}}
        results = get_all_paginated(
            code_collection,
            where=where_filter,
            include=["metadatas"],
        )
        for metadata in results.get("metadatas", []):
            decl = {
                "name": metadata.get("name", ""),
                "type": metadata.get("type", ""),
                "file_path": metadata.get("file_path", ""),
                "line_number": (int(metadata.get("start_line", 0)) if metadata.get("start_line") else 0),
                "usage_count": 1,
                "is_exported": True,
                "parameters": (metadata.get("parameters", "").split(",") if metadata.get("parameters") else []),
            }
            all_declarations.append(decl)
        logger.info("Retrieved %s declarations from ChromaDB", len(all_declarations))
    except Exception as chroma_error:
        logger.warning(f"ChromaDB query failed: {chroma_error}, returning empty declarations")
    return all_declarations, storage_type


def _build_declarations_response(all_declarations: list, storage_type: str) -> dict:
    """Helper for get_code_declarations. Count types, sort, and build response dict. Ref: #1088."""
    functions = sum(1 for d in all_declarations if d.get("type") == "function")
    classes = sum(1 for d in all_declarations if d.get("type") == "class")
    variables = sum(1 for d in all_declarations if d.get("type") == "variable")
    all_declarations.sort(key=lambda x: x.get("usage_count", 0), reverse=True)
    return {
        "status": "success",
        "declarations": all_declarations,
        "total_count": len(all_declarations),
        "functions": functions,
        "classes": classes,
        "variables": variables,
        "storage_type": storage_type,
    }


@router.get("/declarations")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_declarations",
    error_code_prefix="CODEBASE",
)
async def get_code_declarations(
    declaration_type: str | None = None,
    source_id: str | None = None,
):
    """Get code declarations (#1710: per-source filtering)."""
    code_collection = await asyncio.to_thread(get_code_collection)
    if not code_collection:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "No codebase data found. Run indexing first.",
                "declarations": [],
            }
        )
    all_declarations, storage_type = await asyncio.to_thread(_query_chromadb_declarations, code_collection, source_id)
    return JSONResponse(_build_declarations_response(all_declarations, storage_type))
