# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AI Document CRUD + refinement API (Issue #3245).

Endpoints
---------
POST   /documents                    — create a new AI document
GET    /documents                    — list documents owned by current user
GET    /documents/{doc_id}           — fetch a single document
PUT    /documents/{doc_id}           — update title/content/tags/metadata
DELETE /documents/{doc_id}           — delete a document
POST   /documents/{doc_id}/refine    — AI-refine a section using source facts

All endpoints require authentication.  Users can only read/update/delete their
own documents.

Storage
-------
Each document is serialised as a JSON blob under the ``main`` Redis database:

    Key:   autobot:ai_document:{doc_id}
    Index: autobot:ai_documents:by_user:{user_id}  (Redis Set of doc IDs)
"""

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas_knowledge import (
    AIDocumentListResponse,
    AIDocumentResponse,
    CreateDocumentRequest,
    RefineDocumentRequest,
    UpdateDocumentRequest,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from constants.ttl_constants import TTL_365_DAYS
from models.document import AIDocument

logger = get_logger(__name__)

router = APIRouter(tags=["ai-documents"])

# Redis key for the per-user document index
_USER_INDEX_KEY = "autobot:ai_documents:by_user:{user_id}"


# ============================================================================
# Request / response schemas
# ============================================================================


# ============================================================================
# Helpers
# ============================================================================


def _user_index_key(user_id: str) -> str:
    return _USER_INDEX_KEY.format(user_id=user_id)


def _owner_id(current_user: dict) -> str:
    """Extract a stable user ID string from the JWT payload dict."""
    return current_user.get("user_id") or current_user.get("id") or current_user.get("sub") or "anonymous"


async def _load_document(redis, doc_id: str) -> AIDocument | None:
    """Return the document or None if the key is missing."""
    raw = await redis.get(f"autobot:ai_document:{doc_id}")
    if raw is None:
        return None
    return AIDocument.model_validate(json.loads(raw))


async def _save_document(redis, doc: AIDocument) -> None:
    """Persist a document and its TTL; index under owner."""
    payload = doc.model_dump_json()
    pipe = redis.pipeline(transaction=False)
    pipe.set(doc.redis_key(), payload, ex=TTL_365_DAYS)
    pipe.sadd(_user_index_key(doc.user_id), doc.id)
    await pipe.execute()


async def _assert_ownership(doc: AIDocument, user_id: str) -> None:
    """Raise HTTP 403 if the document is not owned by ``user_id``."""
    if doc.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorised to access this document")


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/documents", status_code=201, response_model=AIDocumentResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_ai_document",
    error_code_prefix="DOCUMENTS",
)
async def create_document(
    body: CreateDocumentRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Create a new AI document from a KB-grounded response.

    Issue #3245: User can save any AI response as a named document.
    """
    uid = _owner_id(current_user)
    doc = AIDocument(
        title=body.title,
        content=body.content,
        source_facts=body.source_facts,
        source_session_id=body.source_session_id,
        source_message_id=body.source_message_id,
        tags=body.tags,
        metadata=body.metadata,
        user_id=uid,
    )
    redis = await get_async_redis_client(database="main")
    await _save_document(redis, doc)
    logger.info("Created AI document %s for user %s", doc.id, uid)
    return doc.model_dump()


@router.get("/documents", response_model=AIDocumentListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_ai_documents",
    error_code_prefix="DOCUMENTS",
)
async def list_documents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """List AI documents owned by the authenticated user.

    Issue #3245: Documents listed and searchable in a documents view.
    """
    uid = _owner_id(current_user)
    redis = await get_async_redis_client(database="main")
    doc_ids = await redis.smembers(_user_index_key(uid))
    if not doc_ids:
        return {"documents": [], "total": 0}

    # Batch-fetch all documents then sort by updated_at (newest first)
    pipe = redis.pipeline(transaction=False)
    for doc_id in doc_ids:
        pipe.get(f"autobot:ai_document:{doc_id}")
    raw_values = await pipe.execute()

    documents: List[AIDocument] = []
    for raw in raw_values:
        if raw is not None:
            try:
                documents.append(AIDocument.model_validate(json.loads(raw)))
            except Exception as exc:
                logger.warning("Skipping malformed document blob: %s", exc)

    documents.sort(key=lambda d: d.updated_at, reverse=True)
    total = len(documents)
    page = documents[offset : offset + limit]
    return {"documents": [d.model_dump() for d in page], "total": total}


