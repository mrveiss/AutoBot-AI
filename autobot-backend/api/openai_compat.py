# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
OpenAI-compatible API endpoints (#4447).

Exposes:
  POST /v1/chat/completions  — accepts OpenAI-format requests, delegates to
                               ProviderRegistry, returns OpenAI-format responses
  GET  /v1/models            — lists available models from ProviderRegistry

Auth: Bearer token in Authorization header, validated via AutoBot's own JWT
middleware.  Unknown model values fall back to the first available provider's
default.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, AsyncIterator, Dict, List, Tuple
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api.schemas_code import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    OAIChoice,
    OAIChoiceMessage,
    OAIDeltaMessage,
    OAIModelCard,
    OAIModelListResponse,
    OAIStreamChoice,
    OAIUsage,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from llm_shared import get_provider_registry
from llm_shared.model_fallback_coordinator import get_fallback_coordinator
from llm_shared.models import LLMRequest
from llm_shared.tiered_routing.tier_router import get_tiered_router
from services.llm_api_key_service import LLMApiKeyRecord, get_llm_api_key_service
from services.llm_cost_tracker import get_cost_tracker

logger = get_logger(__name__)

router = APIRouter(tags=["openai-compat"])

# ---------------------------------------------------------------------------
# Reserved model names for server-side tiered routing (#6592)
# ---------------------------------------------------------------------------
# Callers may pass these instead of a concrete model name to opt into
# AutoBot's tiered routing.  "auto" uses TieredModelRouter complexity scoring;
# "auto-fast" forces the simple tier; "auto-quality" forces the complex tier.
_AUTO_MODEL_NAMES = frozenset({"auto", "auto-fast", "auto-quality"})

# ---------------------------------------------------------------------------
# Rate limiting — per-IP sliding window via shared IPRateLimiter (#7271)
# ---------------------------------------------------------------------------
#
# #6588 originally hand-rolled the Redis sorted-set + in-process fallback
# directly here. #7271 extracted that into autobot_shared/rate_limit.py so
# it can be reused by /a2a (#7270) and any future per-IP limiter.

from autobot_shared.rate_limit import IPRateLimiter

_oai_limiter = IPRateLimiter(
    key_prefix="ratelimit:oai",
    limit_env="AUTOBOT_OAI_RATE_LIMIT",
    default_limit=60,
    window_seconds=60,
)


def _remote_addr(request: Request) -> str:
    """Extract real client IP (respects X-Forwarded-For from nginx)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------------------
# Auth helper — re-uses AutoBot JWT middleware
# ---------------------------------------------------------------------------


async def _get_user(request: Request) -> Dict[str, Any]:
    """Validate Bearer token and return AutoBot user dict.

    Raises HTTPException 401 if auth fails.
    """
    try:
        return await get_current_user(request)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("OpenAI compat auth error: %s", exc)
        raise HTTPException(status_code=401, detail="Unauthorized")


def _extract_bearer(request: Request) -> str | None:
    """Return the raw Bearer token string, or None if absent/malformed."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


async def _resolve_auth(request: Request) -> Tuple[Dict[str, Any] | None, LLMApiKeyRecord | None]:
    """Dual-auth: accept either a platform JWT or a virtual sk-... API key.

    Returns (user_dict, api_key_record). Exactly one of them will be non-None.
    Raises HTTPException 401 if neither form of auth succeeds.
    """
    bearer = _extract_bearer(request)
    if bearer and bearer.startswith("sk-"):
        svc = get_llm_api_key_service()
        record = await svc.authenticate_key(bearer)
        if record is None:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")
        return None, record
    # Fall back to platform JWT
    user = await _get_user(request)
    return user, None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _resolve_auto_model(model: str, messages: list) -> str:
    """Resolve an auto-* model alias to a concrete model name via TieredModelRouter."""
    router = get_tiered_router()
    if model == "auto-fast":
        return router.get_model_for_tier("simple")
    if model == "auto-quality":
        return router.get_model_for_tier("complex")
    # "auto" — complexity-scored routing
    selected, _ = router.route(messages, requested_model=model)
    return selected


def _build_llm_request(body: ChatCompletionRequest, resolved_model: str | None = None) -> LLMRequest:
    """Convert OpenAI-format request to AutoBot LLMRequest."""
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    effective_model = resolved_model or (body.model if body.model != "autobot-default" else None)
    return LLMRequest(
        messages=messages,
        model_name=effective_model,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        top_p=body.top_p,
        frequency_penalty=body.frequency_penalty,
        presence_penalty=body.presence_penalty,
        stop=body.stop,
        stream=body.stream,
    )


def _make_completion_id() -> str:
    return f"chatcmpl-{uuid4().hex[:24]}"


def _estimate_tokens(text: str) -> int:
    """Approximate token count (OpenAI convention: 1 token ≈ 0.75 words).

    Used for streaming usage when the provider does not return native token
    counts per chunk. Slight overestimate so downstream budgeting is safe.
    """
    if not text:
        return 0
    import math

    return math.ceil(len(text.split()) * 1.3)


async def _stream_generator(
    provider,
    llm_request: LLMRequest,
    completion_id: str,
    model_name: str,
    *,
    include_usage: bool = False,
    prompt_text: str = "",
    api_key_record: LLMApiKeyRecord | None = None,
) -> AsyncIterator[str]:
    """Yield SSE lines for a streaming completion."""
    created = int(time.time())
    completion_text_parts: List[str] = []

    # Opening chunk — role delta
    role_chunk = ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model_name,
        choices=[
            OAIStreamChoice(
                index=0,
                delta=OAIDeltaMessage(role="assistant"),
                finish_reason=None,
            )
        ],
    )
    yield f"data: {role_chunk.model_dump_json()}\n\n"

    async for text_chunk in provider.stream_completion(llm_request):
        if not text_chunk:
            continue
        completion_text_parts.append(text_chunk)
        chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=model_name,
            choices=[
                OAIStreamChoice(
                    index=0,
                    delta=OAIDeltaMessage(content=text_chunk),
                    finish_reason=None,
                )
            ],
        )
        yield f"data: {chunk.model_dump_json()}\n\n"

    # Terminal chunk
    final_chunk = ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model_name,
        choices=[
            OAIStreamChoice(
                index=0,
                delta=OAIDeltaMessage(),
                finish_reason="stop",
            )
        ],
    )
    yield f"data: {final_chunk.model_dump_json()}\n\n"

    prompt_tokens = _estimate_tokens(prompt_text)
    completion_tokens = _estimate_tokens("".join(completion_text_parts))
    tracker = get_cost_tracker()
    cost_usd = tracker.calculate_cost(model_name, prompt_tokens, completion_tokens)

    # Usage chunk (OpenAI spec: emit only when stream_options.include_usage=true)
    # Cost is embedded here when available; a standalone cost chunk is emitted
    # when include_usage is false so clients get cost info in a valid chunk (#7610).
    if include_usage:
        usage_chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=model_name,
            choices=[],
            usage=OAIUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                cost_usd=cost_usd if cost_usd > 0 else None,
            ),
        )
        yield f"data: {usage_chunk.model_dump_json(exclude_none=True)}\n\n"
    elif cost_usd > 0:
        cost_chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=model_name,
            choices=[],
            usage=OAIUsage(cost_usd=cost_usd),
        )
        yield f"data: {cost_chunk.model_dump_json(exclude_none=True)}\n\n"

    yield "data: [DONE]\n\n"

    # Record per-key spend and publish usage event after stream completes (#6590)
    if api_key_record is not None:
        svc = get_llm_api_key_service()
        await svc.record_spend(api_key_record, cost_usd)
        await svc.publish_usage_event(api_key_record, model_name, prompt_tokens, completion_tokens, cost_usd)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/chat/completions", response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="chat_completions",
    error_code_prefix="OPENAI_COMPAT",
)
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
) -> Any:
    """OpenAI-compatible chat completions endpoint (#4447).

    Accepts Bearer token auth (platform JWT or virtual sk-... key), delegates
    to ProviderRegistry, returns OpenAI-format response (streaming or non-streaming).
    Virtual keys enforce per-key monthly budget and model whitelist (#6590).
    """
    _user, api_key_record = await _resolve_auth(request)
    await _oai_limiter.check_or_429(_remote_addr(request))

    # Virtual key enforcement: model whitelist + budget (#6590)
    if api_key_record is not None:
        from services.llm_api_key_service import LLMApiKeyService

        if body.model not in _AUTO_MODEL_NAMES and body.model != "autobot-default":
            if not LLMApiKeyService.model_allowed(api_key_record, body.model):
                raise HTTPException(
                    status_code=403,
                    detail="Model not permitted for this API key",
                    headers={"x-llm-key-allowed-models": ",".join(api_key_record.allowed_models)},
                )
        allowed, remaining = await get_llm_api_key_service().check_budget(api_key_record)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Monthly budget exhausted",
                headers={"x-llm-budget-remaining": "0"},
            )

    # Resolve auto-* model aliases to concrete model names via tiered routing (#6592)
    if body.model in _AUTO_MODEL_NAMES:
        messages_raw = [{"role": m.role, "content": m.content} for m in body.messages]
        resolved_model = await _resolve_auto_model(body.model, messages_raw)
    elif body.model == "autobot-default":
        resolved_model = None  # will be set from provider name below
    else:
        resolved_model = body.model

    registry = get_provider_registry()
    llm_request = _build_llm_request(body, resolved_model=resolved_model)

    provider = await registry.get_provider_for_request(request=llm_request)
    if provider is None:
        raise HTTPException(status_code=503, detail="No LLM providers available")

    # Fix 3: validate stream_completion is an async generator function (#5132)
    if not inspect.isasyncgenfunction(provider.stream_completion):
        raise ValueError(f"Provider {provider.provider_name!r} stream_completion must be an async generator function")

    completion_id = _make_completion_id()
    # Echo the concrete model name; fall back to provider name for autobot-default
    if resolved_model is None:
        resolved_model = provider.provider_name

    if body.stream:
        include_usage = bool(body.stream_options and body.stream_options.include_usage)
        prompt_text = "\n".join(m.content for m in body.messages)
        # For streaming, cost cannot be determined accurately until stream completes
        # (token counts are not known upfront). Per acceptance criteria, header is
        # absent when cost cannot be determined. Non-streaming path includes the header.
        stream_headers: Dict[str, str] = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        if body.model in _AUTO_MODEL_NAMES:
            stream_headers["x-llm-routed-from"] = body.model
        return StreamingResponse(
            _stream_generator(
                provider,
                llm_request,
                completion_id,
                resolved_model,
                include_usage=include_usage,
                prompt_text=prompt_text,
                api_key_record=api_key_record,
            ),
            media_type="text/event-stream",
            headers=stream_headers,
        )

    # Non-streaming path — use fallback coordinator for quota-triggered model switch
    llm_response = await get_fallback_coordinator().execute_with_fallback(llm_request, registry)
    if llm_response.error:
        raise HTTPException(status_code=502, detail=llm_response.error)

    tokens = llm_response.usage or {}
    usage = OAIUsage(
        prompt_tokens=tokens.get("prompt_tokens", 0),
        completion_tokens=tokens.get("completion_tokens", 0),
        total_tokens=tokens.get("total_tokens", llm_response.tokens_used or 0),
    )

    # Calculate cost and store in response hidden params
    tracker = get_cost_tracker()
    cost_usd = tracker.calculate_cost(
        resolved_model,
        usage.prompt_tokens,
        usage.completion_tokens,
    )
    llm_response.hidden_params["response_cost"] = cost_usd

    response = ChatCompletionResponse(
        id=completion_id,
        created=int(time.time()),
        model=resolved_model,
        choices=[
            OAIChoice(
                index=0,
                message=OAIChoiceMessage(
                    role="assistant",
                    content=llm_response.content,
                ),
                finish_reason=llm_response.finish_reason or "stop",
            )
        ],
        usage=usage,
    )

    # Extract cost from hidden params and add as header
    response_cost = llm_response.hidden_params.get("response_cost", 0)
    headers: Dict[str, str] = {}
    if response_cost > 0:
        headers["x-llm-cost"] = str(response_cost)
    if body.model in _AUTO_MODEL_NAMES:
        headers["x-llm-routed-from"] = body.model

    # Record per-key spend and publish usage event (#6590)
    if api_key_record is not None:
        svc = get_llm_api_key_service()
        await svc.record_spend(api_key_record, cost_usd)
        await svc.publish_usage_event(
            api_key_record,
            resolved_model,
            usage.prompt_tokens,
            usage.completion_tokens,
            cost_usd,
        )

    return JSONResponse(
        content=response.model_dump(exclude_none=True),
        headers=headers,
    )


