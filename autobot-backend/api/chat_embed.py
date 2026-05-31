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

Config:
    AUTOBOT_EMBED_ALLOWED_ORIGINS — comma-separated list of allowed request
        origins, e.g. "https://example.com,https://app.acme.io".
        When set to "*" (the default) all origins are permitted (backward
        compatible open mode).  When any specific origins are listed only
        those origins may call the embed endpoint; requests from other
        origins receive 403 (GH#9117).
"""

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["chat", "embed"])

# ---------------------------------------------------------------------------
# Origin allowlist (GH#9117)
# ---------------------------------------------------------------------------
_EMBED_ALLOWED_ORIGINS_ENV = "AUTOBOT_EMBED_ALLOWED_ORIGINS"
_EMBED_ALLOWED_ORIGINS_RAW: str = os.environ.get(_EMBED_ALLOWED_ORIGINS_ENV, "*").strip()

# When the env var is "*" (default) enforcement is disabled for backward compat.
_EMBED_ORIGIN_ENFORCEMENT_ENABLED: bool = _EMBED_ALLOWED_ORIGINS_RAW != "*"
_EMBED_ALLOWED_ORIGINS: frozenset[str] = (
    frozenset(o.strip() for o in _EMBED_ALLOWED_ORIGINS_RAW.split(",") if o.strip())
    if _EMBED_ORIGIN_ENFORCEMENT_ENABLED
    else frozenset()
)

if _EMBED_ORIGIN_ENFORCEMENT_ENABLED:
    logger.info(
        "Embed origin allowlist active (%d entries): %s",
        len(_EMBED_ALLOWED_ORIGINS),
        ", ".join(sorted(_EMBED_ALLOWED_ORIGINS)),
    )
else:
    logger.info("Embed origin allowlist: open (*) — set %s to restrict", _EMBED_ALLOWED_ORIGINS_ENV)


def _check_embed_origin(request: Request) -> str | None:
    """Return the validated origin string, or None when enforcement is off.

    Raises JSONResponse (403) when enforcement is active and the request
    origin is not in the allowlist.
    """
    if not _EMBED_ORIGIN_ENFORCEMENT_ENABLED:
        return None
    origin = request.headers.get("origin", "")
    if not origin or origin not in _EMBED_ALLOWED_ORIGINS:
        logger.warning("embed: blocked request from disallowed origin %r", origin or "(none)")
        raise HTTPException(status_code=403, detail="Origin not allowed")
    return origin


def _origin_forbidden() -> JSONResponse:
    return JSONResponse({"detail": "Origin not allowed"}, status_code=403)


def _acao_header(origin: str | None) -> str:
    """Return the Access-Control-Allow-Origin header value for a response."""
    return origin if origin else "*"


class EmbedMessageRequest(BaseModel):
    message: str


async def _get_llm_service(request: Request) -> Any:
    from services.llm_service import LLMService
    from utils.lazy_singleton import lazy_init_singleton

    llm_service = lazy_init_singleton(request.app.state, "llm_service", LLMService)
    if llm_service is None:
        logger.error("LLMService initialization failed for embed endpoint")
        raise HTTPException(status_code=503, detail="LLM service unavailable")
    return llm_service


async def _stream_embed(llm_service: Any, message: str):
    """Yield SSE chunks compatible with the AutobotWidget SSE reader."""
    try:
        if hasattr(llm_service, "stream_response"):
            async for chunk in llm_service.stream_response(message, session_id=None):
                data = json.dumps({"content": chunk.get("content", "")})
                yield f"data: {data}\n\n"
        else:
            response = await llm_service.chat(messages=[{"role": "user", "content": message}])
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
    embed contexts.  Origin enforcement via AUTOBOT_EMBED_ALLOWED_ORIGINS
    (GH#9117).
    """
    origin = _check_embed_origin(request)
    acao = _acao_header(origin)

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
                "Access-Control-Allow-Origin": acao,
                "Access-Control-Allow-Headers": "Content-Type, X-Org-Id",
            },
        )

    try:
        response = await llm_service.chat(messages=[{"role": "user", "content": message}])
        content = response.content if not response.error else "Sorry, something went wrong. Please try again."
    except Exception as exc:
        logger.error("embed message error: %s", exc)
        content = "Sorry, something went wrong. Please try again."

    return JSONResponse(
        {"content": content},
        headers={"Access-Control-Allow-Origin": acao},
    )


@router.options("/chats/embed/message")
async def embed_message_preflight(request: Request) -> JSONResponse:
    """CORS preflight for embed widget cross-origin requests (GH#9117)."""
    if _EMBED_ORIGIN_ENFORCEMENT_ENABLED:
        origin = request.headers.get("origin", "")
        if not origin or origin not in _EMBED_ALLOWED_ORIGINS:
            return _origin_forbidden()
        acao = origin
    else:
        acao = "*"

    return JSONResponse(
        {},
        headers={
            "Access-Control-Allow-Origin": acao,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-Org-Id",
        },
    )
