# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Multi-model comparison API endpoint (Issue #4414).

POST /api/chat/compare
  - Accepts {prompt, models, context?}
  - Fans out to N providers concurrently via asyncio.gather(return_exceptions=True)
  - Streams SSE — one stream per model interleaved on the same connection
  - One model erroring does NOT cancel others

SSE event shapes:
  {"model": "<provider>/<model>", "delta": "...", "done": false}
  {"model": "<provider>/<model>", "done": true}
  {"model": "<provider>/<model>", "error": "...", "done": true}
"""

import asyncio
import json
from typing import AsyncIterator, Dict, List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from api.schemas_chat import CompareRequest
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["chat"])

# ---------------------------------------------------------------------------
# Module-level singleton — initialized once, no lazy-init race (#5023)
# ---------------------------------------------------------------------------

_init_lock: asyncio.Lock = asyncio.Lock()
_compare_interface: object | None = None


async def _get_compare_interface() -> object:
    """Return the process-level LLMService singleton, initializing it once (#5023)."""
    global _compare_interface
    if _compare_interface is not None:
        return _compare_interface
    async with _init_lock:
        if _compare_interface is None:
            from services.llm_service import get_llm_service

            _compare_interface = get_llm_service()
    return _compare_interface


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_provider_model(spec: str) -> tuple[str, str]:
    """Split 'provider/model' → (provider, model).  Plain strings become (spec, '')."""
    if "/" in spec:
        provider, _, model = spec.partition("/")
        return provider.strip(), model.strip()
    return spec.strip(), ""


async def _stream_single_model(
    model_spec: str,
    messages: List[Dict],
) -> AsyncIterator[str]:
    """
    Yield SSE data lines for a single model using real provider streaming (#5013).

    Resolves the provider via ProviderRegistry and calls stream_completion() so
    chunks arrive from the LLM as they are generated, not as a post-hoc slice.
    """
    from llm_shared import get_provider_registry
    from llm_shared.models import LLMRequest

    provider_name, model_name = _parse_provider_model(model_spec)
    try:
        registry = get_provider_registry()
        llm_request = LLMRequest(
            messages=messages,
            llm_type="chat",
            provider=provider_name or None,
            model_name=model_name or None,
            stream=True,
        )
        provider = await registry.get_provider_for_request(
            provider_name=provider_name or None,
            request=llm_request,
        )
        if provider is None:
            yield _sse(
                {
                    "model": model_spec,
                    "error": f"No provider available for {model_spec!r}",
                    "done": True,
                }
            )
            return

        async for chunk in provider.stream_completion(llm_request):
            if chunk:
                yield _sse({"model": model_spec, "delta": chunk, "done": False})

        yield _sse({"model": model_spec, "done": True})

    except Exception as exc:
        logger.warning("compare stream error for %s: %s", model_spec, exc)
        # Issue #9410: Never leak exception details in SSE streams
        yield _sse({"model": model_spec, "error": "Model comparison failed", "done": True})


def _sse(payload: Dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _fan_out_stream(
    model_specs: List[str],
    messages: List[Dict],
) -> AsyncIterator[str]:
    """
    Interleave SSE events from all models concurrently using asyncio queues.

    Each model gets its own async generator.  A coordinator task drains all
    generators round-robin via a shared asyncio.Queue so results are
    interleaved as they arrive rather than sequentially.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    n_models = len(model_specs)
    sentinel_count = 0

    async def _drain(gen: AsyncIterator[str]) -> None:
        async for item in gen:
            await queue.put(item)
        await queue.put(None)  # signal this model is done

    # Launch all model streams concurrently
    tasks = [asyncio.create_task(_drain(_stream_single_model(spec, messages))) for spec in model_specs]

    try:
        while sentinel_count < n_models:
            item = await queue.get()
            if item is None:
                sentinel_count += 1
            else:
                yield item
    finally:
        for t in tasks:
            t.cancel()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/chat/compare", response_model=None)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="compare_models",
    error_code_prefix="CHAT_COMPARE",
)
async def compare_models(
    body: CompareRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """
    Fan out a prompt to multiple LLM providers/models and stream all responses
    concurrently as SSE (Issue #4414).

    Each SSE event is a JSON object:
      {"model": "provider/model", "delta": "text", "done": false}
      {"model": "provider/model", "done": true}
      {"model": "provider/model", "error": "message", "done": true}
    """
    # Ensure LLMInterface singleton is initialized (used for future non-registry paths).
    await _get_compare_interface()

    user_content = body.prompt
    if body.context:
        user_content = f"{body.context}\n\n{user_content}"

    messages = [{"role": "user", "content": user_content}]

    return StreamingResponse(
        _fan_out_stream(body.models, messages),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
