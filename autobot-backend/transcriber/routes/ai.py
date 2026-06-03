# autobot-backend/transcriber/routes/ai.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Streaming AI analysis route — delegates to AutoBot llm_shared."""
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.models import AiAskRequest
from transcriber.ai.prompts import get_system_prompt
from transcriber.ai.context import build_context
from transcriber.routes.export import _build_segment_list
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["transcriber-ai"])

# Development fallback — auth middleware populates request.state.user in production
def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.id if user else "default"


@router.post("/recordings/{recording_id}/ai/ask")
async def ai_ask(
    recording_id: int,
    body: AiAskRequest,
    request: Request,
    db: Database = Depends(get_db),
):
    rec = await db.get_recording(recording_id)
    if not rec or rec["user_id"] != _user_id(request):
        raise HTTPException(404, "Recording not found")
    segments = await _build_segment_list(recording_id, db)
    context = build_context(segments)
    system_prompt = get_system_prompt(body.action, custom_question=body.custom_question)

    async def stream():
        try:
            from llm_shared.providers import get_default_provider
            provider = get_default_provider()
            async for chunk in provider.stream_chat(
                system=system_prompt,
                user=f"Transcript:\n\n{context}",
            ):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        except Exception as exc:
            logger.exception("AI analysis failed for recording=%s", recording_id)
            yield f"data: {json.dumps({'error': 'AI analysis failed'})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