@router.get("/documents/{doc_id}", response_model=AIDocumentResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_ai_document",
    error_code_prefix="DOCUMENTS",
)
async def get_document(
    doc_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Fetch a single AI document by ID."""
    uid = _owner_id(current_user)
    redis = await get_async_redis_client(database="main")
    doc = await _load_document(redis, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    await _assert_ownership(doc, uid)
    return doc.model_dump()


@router.put("/documents/{doc_id}", response_model=AIDocumentResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_ai_document",
    error_code_prefix="DOCUMENTS",
)
async def update_document(
    doc_id: str,
    body: UpdateDocumentRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Partially update title, content, tags, or metadata of an AI document.

    Issue #3245: Document is editable in-frontend (markdown or rich text).
    """
    uid = _owner_id(current_user)
    redis = await get_async_redis_client(database="main")
    doc = await _load_document(redis, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    await _assert_ownership(doc, uid)

    if "title" in body.model_fields_set:
        doc.title = body.title
    if "content" in body.model_fields_set:
        doc.content = body.content
    if "tags" in body.model_fields_set:
        doc.tags = body.tags
    if "metadata" in body.model_fields_set:
        doc.metadata = body.metadata
    doc.touch()

    await _save_document(redis, doc)
    return doc.model_dump()


@router.delete("/documents/{doc_id}", status_code=204, response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_ai_document",
    error_code_prefix="DOCUMENTS",
)
async def delete_document(
    doc_id: str,
    current_user: dict = Depends(get_current_user),
) -> None:
    """Delete an AI document."""
    uid = _owner_id(current_user)
    redis = await get_async_redis_client(database="main")
    doc = await _load_document(redis, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    await _assert_ownership(doc, uid)

    pipe = redis.pipeline(transaction=False)
    pipe.delete(doc.redis_key())
    pipe.srem(_user_index_key(uid), doc_id)
    await pipe.execute()
    logger.info("Deleted AI document %s for user %s", doc_id, uid)


@router.post("/documents/{doc_id}/refine", response_model=AIDocumentResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="refine_ai_document",
    error_code_prefix="DOCUMENTS",
)
async def refine_document(
    doc_id: str,
    body: RefineDocumentRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """AI-refine a section of an AI document using its source facts.

    Issue #3245: User can send a refinement prompt scoped to the document's
    source facts.  The LLM edits the document in-place and the updated
    content is saved back to Redis.

    The LLM call is delegated to the AIStackClient.  If the AI stack is
    unavailable the endpoint returns an appropriate error rather than
    silently degrading.
    """
    uid = _owner_id(current_user)
    redis = await get_async_redis_client(database="main")
    doc = await _load_document(redis, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    await _assert_ownership(doc, uid)

    try:
        from services.ai_stack_client import get_ai_stack_client

        client = await get_ai_stack_client()
        system_prompt = (
            "You are a document editor.  Apply the user's instruction to the "
            "document content and return ONLY the updated document content — no "
            "preamble, no explanation.  Preserve markdown formatting."
        )
        if body.section:
            user_prompt = (
                f"Document title: {doc.title}\n\n"
                f"Current content:\n{doc.content}\n\n"
                f"Scope: section '{body.section}'\n"
                f"Instruction: {body.instruction}"
            )
        else:
            user_prompt = (
                f"Document title: {doc.title}\n\n"
                f"Current content:\n{doc.content}\n\n"
                f"Instruction: {body.instruction}"
            )

        refined_content = await client.generate(
            system=system_prompt,
            prompt=user_prompt,
            context_ids=doc.source_facts,
        )
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="AI Stack client not available; refinement requires an active LLM service",
        )
    except Exception as exc:
        logger.error("Refinement LLM call failed for document %s: %s", doc_id, exc)
        raise HTTPException(status_code=502, detail="LLM refinement failed") from exc

    doc.content = refined_content
    doc.touch()
    await _save_document(redis, doc)
    logger.info("Refined AI document %s for user %s", doc_id, uid)
    return doc.model_dump()
