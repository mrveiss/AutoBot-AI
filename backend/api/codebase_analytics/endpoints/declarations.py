# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code declarations endpoints
"""

import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.utils.error_boundaries import ErrorCategory, with_error_handling

from ..storage import get_code_collection

logger = logging.getLogger(__name__)

router = APIRouter()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_code_declarations",
    error_code_prefix="CODEBASE",
)
@router.get("/declarations")
async def get_code_declarations(declaration_type: Optional[str] = None):
    """Get code declarations (functions, classes, variables) detected during analysis"""
    # Try ChromaDB first
    code_collection = get_code_collection()

    all_declarations = []

    if code_collection:
        try:
            # Query ChromaDB for functions and classes
            where_filter = {"type": {"$in": ["function", "class"]}}

            results = code_collection.get(where=where_filter, include=["metadatas"])

            # Extract declarations from metadata
            for metadata in results.get("metadatas", []):
                decl = {
                    "name": metadata.get("name", ""),
                    "type": metadata.get("type", ""),
                    "file_path": metadata.get("file_path", ""),
                    "line_number": (
                        int(metadata.get("start_line", 0))
                        if metadata.get("start_line")
                        else 0
                    ),
                    "usage_count": 1,  # Default, can be calculated later
                    "is_exported": True,  # Default
                    "parameters": (
                        metadata.get("parameters", "").split(",")
                        if metadata.get("parameters")
                        else []
                    ),
                }
                all_declarations.append(decl)

            storage_type = "chromadb"
            logger.info(
                "Retrieved %s declarations from ChromaDB", len(all_declarations)
            )

        except Exception as chroma_error:
            logger.warning(
                f"ChromaDB query failed: {chroma_error}, returning empty declarations"
            )
            # Declarations don't exist in old Redis structure, so just return empty
            storage_type = "chromadb"

    else:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "No codebase data found. Run indexing first.",
                "declarations": [],
            }
        )

    # Count by type
    functions = sum(1 for d in all_declarations if d.get("type") == "function")
    classes = sum(1 for d in all_declarations if d.get("type") == "class")
    variables = sum(1 for d in all_declarations if d.get("type") == "variable")

    # Sort by usage count (most used first)
    all_declarations.sort(key=lambda x: x.get("usage_count", 0), reverse=True)

    return JSONResponse(
        {
            "status": "success",
            "declarations": all_declarations,
            "total_count": len(all_declarations),
            "functions": functions,
            "classes": classes,
            "variables": variables,
            "storage_type": storage_type,
        }
    )
