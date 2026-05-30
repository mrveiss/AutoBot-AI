# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Embed widget chat endpoint (GH#9047).

Provides an unauthenticated POST endpoint consumed by the AutobotWidget
custom element.  The embed widget runs on third-party pages and cannot
hold session cookies or Bearer tokens, so this endpoint accepts an
optional X-Org-Id header for future multi-tenant scoping but requires
no auth.

Endpoints:
    POST /api/chats/embed/message  — send a message, receive JSON reply
"""

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["chat", "embed"])


class EmbedMessageRequest(BaseModel):
    message: str


async def _get_llm_service(request: Request) -> Any:
    from services.llm_service import LLMService
    from utils.lazy_singleton import lazy_init_singleton

    return lazy_init_singleton(request.app.state, "llm_service", LLMService)


async def _stream_embed(llm_service: Any, message: str):
    """Yield SSE chunks compatible with the AutobotWidget SSE reader."""
    try:
        if hasattr(llm_service, "stream_response"):
            async for chunk in llm_service.stream_response(message, session_id=None):
                data = json.dumps({"content": chunk.get("content", "")})
                yield f"data: {data}\n\n"
        else:
            response = await llm_service.chat(
                messages=[{"role": "user", "content": message}]
            )
            content = response.content if not response.error else "Sorry, something went wrong."
            data = json.dumps({"content": content})
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        logger.error("embed stream error: %s", exc)
        yield f"data: {json.dumps({'content': 'Sorry, something went wrong.'})}\n\n"
        yield "data: [DONE]\n\n"


@router.post("/chats/embed/message")
async def embed_message(
    body: EmbedMessageRequest,
    request: Request,
) -> JSONResponse:
    """Accept a chat message from the embed widget and return an AI reply.

    Supports both plain JSON and SSE streaming.  The response format is
    selected by the ``Accept`` header:
    - ``text/event-stream`` → SSE stream
    - anything else (default) → JSON ``{"content": "..."}``

    No authentication required — the endpoint is designed for unauthenticated
    embed contexts.  Rate-limiting is delegated to the upstream reverse proxy.
    """
    accept = request.headers.get("accept", "")
    message = body.message.strip()
    if not message:
        return JSONResponse({"content": ""}, status_code=200)

    llm_service = await _get_llm_service(request)

    if "text/event-stream" in accept:
        return StreamingResponse(
            _stream_embed(llm_service, message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type, X-Org-Id",
            },
        )

    try:
        response = await llm_service.chat(
            messages=[{"role": "user", "content": message}]
        )
        content = response.content if not response.error else "Sorry, something went wrong. Please try again."
    except Exception as exc:
        logger.error("embed message error: %s", exc)
        content = "Sorry, something went wrong. Please try again."

    return JSONResponse(
        {"content": content},
        headers={"Access-Control-Allow-Origin": "*"},
    )


@router.options("/chats/embed/message")
async def embed_message_preflight() -> JSONResponse:
    """CORS preflight for embed widget cross-origin requests."""
    return JSONResponse(
        {},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-Org-Id",
        },
    )
