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
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth_middleware import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class CompareRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=50000)
    models: List[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of 'provider/model' strings, e.g. ['ollama/llama3', 'openai/gpt-4o']",
    )
    context: Optional[str] = Field(None, max_length=50000)


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
    llm_interface: Any,
    model_spec: str,
    messages: List[Dict],
) -> AsyncIterator[str]:
    """
    Yield SSE data lines for a single model.

    Uses chat_completion (non-streaming) and emits the content in one delta
    plus a done event.  This avoids the complexity of per-provider streaming
    while keeping the SSE protocol consistent for the frontend.
    """
    provider, model_name = _parse_provider_model(model_spec)
    try:
        kwargs: Dict[str, Any] = {"provider": provider}
        if model_name:
            kwargs["model_name"] = model_name

        response = await llm_interface.chat_completion(
            messages=messages,
            llm_type="chat",
            **kwargs,
        )

        if response.error:
            yield _sse({"model": model_spec, "error": response.error, "done": True})
            return

        content: str = response.content or ""
        # Stream in reasonably-sized chunks so the UI can start rendering early
        chunk_size = 64
        for i in range(0, max(1, len(content)), chunk_size):
            yield _sse({"model": model_spec, "delta": content[i : i + chunk_size], "done": False})
            await asyncio.sleep(0)  # yield event-loop slot

        yield _sse({"model": model_spec, "done": True})

    except Exception as exc:
        logger.warning("compare stream error for %s: %s", model_spec, exc)
        yield _sse({"model": model_spec, "error": str(exc), "done": True})


def _sse(payload: Dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _fan_out_stream(
    llm_interface: Any,
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
    tasks = [
        asyncio.create_task(_drain(_stream_single_model(llm_interface, spec, messages)))
        for spec in model_specs
    ]

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
    from llm_interface_pkg.interface import LLMInterface

    llm_interface = getattr(request.app.state, "_compare_llm_interface", None)
    if llm_interface is None:
        llm_interface = LLMInterface()
        request.app.state._compare_llm_interface = llm_interface

    user_content = body.prompt
    if body.context:
        user_content = f"{body.context}\n\n{user_content}"

    messages = [{"role": "user", "content": user_content}]

    return StreamingResponse(
        _fan_out_stream(llm_interface, body.models, messages),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
