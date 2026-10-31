# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/routes/ai.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Streaming AI analysis route.

Streams through ``LLMService.stream()``, which resolves the provider, falls back
on a rate limit, and records the spend against the caller and the recording
(#16924).
"""

import json
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import CategoryDefaults
from services.llm_service import get_llm_service
from services.llm_usage_recording import spend_attribution
from transcriber.ai.context import build_context
from transcriber.ai.prompts import ANALYSIS_MAX_TOKENS, get_system_prompt
from transcriber.database import Database
from transcriber.deps import authenticate, caller_can_access, caller_id_of, get_transcriber_db_from_request
from transcriber.export.segments import build_segment_list
from transcriber.models import AiAskRequest

logger = get_logger(__name__)
router = APIRouter(tags=["transcriber-ai"], dependencies=[Depends(authenticate)])

# The usage record's endpoint label: the full mounted route TEMPLATE (api.transcriber
# mounts this router under /transcriber, and the app prefixes /api), braces included on
# purpose, so spend groups by route; the recording id rides in the record's metadata.
_ASK_ENDPOINT = "/api/transcriber/recordings/{recording_id}/ai/ask"


def _ask_messages(system_prompt: str, context: str) -> List[Dict[str, str]]:
    """The chat messages for one ask: the action's system prompt, then the transcript."""
    return [
        {"role": CategoryDefaults.ROLE_SYSTEM, "content": system_prompt},
        {"role": CategoryDefaults.ROLE_USER, "content": f"Transcript:\n\n{context}"},
    ]


@router.post("/recordings/{recording_id}/ai/ask")
async def ai_ask(
    recording_id: int,
    body: AiAskRequest,
    request: Request,
    db: Database = Depends(get_transcriber_db_from_request),
):
    rec = await db.get_recording(recording_id)
    if not rec or not caller_can_access(rec, request):
        raise HTTPException(404, "Recording not found")
    segments = await build_segment_list(recording_id, db)
    context = build_context(segments)
    system_prompt = get_system_prompt(body.action, custom_question=body.custom_question)

    messages = _ask_messages(system_prompt, context)
    attribution = spend_attribution(user_id=caller_id_of(request), endpoint=_ASK_ENDPOINT, recording_id=recording_id)

    async def stream():
        try:
            async for chunk in get_llm_service().stream(messages, max_tokens=ANALYSIS_MAX_TOKENS, metadata=attribution):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        except Exception:
            logger.exception("AI analysis failed for recording=%s", recording_id)
            yield f"data: {json.dumps({'error': 'AI analysis failed'})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
