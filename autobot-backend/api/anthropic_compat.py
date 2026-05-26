# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anthropic-compatible API endpoint (#6591).

Exposes:
  POST /v1/messages  — accepts Anthropic Messages-format requests, delegates to
                       ProviderRegistry, returns Anthropic-format responses

Auth: Bearer token in Authorization header, validated via AutoBot's own JWT
middleware or virtual sk-... API keys.  Same auth + rate limit middleware as
openai_compat.py.
"""

from __future__ import annotations

import inspect
import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.openai_compat import (
    _AUTO_MODEL_NAMES,
    _estimate_tokens,
    _oai_limiter,
    _remote_addr,
    _resolve_auth,
    _resolve_auto_model,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from llm_shared import get_provider_registry
from llm_shared.models import LLMRequest
from services.llm_api_key_service import LLMApiKeyRecord, get_llm_api_key_service
from services.llm_cost_tracker import get_cost_tracker

logger = get_logger(__name__)

router = APIRouter(tags=["anthropic-compat"])

# ---------------------------------------------------------------------------
# Anthropic Messages API request/response schemas
# ---------------------------------------------------------------------------


class AnthropicContentBlock(BaseModel):
    type: str = "text"
    text: str = ""


class AnthropicMessage(BaseModel):
    role: str
    # Anthropic supports both plain string and list-of-blocks for content
    content: str | List[AnthropicContentBlock]


class AnthropicRequest(BaseModel):
    model: str = "autobot-default"
    messages: List[AnthropicMessage]
    system: Optional[str] = None
    max_tokens: int = 1024
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    stop_sequences: Optional[List[str]] = None
    stream: bool = False
    metadata: Optional[Dict[str, Any]] = None


class AnthropicUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class AnthropicTextBlock(BaseModel):
    type: str = "text"
    text: str


class AnthropicResponse(BaseModel):
    id: str
    type: str = "message"
    role: str = "assistant"
    content: List[AnthropicTextBlock]
    model: str
    stop_reason: str = "end_turn"
    stop_sequence: Optional[str] = None
    usage: AnthropicUsage


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_message_id() -> str:
    return f"msg_{uuid4().hex[:24]}"


def _extract_content_text(content: str | List[AnthropicContentBlock]) -> str:
    """Flatten Anthropic content to plain text."""
    if isinstance(content, str):
        return content
    return "".join(block.text for block in content if block.type == "text")


def _map_finish_reason(finish_reason: str | None) -> str:
    """Map provider finish_reason to Anthropic stop_reason vocabulary."""
    if finish_reason in ("length", "max_tokens"):
        return "max_tokens"
    if finish_reason in ("tool_calls", "tool_use"):
        return "tool_use"
    return "end_turn"


def _build_llm_request(body: AnthropicRequest, resolved_model: str | None = None) -> LLMRequest:
    """Convert Anthropic Messages-format request to AutoBot LLMRequest."""
    messages: List[Dict[str, str]] = []
    if body.system:
        messages.append({"role": "system", "content": body.system})
    for m in body.messages:
        messages.append({"role": m.role, "content": _extract_content_text(m.content)})
    effective_model = resolved_model or (body.model if body.model != "autobot-default" else None)
    return LLMRequest(
        messages=messages,
        model_name=effective_model,
        temperature=body.temperature if body.temperature is not None else 0.7,
        max_tokens=body.max_tokens,
        top_p=body.top_p if body.top_p is not None else 1.0,
        stop=body.stop_sequences,
        stream=body.stream,
    )


async def _stream_generator_anthropic(
    provider,
    llm_request: LLMRequest,
    message_id: str,
    model_name: str,
    *,
    prompt_text: str = "",
    api_key_record: LLMApiKeyRecord | None = None,
) -> AsyncIterator[str]:
    """Yield Anthropic SSE events for a streaming completion."""
    completion_text_parts: List[str] = []
    content_index = 0

    def _sse(event_type: str, data: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    prompt_tokens = _estimate_tokens(prompt_text)

    # message_start
    yield _sse(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": message_id,
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model_name,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": prompt_tokens, "output_tokens": 0},
            },
        },
    )

    # content_block_start
    yield _sse(
        "content_block_start",
        {
            "type": "content_block_start",
            "index": content_index,
            "content_block": {"type": "text", "text": ""},
        },
    )

    # ping — Anthropic sends these periodically; one is enough for clients
    yield _sse("ping", {"type": "ping"})

    async for text_chunk in provider.stream_completion(llm_request):
        if not text_chunk:
            continue
        completion_text_parts.append(text_chunk)
        yield _sse(
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": content_index,
                "delta": {"type": "text_delta", "text": text_chunk},
            },
        )

    # content_block_stop
    yield _sse("content_block_stop", {"type": "content_block_stop", "index": content_index})

    completion_text = "".join(completion_text_parts)
    completion_tokens = _estimate_tokens(completion_text)
    tracker = get_cost_tracker()
    cost_usd = tracker.calculate_cost(model_name, prompt_tokens, completion_tokens)

    # message_delta — carries final stop_reason + output token count
    yield _sse(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": completion_tokens},
        },
    )

    # message_stop
    yield _sse("message_stop", {"type": "message_stop"})

    # Record per-key spend and publish usage event after stream completes
    if api_key_record is not None:
        svc = get_llm_api_key_service()
        await svc.record_spend(api_key_record, cost_usd)
        await svc.publish_usage_event(api_key_record, model_name, prompt_tokens, completion_tokens, cost_usd)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/messages", response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="messages",
    error_code_prefix="ANTHROPIC_COMPAT",
)
async def messages(
    body: AnthropicRequest,
    request: Request,
) -> Any:
    """Anthropic-compatible messages endpoint (#6591).

    Accepts Bearer token auth (platform JWT or virtual sk-... key), delegates
    to ProviderRegistry, returns Anthropic Messages-format response.
    Virtual keys enforce per-key monthly budget and model whitelist.
    """
    _user, api_key_record = await _resolve_auth(request)
    await _oai_limiter.check_or_429(_remote_addr(request))

    # Virtual key enforcement: model whitelist + budget
    if api_key_record is not None:
        from services.llm_api_key_service import LLMApiKeyService

        if body.model not in _AUTO_MODEL_NAMES and body.model != "autobot-default":
            if not LLMApiKeyService.model_allowed(api_key_record, body.model):
                raise HTTPException(
                    status_code=403,
                    detail="Model not permitted for this API key",
                    headers={"x-llm-key-allowed-models": ",".join(api_key_record.allowed_models)},
                )
        allowed, _remaining = await get_llm_api_key_service().check_budget(api_key_record)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Monthly budget exhausted",
                headers={"x-llm-budget-remaining": "0"},
            )

    # Resolve auto-* model aliases via tiered routing
    if body.model in _AUTO_MODEL_NAMES:
        messages_raw: List[Dict[str, str]] = []
        if body.system:
            messages_raw.append({"role": "system", "content": body.system})
        messages_raw += [{"role": m.role, "content": _extract_content_text(m.content)} for m in body.messages]
        resolved_model = await _resolve_auto_model(body.model, messages_raw)
    elif body.model == "autobot-default":
        resolved_model = None
    else:
        resolved_model = body.model

    registry = get_provider_registry()
    llm_request = _build_llm_request(body, resolved_model=resolved_model)

    provider = await registry.get_provider_for_request(request=llm_request)
    if provider is None:
        raise HTTPException(status_code=503, detail="No LLM providers available")

    if not inspect.isasyncgenfunction(provider.stream_completion):
        raise ValueError(f"Provider {provider.provider_name!r} stream_completion must be an async generator function")

    message_id = _make_message_id()
    if resolved_model is None:
        resolved_model = provider.provider_name

    if body.stream:
        prompt_text = (body.system or "") + "\n" + "\n".join(_extract_content_text(m.content) for m in body.messages)
        stream_headers: Dict[str, str] = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        if body.model in _AUTO_MODEL_NAMES:
            stream_headers["x-llm-routed-from"] = body.model
        return StreamingResponse(
            _stream_generator_anthropic(
                provider,
                llm_request,
                message_id,
                resolved_model,
                prompt_text=prompt_text,
                api_key_record=api_key_record,
            ),
            media_type="text/event-stream",
            headers=stream_headers,
        )

    # Non-streaming path
    llm_response = await provider.chat_completion(llm_request)
    if llm_response.error:
        raise HTTPException(status_code=502, detail=llm_response.error)

    tokens = llm_response.usage or {}
    prompt_tokens = tokens.get("prompt_tokens", 0)
    completion_tokens = tokens.get("completion_tokens", 0)

    tracker = get_cost_tracker()
    cost_usd = tracker.calculate_cost(resolved_model, prompt_tokens, completion_tokens)

    response = AnthropicResponse(
        id=message_id,
        content=[AnthropicTextBlock(text=llm_response.content or "")],
        model=resolved_model,
        stop_reason=_map_finish_reason(llm_response.finish_reason),
        usage=AnthropicUsage(input_tokens=prompt_tokens, output_tokens=completion_tokens),
    )

    headers: Dict[str, str] = {}
    if cost_usd > 0:
        headers["x-llm-cost"] = str(cost_usd)
    if body.model in _AUTO_MODEL_NAMES:
        headers["x-llm-routed-from"] = body.model

    if api_key_record is not None:
        svc = get_llm_api_key_service()
        await svc.record_spend(api_key_record, cost_usd)
        await svc.publish_usage_event(api_key_record, resolved_model, prompt_tokens, completion_tokens, cost_usd)

    return JSONResponse(content=response.model_dump(exclude_none=True), headers=headers)
