# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
KB Librarian API — LLM-mediated librarian agent interface.

Mounted at ``/api/kb-librarian`` (issue #3402).

Endpoints:
    - ``POST /query``      — Process a natural-language query through the
                            KBLibrarianAgent: intent detection, similarity
                            search, and optional LLM auto-summarisation.
                            Accepts per-request overrides for max_results,
                            similarity_threshold, and auto_summarize.
    - ``GET  /status``     — Return the runtime configuration of the
                            librarian agent singleton (enabled flag,
                            threshold, max results, summarise, KB active).
    - ``PUT  /configure``  — Update librarian agent runtime parameters:
                            enabled flag, similarity_threshold (0.0–1.0),
                            max_results (>=1), and auto_summarize.

What does NOT belong here:
    - Raw KB document CRUD → api/knowledge.py (``/api/knowledge_base/*``)
    - Chat-session knowledge lifecycle → api/chat_knowledge.py
      (``/api/chat-knowledge/*``)

Overlap note (issue #3336):
    ``POST /query`` overlaps in *outcome* with ``POST /api/knowledge_base/search``
    but routes through a stateful agent singleton with per-request parameter
    overrides and LLM summarisation.  It is a higher-level abstraction, not a
    duplicate.
"""

from fastapi import APIRouter, Depends, HTTPException

from agents.kb_librarian_agent import get_kb_librarian
from api.schemas_knowledge import (
    KbLibrarianConfigureResponse,
    KbLibrarianStatusResponse,
    KBQuery,
    KBQueryResponse,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/query", response_model=KBQueryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="query_knowledge_base",
    error_code_prefix="KB_LIBRARIAN",
)
async def query_knowledge_base(
    kb_query: KBQuery,
    current_user: dict = Depends(get_current_user),
):
    """Query the knowledge base using the KB Librarian Agent.

    Routes the query through the KBLibrarianAgent singleton: intent detection,
    similarity search, and optional LLM auto-summarisation.  Per-request
    overrides for max_results, similarity_threshold, and auto_summarize are
    applied temporarily and restored after the call.

    Args:
        kb_query: The query parameters including optional per-request overrides.

    Returns:
        KBQueryResponse with search results and optional summary.
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/status", response_model=KbLibrarianStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_kb_librarian_status",
    error_code_prefix="KB_LIBRARIAN",
)
async def get_kb_librarian_status(
    current_user: dict = Depends(get_current_user),
):
    """Return the runtime configuration of the KB Librarian Agent singleton.

    Returns:
        Dict containing enabled, similarity_threshold, max_results,
        auto_summarize, and knowledge_base_active.
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/configure", response_model=KbLibrarianConfigureResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="configure_kb_librarian",
    error_code_prefix="KB_LIBRARIAN",
)
async def configure_kb_librarian(
    enabled: bool | None = None,
    similarity_threshold: float | None = None,
    max_results: int | None = None,
    auto_summarize: bool | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Update KB Librarian Agent runtime parameters.

    All parameters are optional; only supplied values are changed.

    Args:
        enabled: Whether the KB Librarian is enabled.
        similarity_threshold: Minimum similarity score (0.0–1.0).
        max_results: Maximum number of results to return (>=1).
        auto_summarize: Whether to automatically summarise findings.

    Returns:
        Dict with confirmation message and updated configuration values.
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

    except ValueError:
        raise HTTPException(status_code=400, detail="Internal server error")
    except Exception as e:
        logger.error("Error configuring KB Librarian: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