@router.get("/models", response_model=OAIModelListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_models",
    error_code_prefix="OPENAI_COMPAT",
)
async def list_models(request: Request) -> OAIModelListResponse:
    """OpenAI-compatible models list endpoint (#4447).

    Returns all models available across registered providers.
    """
    await _resolve_auth(request)

    registry = get_provider_registry()
    created = int(time.time())
    model_cards: List[OAIModelCard] = []
    seen: set = set()

    for provider_info in registry.list_providers():
        provider_name = provider_info["name"]
        provider = registry.get_provider_by_name(str(provider_name))
        if provider is None:
            continue
        try:
            models = await asyncio.wait_for(provider.list_models(), timeout=5.0)
            for m in models:
                if m not in seen:
                    seen.add(m)
                    model_cards.append(OAIModelCard(id=m, created=created, owned_by=str(provider_name)))
        except Exception as exc:
            logger.debug("list_models failed for %s: %s", provider_name, exc)

    # Always include a sentinel entry so the list is non-empty
    if not model_cards:
        model_cards.append(OAIModelCard(id="autobot-default", created=created))

    # Prepend reserved auto-routing aliases (#6592)
    auto_cards = [
        OAIModelCard(id="auto", created=created, owned_by="autobot"),
        OAIModelCard(id="auto-fast", created=created, owned_by="autobot"),
        OAIModelCard(id="auto-quality", created=created, owned_by="autobot"),
    ]
    model_cards = auto_cards + [c for c in model_cards if c.id not in _AUTO_MODEL_NAMES]

    return OAIModelListResponse(data=model_cards)
