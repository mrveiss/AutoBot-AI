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

Rate Limiting (GH#9117):
    Per-IP rate limiting using the shared RateLimiter with "anonymous" tier
    defaults (20 req/min, 500 req/hour). Requests exceeding the limit receive
    429 with Retry-After header.
"""

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from autobot_shared.logging_manager import get_logger
from autobot_shared.rate_limiter import RateLimiter

logger = get_logger(__name__)

router = APIRouter(tags=["chat", "embed"])

# ---------------------------------------------------------------------------
# Rate limiter (GH#9117)
# ---------------------------------------------------------------------------
_embed_rate_limiter = RateLimiter(
    scope_prefix="embed",
    default_tier="anonymous",  # 20 req/min, 500 req/hour
)

# Trusted proxy IPs for X-Forwarded-For header validation (GH#9117)
# Only honor X-Forwarded-For when the immediate peer is in this allowlist
# to prevent rate-limit bypass via header spoofing.
_TRUSTED_PROXIES_ENV = "AUTOBOT_EMBED_TRUSTED_PROXIES"
_TRUSTED_PROXIES_RAW = os.environ.get(_TRUSTED_PROXIES_ENV, "").strip()
_TRUSTED_PROXIES: frozenset[str] = (
    frozenset(ip.strip() for ip in _TRUSTED_PROXIES_RAW.split(",") if ip.strip())
    if _TRUSTED_PROXIES_RAW
    else frozenset()
)

if _TRUSTED_PROXIES:
    logger.info(
        "Embed trusted proxies: %d configured — X-Forwarded-For honored only from: %s",
        len(_TRUSTED_PROXIES),
        ", ".join(sorted(_TRUSTED_PROXIES)),
    )
else:
    logger.info(
        "Embed trusted proxies: none — rate limiting by direct connection IP only " "(set %s if behind reverse proxy)",
        _TRUSTED_PROXIES_ENV,
    )


def _get_client_ip(request: Request) -> str:
    """Extract client IP for rate limiting, validating X-Forwarded-For against trusted proxies.

    Only trusts X-Forwarded-For when the immediate peer is in AUTOBOT_EMBED_TRUSTED_PROXIES
    to prevent rate-limit bypass via header spoofing (GH#9117).
    """
    peer_ip = request.client.host if request.client else "unknown"

    # Only honor X-Forwarded-For if the immediate connection is from a trusted proxy
    if _TRUSTED_PROXIES and peer_ip in _TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # X-Forwarded-For can be comma-separated; use the first (client) IP
            return forwarded.split(",")[0].strip()

    # Default: use the direct connection IP (untrusted proxies or no XFF)
    return peer_ip


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

    return lazy_init_singleton(request.app.state, "llm_service", LLMService)


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
    and per-IP rate limiting (GH#9117).
    """
    origin = _check_embed_origin(request)
    acao = _acao_header(origin)

    # Rate limit check (GH#9117)
    client_ip = _get_client_ip(request)
    allowed = await _embed_rate_limiter.acquire(client_ip)
    if not allowed:
        retry_after = await _embed_rate_limiter.get_retry_after_seconds(client_ip)
        logger.warning("embed: rate limit exceeded for IP %s (retry after %ds)", client_ip, retry_after)
        return JSONResponse(
            {"detail": "Rate limit exceeded. Please try again later."},
            status_code=429,
            headers={
                "Retry-After": str(retry_after),
                "Access-Control-Allow-Origin": acao,
            },
        )

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
    # Rate limit preflight requests to prevent abuse (GH#9117)
    client_ip = _get_client_ip(request)
    allowed = await _embed_rate_limiter.acquire(client_ip)
    if not allowed:
        retry_after = await _embed_rate_limiter.get_retry_after_seconds(client_ip)
        logger.warning("embed preflight: rate limit exceeded for IP %s", client_ip)
        return JSONResponse(
            {},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )

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
