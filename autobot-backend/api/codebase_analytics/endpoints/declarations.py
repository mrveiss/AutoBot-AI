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

from autobot_shared.error_boundaries import ErrorCategory, bounded, with_error_handling
from autobot_shared.logging_manager import get_logger
from utils.chromadb_client import get_all_paginated

from ..storage import get_code_collection
from .store_state import index_state, store_unavailable

logger = get_logger(__name__)

router = APIRouter()


def _declaration_filter(source_id: str | None) -> dict:
    """The store filter for declarations: function/class rows, scoped to a source when given."""
    kinds = {"type": {"$in": ["function", "class"]}}
    return {"$and": [kinds, {"source_id": source_id}]} if source_id else kinds


def _declaration_from_metadata(metadata: dict) -> dict:
    """One declaration as the panel reads it, from a stored row's metadata."""
    return {
        "name": metadata.get("name", ""),
        "type": metadata.get("type", ""),
        "file_path": metadata.get("file_path", ""),
        "line_number": (int(metadata.get("start_line", 0)) if metadata.get("start_line") else 0),
        "usage_count": 1,
        "is_exported": True,
        "parameters": (metadata.get("parameters", "").split(",") if metadata.get("parameters") else []),
    }


def _query_chromadb_declarations(code_collection, source_id: str | None = None) -> tuple:
    """Helper for get_code_declarations (#1088, #1710: per-source filter).

    A store read failure propagates (#17651): it used to be logged and returned
    as an empty list, which the panel could not tell from "nothing declared".

    Returns:
        Tuple of (declarations_list, storage_type_str)
    """
    results = get_all_paginated(code_collection, where=_declaration_filter(source_id), include=["metadatas"])
    all_declarations = [_declaration_from_metadata(m) for m in results.get("metadatas", [])]
    logger.info("Retrieved %s declarations from ChromaDB", len(all_declarations))
    return all_declarations, "chromadb"


def _build_declarations_response(all_declarations: list, storage_type: str, state: dict | None = None) -> dict:
    """Helper for get_code_declarations. Count types, sort, and build response dict. Ref: #1088."""
    functions = sum(1 for d in all_declarations if d.get("type") == "function")
    classes = sum(1 for d in all_declarations if d.get("type") == "class")
    variables = sum(1 for d in all_declarations if d.get("type") == "variable")
    all_declarations.sort(key=lambda x: x.get("usage_count", 0), reverse=True)
    return {
        "status": "success",
        **(state or {}),
        "declarations": all_declarations,
        "total_count": len(all_declarations),
        "functions": functions,
        "classes": classes,
        "variables": variables,
        "storage_type": storage_type,
    }


@router.get("/declarations")
@bounded(60.0)
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
        logger.error("declarations: the code index store could not be opened")
        raise store_unavailable()
    try:
        all_declarations, storage_type = await asyncio.to_thread(
            _query_chromadb_declarations, code_collection, source_id
        )
        state = await asyncio.to_thread(index_state, code_collection, source_id, bool(all_declarations))
    except Exception as store_error:
        logger.error("declarations: the code index store read failed: %s", store_error)
        raise store_unavailable() from store_error
    return JSONResponse(_build_declarations_response(all_declarations, storage_type, state))
