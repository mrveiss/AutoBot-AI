# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base AI Stack Extraction API - Extracted from knowledge_ai_stack.py
(#16665) to keep that file's own growth within its grandfathered line-count
ceiling (#14236). Content extraction and optional auto-storage; not a read
path, so it carries no fact-visibility concern.

Endpoints:
- POST /extract - Extract structured knowledge from content, optionally storing it
"""

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request

from api.schemas_common import DataResponse
from api.schemas_knowledge import (
    AIStackKnowledgeExtractData,
    AIStackKnowledgeExtractionRequest,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from knowledge_factory import get_or_create_knowledge_base
from services.ai_stack_client import AIStackError, get_ai_stack_client
from utils.response_helpers import create_success_response, handle_ai_stack_error

logger = get_logger(__name__)

router = APIRouter(tags=["knowledge-ai-extraction"])


async def _store_single_fact_with_semaphore(
    kb,
    fact: Dict[str, Any],
    semaphore: asyncio.Semaphore,
    title: str | None,
    source: str | None,
    category: str | None,
) -> Dict[str, Any]:
    """Store a single fact with semaphore-bounded concurrency."""
    async with semaphore:
        try:
            return await kb.store_fact(
                content=fact.get("content", ""),
                metadata={
                    "title": title or fact.get("title", "Extracted Knowledge"),
                    "source": source,
                    "category": category,
                    "extraction_confidence": fact.get("confidence", 0.5),
                    "extracted_at": utc_timestamp(),
                },
            )
        except Exception as e:
            logger.warning("Failed to store extracted fact: %s", e)
            return {"status": "error", "message": "Operation failed"}


async def _store_extracted_facts(
    req: Request, extraction_result: dict, request_data: AIStackKnowledgeExtractionRequest
) -> List[Dict[str, Any]]:
    """Store extracted facts in knowledge base with parallel processing."""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if not kb_to_use:
        return []

    extracted_facts = extraction_result.get("extracted_facts")
    if not extracted_facts:
        return []

    # Use asyncio.gather for parallel fact storage with bounded concurrency
    semaphore = asyncio.Semaphore(50)

    # Store all facts in parallel
    results = await asyncio.gather(
        *[
            _store_single_fact_with_semaphore(
                kb_to_use,
                fact,
                semaphore,
                request_data.title,
                request_data.source,
                request_data.category,
            )
            for fact in extracted_facts
        ],
        return_exceptions=True,
    )

    # Filter successful results
    stored_facts = [result for result in results if isinstance(result, dict) and result.get("status") != "error"]

    logger.info("Stored %s extracted facts in knowledge base", len(stored_facts))
    return stored_facts


@router.post("/extract", response_model=DataResponse[AIStackKnowledgeExtractData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="extract_knowledge",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def extract_knowledge(
    request_data: AIStackKnowledgeExtractionRequest,
    req: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Extract structured knowledge from content using AI Stack capabilities.

    This endpoint uses AI Stack's knowledge extraction agent to identify
    and structure knowledge from various content types.

    Issue #744: Requires authenticated user.
    """
    try:
        ai_client = await get_ai_stack_client()

        # Extract knowledge using AI Stack
        extraction_result = await ai_client.extract_knowledge(
            content=request_data.content,
            content_type=request_data.content_type,
            extraction_mode=request_data.extraction_mode,
        )

        # Optionally store extracted knowledge in local knowledge base
        stored_facts = []
        if request_data.auto_store:
            try:
                stored_facts = await _store_extracted_facts(req, extraction_result, request_data)
            except Exception as e:
                logger.warning("Auto-storage of extracted knowledge failed: %s", e)

        return create_success_response(
            {
                "extraction_result": extraction_result,
                "auto_stored": request_data.auto_store,
                "stored_facts_count": len(stored_facts),
                "stored_facts": stored_facts if stored_facts else None,
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "Knowledge extraction")
