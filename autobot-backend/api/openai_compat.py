# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth_middleware import get_current_user
from llm_interface_pkg.models import LLMRequest
from llm_providers.provider_registry import get_provider_registry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["openai-compat"])


# ---------------------------------------------------------------------------
# Request / response models (OpenAI wire format)
# ---------------------------------------------------------------------------


class OAIMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None


class OAIStreamOptions(BaseModel):
    include_usage: bool = False


class ChatCompletionRequest(BaseModel):
    model: str = "autobot-default"
    messages: List[OAIMessage]
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[List[str]] = None
    stream: bool = False
    stream_options: Optional[OAIStreamOptions] = None
    n: int = Field(default=1, ge=1)
    user: Optional[str] = None


class OAIChoiceMessage(BaseModel):
    role: str
    content: str


class OAIChoice(BaseModel):
    index: int
    message: OAIChoiceMessage
    finish_reason: str = "stop"


class OAIUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OAIChoice]
    usage: OAIUsage


class OAIDeltaMessage(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None


class OAIStreamChoice(BaseModel):
    index: int
    delta: OAIDeltaMessage
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[OAIStreamChoice]
    usage: Optional[OAIUsage] = None


class OAIModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "autobot"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: List[OAIModelCard]


# ---------------------------------------------------------------------------
# Auth helper — re-uses AutoBot JWT middleware
# ---------------------------------------------------------------------------


def _get_user(request: Request) -> Dict[str, Any]:
    """Validate Bearer token and return AutoBot user dict.

    Raises HTTPException 401 if auth fails.
    """
    try:
        return get_current_user(request)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("OpenAI compat auth error: %s", exc)
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_llm_request(body: ChatCompletionRequest) -> LLMRequest:
    """Convert OpenAI-format request to AutoBot LLMRequest."""
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    return LLMRequest(
        messages=messages,
        model_name=body.model if body.model != "autobot-default" else None,
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

    # Usage chunk (OpenAI spec: emit only when stream_options.include_usage=true)
    if include_usage:
        prompt_tokens = _estimate_tokens(prompt_text)
        completion_tokens = _estimate_tokens("".join(completion_text_parts))
        usage_chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=model_name,
            choices=[],
            usage=OAIUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )
        yield f"data: {usage_chunk.model_dump_json()}\n\n"

    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/chat/completions", response_model=None)
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
) -> Any:
    """OpenAI-compatible chat completions endpoint (#4447).

    Accepts Bearer token auth, delegates to ProviderRegistry, returns
    OpenAI-format response (streaming or non-streaming).
    """
    _get_user(request)

    registry = get_provider_registry()
    llm_request = _build_llm_request(body)

    provider = await registry.get_provider_for_request(request=llm_request)
    if provider is None:
        raise HTTPException(status_code=503, detail="No LLM providers available")

    completion_id = _make_completion_id()
    # Use resolved provider name as model echo when caller sent "autobot-default"
    resolved_model = body.model if body.model != "autobot-default" else provider.provider_name

    if body.stream:
        include_usage = bool(body.stream_options and body.stream_options.include_usage)
        prompt_text = "\n".join(m.content for m in body.messages)
        return StreamingResponse(
            _stream_generator(
                provider,
                llm_request,
                completion_id,
                resolved_model,
                include_usage=include_usage,
                prompt_text=prompt_text,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming path
    llm_response = await provider.chat_completion(llm_request)
    if llm_response.error:
        raise HTTPException(status_code=502, detail=llm_response.error)

    tokens = llm_response.usage or {}
    usage = OAIUsage(
        prompt_tokens=tokens.get("prompt_tokens", 0),
        completion_tokens=tokens.get("completion_tokens", 0),
        total_tokens=tokens.get("total_tokens", llm_response.tokens_used or 0),
    )

    return ChatCompletionResponse(
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


@router.get("/models", response_model=ModelListResponse)
async def list_models(request: Request) -> ModelListResponse:
    """OpenAI-compatible models list endpoint (#4447).

    Returns all models available across registered providers.
    """
    _get_user(request)

    registry = get_provider_registry()
    created = int(time.time())
    model_cards: List[OAIModelCard] = []
    seen: set = set()

    for provider_info in registry.list_providers():
        provider_name = provider_info["name"]
        provider = registry._providers.get(str(provider_name))
        if provider is None:
            continue
        try:
            models = await asyncio.wait_for(provider.list_models(), timeout=5.0)
            for m in models:
                if m not in seen:
                    seen.add(m)
                    model_cards.append(
                        OAIModelCard(id=m, created=created, owned_by=str(provider_name))
                    )
        except Exception as exc:
            logger.debug("list_models failed for %s: %s", provider_name, exc)

    # Always include a sentinel entry so the list is non-empty
    if not model_cards:
        model_cards.append(OAIModelCard(id="autobot-default", created=created))

    return ModelListResponse(data=model_cards)
