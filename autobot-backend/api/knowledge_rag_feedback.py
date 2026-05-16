# Copyright (c) mrveiss. All rights reserved.
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base RAG Annotation Feedback API (Issue #3240).

Receives explicit accept/reject annotation signals from the frontend
KnowledgeResearchPanel and records them as user-scoped retrieval feedback
events in the per-user Redis stream.

Endpoint:
- POST /rag-feedback  — record an accept/reject annotation for a source card
"""

import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from api.schemas_knowledge import RagFeedbackRequest
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from constants.ttl_constants import TTL_30_DAYS
from knowledge.schemas.mcp import RagFeedbackResponse
from knowledge.search_components.retrieval_learner import GLOBAL_USER

logger = get_logger(__name__)

router = APIRouter(tags=["knowledge-rag-feedback"])

# Redis stream TTL mirrors _store_feedback_in_stream (Issue #2102).
_STREAM_TTL_SECONDS = TTL_30_DAYS


@router.post("/rag-feedback", response_model=RagFeedbackResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="record_rag_feedback",
    error_code_prefix="KNOWLEDGE",
)
async def record_rag_feedback(
    body: RagFeedbackRequest,
    current_user: dict = Depends(get_current_user),
) -> RagFeedbackResponse:
    """Record a user's explicit accept/reject annotation for a retrieved source.

    Issue #3240: Writes to ``rag:feedback:{user_id}:{date}`` Redis stream so
    RetrievalLearner can consume the signal and update per-user retrieval
    patterns.  The authenticated user's ID from the JWT is used; body.user_id
    is accepted as a fallback for unauthenticated or service-level callers.

    Returns:
        {"status": "recorded", "stream_key": "..."} on success.
    """
    uid = current_user.get("user_id") or current_user.get("id") or body.user_id or GLOBAL_USER
    date_key = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    stream_key = f"rag:feedback:{uid}:{date_key}"

    # Encode the annotation as a pseudo-retrieval feedback event.
    # decision="accepted" → full positive trajectory; "rejected" → empty ranked list.
    is_accepted = body.decision == "accepted"
    entry = {
        "query_text": body.query,
        "retrieved_chunk_ids": json.dumps([body.source_url], ensure_ascii=False),
        "final_ranked_ids": json.dumps([body.source_url] if is_accepted else [], ensure_ascii=False),
        "complexity": "simple",
        "annotation": body.decision,
        "title": body.title,
        "timestamp": str(time.time()),
    }

    try:
        redis = await get_async_redis_client(database="analytics")
        if redis is None:
            logger.warning(
                "record_rag_feedback: Redis unavailable; annotation dropped for user %s",
                uid,
            )
            # Issue #5319 / #5407: emit ops-visible counter alongside the
            # warning.  reason="redis_down" - analytics Redis unreachable.
            from knowledge.metrics import autobot_kb_degradation_total

            autobot_kb_degradation_total.labels(endpoint="rag_feedback", reason="redis_down").inc()
            return {"status": "skipped", "reason": "redis_unavailable"}

        await redis.xadd(stream_key, entry)
        await redis.expire(stream_key, _STREAM_TTL_SECONDS)
        logger.info(
            "record_rag_feedback: %s annotation written to %s",
            body.decision,
            stream_key,
        )
    except Exception as exc:
        logger.warning("record_rag_feedback: stream write failed: %s", exc)
        return {"status": "error", "reason": "stream_write_failed"}

    return {"status": "recorded", "stream_key": stream_key, "decision": body.decision}
