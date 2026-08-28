#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Chat Knowledge API — session-scoped knowledge lifecycle management.

Responsibility (issue #3336):
    This module owns all knowledge operations that are **scoped to a chat
    session**.  It is mounted at ``/api/chat-knowledge/*``.

Scope:
    - Creating and updating per-session knowledge contexts (topic, keywords,
      user ownership).
    - Associating or uploading files to a specific chat session.
    - Adding *temporary* knowledge facts that live only for the duration of
      a session.
    - Presenting pending-decision facts to the user and applying
      add-to-KB / keep-temporary / delete decisions.
    - Compiling an entire chat conversation into a permanent KB entry.
    - Session-fact preservation before conversation deletion (issue #547).

What does NOT belong here:
    - General KB document management (ingestion, tagging, categories) →
      api/knowledge.py  (mounted at ``/api/knowledge_base/*``)
    - LLM-mediated librarian queries → api/kb_librarian.py

Overlap note (issue #3336):
    The ``POST /search`` endpoint in this module delegates to
    ``KnowledgeBase.search()`` *and* additionally searches in-memory
    temporary facts for the requesting session.  It is NOT a duplicate of
    ``POST /api/knowledge_base/search``: it adds session-scoped temporary
    results that the global endpoint cannot see.  Keep both; they serve
    different consumers.
"""

import asyncio
import os
from datetime import datetime, timezone

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from api.chat_knowledge_manager import get_chat_knowledge_manager_instance
from api.schemas_common import DataResponse
from api.schemas_knowledge import (
    AddKnowledgeRequest,
    AssociateFileRequest,
    ChatKnowledgeCompileData,
    ChatKnowledgeContextData,
    ChatKnowledgeDecisionData,
    ChatKnowledgeFileAssocData,
    ChatKnowledgePendingData,
    ChatKnowledgeSearchRequest,
    ChatKnowledgeSearchResultData,
    ChatKnowledgeTempData,
    ChatKnowledgeUploadData,
    CompileChatRequest,
    CreateContextRequest,
    FileAssociationType,
    KnowledgeDecisionRequest,
    MarkFactsPreservedRequest,
    PreserveSessionFactsResponse,
    SessionFactsResponse,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import CategoryDefaults

# Import existing components

logger = get_logger(__name__)

router = APIRouter(tags=["chat_knowledge"])


# API Endpoints


@router.post("/context/create", response_model=DataResponse[ChatKnowledgeContextData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_chat_context",
    error_code_prefix="CHAT_KNOWLEDGE",
)
async def create_chat_context(request_data: CreateContextRequest, request: Request):
    """Create or update knowledge context for a chat (Issue #688: added user_id)."""
    try:
        manager = await get_chat_knowledge_manager_instance(request)
        context = await manager.create_or_update_context(
            chat_id=request_data.chat_id,
            topic=request_data.topic,
            keywords=request_data.keywords,
            user_id=request_data.user_id,
        )

        return {
            "success": True,
            "data": {
                "success": True,
                "chat_id": context.chat_id,
                "topic": context.topic,
                "keywords": context.keywords,
                "user_id": context.user_id,
                "created_at": context.created_at.isoformat(),
                "updated_at": context.updated_at.isoformat(),
            },
        }

    except Exception as e:
        logger.error("Failed to create context: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/files/associate", response_model=DataResponse[ChatKnowledgeFileAssocData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="associate_file_with_chat",
    error_code_prefix="CHAT_KNOWLEDGE",
)
async def associate_file_with_chat(request_data: AssociateFileRequest, request: Request):
    """Associate a file with a chat session"""
    try:
        manager = await get_chat_knowledge_manager_instance(request)
        association = await manager.associate_file(
            chat_id=request_data.chat_id,
            file_path=request_data.file_path,
            association_type=request_data.association_type,
            metadata=request_data.metadata,
        )

        return {
            "success": True,
            "data": {
                "success": True,
                "file_id": association.file_id,
                "file_name": association.file_name,
                "association_type": association.association_type.value,
                "created_at": association.created_at.isoformat(),
            },
        }

    except Exception as e:
        logger.error("Failed to associate file: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/files/upload/{chat_id}", response_model=DataResponse[ChatKnowledgeUploadData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="upload_file_to_chat",
    error_code_prefix="CHAT_KNOWLEDGE",
)
async def upload_file_to_chat(
    chat_id: str,
    request: Request,
    file: UploadFile = File(...),
    association_type: str = Form(default="upload"),
):
    """Upload a file and associate it with a chat"""
    try:
        manager = await get_chat_knowledge_manager_instance(request)

        # Save uploaded file (#1721)
        from autobot_shared.security.path_validator import validate_relative_path

        safe_name = f"{chat_id}_{os.path.basename(file.filename)}"
        file_path = str(
            validate_relative_path(
                safe_name,
                manager.storage_dir,
            )
        )

        content = await file.read()
        try:
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(content)
        except OSError as e:
            logger.error("Failed to write uploaded file %s: %s", file_path, e)
            raise HTTPException(status_code=500, detail="Failed to save file")

        # Associate with chat
        association = await manager.associate_file(
            chat_id=chat_id,
            file_path=file_path,
            association_type=FileAssociationType(association_type),
            metadata={"original_filename": file.filename},
        )

        return {"success": True, "data": {"success": True, "file_id": association.file_id, "file_path": file_path}}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to upload file: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/knowledge/add_temporary", response_model=DataResponse[ChatKnowledgeTempData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_temporary_knowledge",
    error_code_prefix="CHAT_KNOWLEDGE",
)
async def add_temporary_knowledge(request_data: AddKnowledgeRequest, request: Request):
    """Add temporary knowledge to chat context"""
    try:
        manager = await get_chat_knowledge_manager_instance(request)
        knowledge_id = await manager.add_temporary_knowledge(
            chat_id=request_data.chat_id, content=request_data.content, metadata=request_data.metadata
        )

        return {"success": True, "data": {"success": True, "knowledge_id": knowledge_id}}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to add temporary knowledge: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/knowledge/pending/{chat_id}", response_model=DataResponse[ChatKnowledgePendingData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pending_knowledge_decisions",
    error_code_prefix="CHAT_KNOWLEDGE",
)
async def get_pending_knowledge_decisions(chat_id: str, request: Request):
    """Get knowledge items pending user decision"""
    try:
        manager = await get_chat_knowledge_manager_instance(request)
        pending_items = await manager.get_knowledge_for_decision(chat_id)

        return {
            "success": True,
            "data": {
                "success": True,
                "pending_items": pending_items,
                "count": len(pending_items),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get pending knowledge: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/knowledge/decide", response_model=DataResponse[ChatKnowledgeDecisionData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="apply_knowledge_decision",
    error_code_prefix="CHAT_KNOWLEDGE",
)
async def apply_knowledge_decision(request_data: KnowledgeDecisionRequest, request: Request):
    """Apply user decision for temporary knowledge"""
    try:
        manager = await get_chat_knowledge_manager_instance(request)
        success = await manager.apply_knowledge_decision(
            chat_id=request_data.chat_id,
            knowledge_id=request_data.knowledge_id,
            decision=request_data.decision,
        )

        return {
            "success": True,
            "data": {
                "success": success,
                "message": f"Knowledge {request_data.decision.value} applied",
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to apply knowledge decision: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/compile", response_model=DataResponse[ChatKnowledgeCompileData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="compile_chat_to_knowledge",
    error_code_prefix="CHAT_KNOWLEDGE",
)
async def compile_chat_to_knowledge(request_data: CompileChatRequest, request: Request):
    """Compile entire chat conversation to knowledge base"""
    try:
        manager = await get_chat_knowledge_manager_instance(request)
        compiled = await manager.compile_chat_to_knowledge(
            chat_id=request_data.chat_id,
            title=request_data.title,
            include_system_messages=request_data.include_system_messages,
        )

        return {"success": True, "data": {"success": True, "compiled": compiled}}

    except Exception as e:
        logger.error("Failed to compile chat: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/search", response_model=DataResponse[ChatKnowledgeSearchResultData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_chat_knowledge",
    error_code_prefix="CHAT_KNOWLEDGE",
)
async def search_chat_knowledge(request_data: ChatKnowledgeSearchRequest, request: Request):
    """Search knowledge across chats or within specific chat"""
    try:
        manager = await get_chat_knowledge_manager_instance(request)
        results = await manager.search_chat_knowledge(
            query=request_data.query,
            chat_id=request_data.chat_id,
            include_temporary=request_data.include_temporary,
        )

        return {"success": True, "data": {"success": True, "results": results, "count": len(results)}}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to search knowledge: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/context/{chat_id}", response_model=DataResponse[ChatKnowledgeContextData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_chat_context",
    error_code_prefix="CHAT_KNOWLEDGE",
)
async def get_chat_context(chat_id: str, request: Request):
    """Get complete knowledge context for a chat"""
    try:
        manager = await get_chat_knowledge_manager_instance(request)
        context = manager.chat_contexts.get(chat_id)

        if not context:
            return {"success": False, "message": "No context found for chat", "data": None}

        file_associations = manager.file_associations.get(chat_id, [])

        return {
            "success": True,
            "data": {
                "success": True,
                "chat_id": context.chat_id,
                "topic": context.topic,
                "keywords": context.keywords,
                "created_at": context.created_at.isoformat(),
                "updated_at": context.updated_at.isoformat(),
                "temporary_knowledge_count": len(context.temporary_knowledge),
                "persistent_knowledge_count": len(context.persistent_knowledge_ids),
                "file_count": len(file_associations),
                "files": [
                    {
                        "file_id": f.file_id,
                        "file_name": f.file_name,
                        "type": f.association_type.value,
                        "size": f.size_bytes,
                    }
                    for f in file_associations
                ],
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get chat context: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Session Facts Endpoints (Issue #547)
# ============================================================================


@router.get("/chat/sessions/{session_id}/facts", response_model=SessionFactsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_session_facts",
    error_code_prefix="CHAT_KB",
)
async def get_session_facts(session_id: str, request: Request):
    """
    Get all knowledge base facts created during a specific session.

    Issue #547: This endpoint allows the frontend to preview facts
    that will be deleted when a conversation is deleted.

    Args:
        session_id: Chat session ID to get facts for

    Returns:
        List of facts with their metadata
    """
    # Get knowledge base from app state
    knowledge_base = getattr(request.app.state, "knowledge_base", None)
    if not knowledge_base:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        # Get facts for this session
        facts = await knowledge_base.get_facts_by_session(session_id)

        # Format response with relevant fields for frontend
        formatted_facts = []
        for fact in facts:
            formatted_facts.append(
                {
                    "id": fact.get("id"),
                    "content": fact.get("content", "")[:200] + ("..." if len(fact.get("content", "")) > 200 else ""),
                    "full_content": fact.get("content", ""),
                    "category": fact.get("category", CategoryDefaults.GENERAL),
                    "tags": fact.get("tags", []),
                    "important": fact.get("important", False),
                    "preserve": fact.get("preserve", False),
                    "created_at": fact.get("created_at"),
                }
            )

        return {
            "status": "success",
            "session_id": session_id,
            "fact_count": len(formatted_facts),
            "facts": formatted_facts,
        }

    except Exception as e:
        logger.error(f"Failed to get facts for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def _preserve_single_fact(
    knowledge_base,
    fact_id: str,
    session_id: str,
    preserve: bool,
    preserve_time: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Preserve a single fact with bounded concurrency."""
    async with semaphore:
        try:
            fact = await knowledge_base.get_fact(fact_id)
            if not fact:
                return {"status": "error", "fact_id": fact_id, "error": "not_found"}

            fact_session = await knowledge_base.get_session_for_fact(fact_id)
            if fact_session != session_id:
                return {"status": "error", "fact_id": fact_id, "error": "wrong_session"}

            metadata = fact.get("metadata", {})
            metadata["important"] = preserve
            metadata["preserve"] = preserve
            metadata["preserved_at"] = preserve_time
            metadata["preserved_from_deletion"] = True

            success = await knowledge_base.update_fact(fact_id=fact_id, metadata=metadata)
            if success:
                return {"status": "success", "fact_id": fact_id}
            else:
                return {"status": "error", "fact_id": fact_id, "error": "update_failed"}

        except Exception as e:
            logger.error(f"Error preserving fact {fact_id}: {e}")
            return {
                "status": "error",
                "fact_id": fact_id,
                "error": "Internal server error",
            }


def _count_preserve_results(results: list, session_id: str) -> tuple[int, int, list]:
    """Count results and collect error messages."""
    errors = []
    updated_count = 0
    failed_count = 0

    for result in results:
        if isinstance(result, Exception):
            errors.append(f"Unexpected error: {str(result)}")
            failed_count += 1
        elif result.get("status") == "success":
            updated_count += 1
        else:
            error_msg = result.get("error", "unknown")
            fact_id = result.get("fact_id", "unknown")
            if error_msg == "not_found":
                errors.append(f"Fact {fact_id} not found")
            elif error_msg == "wrong_session":
                errors.append(f"Fact {fact_id} does not belong to session {session_id}")
            else:
                errors.append(f"Error with fact {fact_id}: {error_msg}")
            failed_count += 1

    return updated_count, failed_count, errors


@router.post("/chat/sessions/{session_id}/facts/preserve", response_model=PreserveSessionFactsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="preserve_session_facts",
    error_code_prefix="CHAT_KB",
)
async def preserve_session_facts(session_id: str, request: Request, body: MarkFactsPreservedRequest):
    """
    Mark specific facts as preserved/important before session deletion.

    Issue #547: This allows users to select which facts to keep
    when deleting a conversation.

    Uses parallel processing with semaphore for optimal performance.

    Args:
        session_id: Chat session ID
        body: Request body with fact_ids and preserve flag

    Returns:
        Update result with counts
    """
    if len(body.fact_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 facts can be preserved at once")

    knowledge_base = getattr(request.app.state, "knowledge_base", None)
    if not knowledge_base:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        preserve_time = datetime.now(tz=timezone.utc).isoformat()
        semaphore = asyncio.Semaphore(20)

        results = await asyncio.gather(
            *[
                _preserve_single_fact(
                    knowledge_base,
                    fid,
                    session_id,
                    body.preserve,
                    preserve_time,
                    semaphore,
                )
                for fid in body.fact_ids
            ],
            return_exceptions=True,
        )

        updated_count, failed_count, errors = _count_preserve_results(results, session_id)

        return {
            "status": "success" if failed_count == 0 else "partial",
            "session_id": session_id,
            "updated_count": updated_count,
            "failed_count": failed_count,
            "errors": errors if errors else None,
        }

    except Exception as e:
        logger.error(f"Failed to preserve facts for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
