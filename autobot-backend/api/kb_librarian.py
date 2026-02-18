# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""KB Librarian API endpoints."""

import logging
from typing import List, Optional

from agents.kb_librarian_agent import get_kb_librarian
from backend.type_defs.common import Metadata
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter()
logger = logging.getLogger(__name__)


class KBQuery(BaseModel):
    """Knowledge base query request model."""

    query: str
    max_results: Optional[int] = None
    similarity_threshold: Optional[float] = None
    auto_summarize: Optional[bool] = None


class KBQueryResponse(BaseModel):
    """Knowledge base query response model."""

    enabled: bool
    is_question: bool
    query: str
    documents_found: int
    documents: List[Metadata]
    summary: Optional[str] = None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="query_knowledge_base",
    error_code_prefix="KB_LIBRARIAN",
)
@router.post("/query", response_model=KBQueryResponse)
async def query_knowledge_base(kb_query: KBQuery):
    """Query the knowledge base using the KB Librarian Agent.

    Args:
        kb_query: The query parameters

    Returns:
        KBQueryResponse with search results
    """
    try:
        kb_librarian = get_kb_librarian()

        # Override default settings if provided
        if kb_query.max_results is not None:
            original_max = kb_librarian.max_results
            kb_librarian.max_results = kb_query.max_results

        if kb_query.similarity_threshold is not None:
            original_threshold = kb_librarian.similarity_threshold
            kb_librarian.similarity_threshold = kb_query.similarity_threshold

        if kb_query.auto_summarize is not None:
            original_summarize = kb_librarian.auto_summarize
            kb_librarian.auto_summarize = kb_query.auto_summarize

        # Process the query
        result = await kb_librarian.process_query(kb_query.query)

        # Restore original settings
        if kb_query.max_results is not None:
            kb_librarian.max_results = original_max
        if kb_query.similarity_threshold is not None:
            kb_librarian.similarity_threshold = original_threshold
        if kb_query.auto_summarize is not None:
            kb_librarian.auto_summarize = original_summarize

        return KBQueryResponse(**result)

    except Exception as e:
        logger.error("Error querying knowledge base: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_kb_librarian_status",
    error_code_prefix="KB_LIBRARIAN",
)
@router.get("/status")
async def get_kb_librarian_status():
    """Get the status of the KB Librarian Agent.

    Returns:
        Status information about the KB Librarian
    """
    try:
        kb_librarian = get_kb_librarian()

        return {
            "enabled": kb_librarian.enabled,
            "similarity_threshold": kb_librarian.similarity_threshold,
            "max_results": kb_librarian.max_results,
            "auto_summarize": kb_librarian.auto_summarize,
            "knowledge_base_active": kb_librarian.knowledge_base is not None,
        }

    except Exception as e:
        logger.error("Error getting KB Librarian status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="configure_kb_librarian",
    error_code_prefix="KB_LIBRARIAN",
)
@router.put("/configure")
async def configure_kb_librarian(
    enabled: Optional[bool] = None,
    similarity_threshold: Optional[float] = None,
    max_results: Optional[int] = None,
    auto_summarize: Optional[bool] = None,
):
    """Configure the KB Librarian Agent settings.

    Args:
        enabled: Whether the KB Librarian is enabled
        similarity_threshold: Minimum similarity score (0.0-1.0)
        max_results: Maximum number of results to return
        auto_summarize: Whether to automatically summarize findings

    Returns:
        Updated configuration
    """
    try:
        kb_librarian = get_kb_librarian()

        if enabled is not None:
            kb_librarian.enabled = enabled

        if similarity_threshold is not None:
            if not 0.0 <= similarity_threshold <= 1.0:
                raise ValueError("similarity_threshold must be between 0.0 and 1.0")
            kb_librarian.similarity_threshold = similarity_threshold

        if max_results is not None:
            if max_results < 1:
                raise ValueError("max_results must be at least 1")
            kb_librarian.max_results = max_results

        if auto_summarize is not None:
            kb_librarian.auto_summarize = auto_summarize

        return {
            "message": "KB Librarian configuration updated",
            "enabled": kb_librarian.enabled,
            "similarity_threshold": kb_librarian.similarity_threshold,
            "max_results": kb_librarian.max_results,
            "auto_summarize": kb_librarian.auto_summarize,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Error configuring KB Librarian: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
