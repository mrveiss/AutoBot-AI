# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
KB Librarian API — LLM-mediated librarian agent interface.

Responsibility (issue #3336):
    This module exposes the ``KBLibrarianAgent`` (``agents/kb_librarian_agent.py``)
    as an HTTP API.  Its routes are **NOT currently registered** in any router
    loader (``initialization/router_registry/``).  All routes therefore return
    404 in every deployed environment.

    The librarian agent layer is also used internally by ``conversation.py``
    via a direct Python import; it does not need an HTTP surface for that use.

Scope (intended, if re-registered):
    - ``POST /query``      — Process a natural-language query through the
                            librarian agent (intent detection, similarity
                            search, optional auto-summarisation).
    - ``GET  /status``     — Return runtime configuration of the librarian
                            agent singleton.
    - ``PUT  /configure``  — Update librarian agent runtime parameters
                            (enabled flag, threshold, max results, summarise).

What does NOT belong here:
    - Raw KB document CRUD → api/knowledge.py (``/api/knowledge_base/*``)
    - Chat-session knowledge lifecycle → api/chat_knowledge.py
      (``/api/chat-knowledge/*``)

Overlap note (issue #3336):
    ``POST /query`` overlaps in *outcome* with ``POST /api/knowledge_base/search``
    but routes through a stateful agent singleton with per-request parameter
    overrides and LLM summarisation.  It is a higher-level abstraction, not a
    duplicate.  If this router is re-registered, its mount point should be
    ``/api/kb-librarian`` and the e2e tests in
    ``autobot-frontend/tests/e2e/kb-librarian-api.spec.ts`` can be enabled.

DEPRECATION WARNING:
    All routes in this module emit a WARNING-level log on every invocation
    until the router is formally re-registered or removed.  See issue #3336.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.kb_librarian_agent import get_kb_librarian
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from type_defs.common import Metadata

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

    .. deprecated::
        This router is not registered in any router loader (issue #3336).
        This endpoint is unreachable in all deployed environments.
        For general KB search use POST /api/knowledge_base/search.
        For chat-scoped search use POST /api/chat-knowledge/search.

    Args:
        kb_query: The query parameters

    Returns:
        KBQueryResponse with search results
    """
    logger.warning(
        "DEPRECATED: kb_librarian /query called but this router is not registered "
        "(issue #3336). Use /api/knowledge_base/search for general KB search."
    )
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_kb_librarian_status",
    error_code_prefix="KB_LIBRARIAN",
)
@router.get("/status")
async def get_kb_librarian_status():
    """Get the status of the KB Librarian Agent.

    .. deprecated::
        This router is not registered in any router loader (issue #3336).
        This endpoint is unreachable in all deployed environments.

    Returns:
        Status information about the KB Librarian
    """
    logger.warning(
        "DEPRECATED: kb_librarian /status called but this router is not registered "
        "(issue #3336)."
    )
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

    .. deprecated::
        This router is not registered in any router loader (issue #3336).
        This endpoint is unreachable in all deployed environments.

    Args:
        enabled: Whether the KB Librarian is enabled
        similarity_threshold: Minimum similarity score (0.0-1.0)
        max_results: Maximum number of results to return
        auto_summarize: Whether to automatically summarize findings

    Returns:
        Updated configuration
    """
    logger.warning(
        "DEPRECATED: kb_librarian /configure called but this router is not "
        "registered (issue #3336)."
    )
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
