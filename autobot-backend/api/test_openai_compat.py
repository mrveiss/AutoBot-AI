# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for OpenAI-compatible /v1 endpoints (#4447).

Tests:
  1. POST /v1/chat/completions (non-streaming) returns OpenAI-shaped response
  2. GET  /v1/models returns a list of model objects
  3. POST /v1/chat/completions (streaming) returns SSE chunks + [DONE]
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.openai_compat import router
from auth_middleware import get_current_user

# ---------------------------------------------------------------------------
# Minimal test app
# ---------------------------------------------------------------------------

app = FastAPI()
app.include_router(router, prefix="/v1")
# Bypass auth so tests never need real JWT tokens.
app.dependency_overrides[get_current_user] = lambda: {"username": "test", "role": "user"}


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------

_SYNTHETIC_USER = {"username": "test", "role": "user"}


def _make_mock_registry(content: str = "Hello from AutoBot", models: list = None):
    """Return a mocked ProviderRegistry with one provider."""
    from llm_shared.models import LLMResponse

    models = models or ["autobot-model-1"]

    mock_provider = MagicMock()
    mock_provider.provider_name = "mock_provider"

    llm_resp = LLMResponse(
        content=content,
        model="autobot-model-1",
        provider="mock_provider",
        finish_reason="stop",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    mock_provider.chat_completion = AsyncMock(return_value=llm_resp)

    async def _fake_stream(request):
        yield "Hello "
        yield "from AutoBot"

    mock_provider.stream_completion = _fake_stream
    mock_provider.list_models = AsyncMock(return_value=models)

    mock_registry = MagicMock()
    mock_registry.get_provider_for_request = AsyncMock(return_value=mock_provider)
    mock_registry.list_providers = MagicMock(return_value=[{"name": "mock_provider"}])
    mock_registry._providers = {"mock_provider": mock_provider}
    return mock_registry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_completions_non_streaming_returns_oai_shape():
    """POST /v1/chat/completions (non-streaming) must return OpenAI-shaped JSON."""
    mock_registry = _make_mock_registry("Hello from AutoBot")

    with (
        patch("api.openai_compat.get_provider_registry", return_value=mock_registry),
        patch("api.openai_compat._get_user", return_value=_SYNTHETIC_USER),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "autobot-model-1",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": False,
                },
            )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["object"] == "chat.completion"
    assert "id" in data
    assert data["id"].startswith("chatcmpl-")
    assert "choices" in data
    assert len(data["choices"]) == 1
    choice = data["choices"][0]
    assert choice["message"]["role"] == "assistant"
    assert "Hello from AutoBot" in choice["message"]["content"]
    assert "usage" in data
    assert data["usage"]["total_tokens"] >= 0


@pytest.mark.asyncio
async def test_non_streaming_usage_omits_cost_usd():
    """Non-streaming usage object must NOT include cost_usd (GH#7639 / MVA-202).

    Strict OAI clients (LiteLLM, openai-python strict mode) reject unknown fields.
    cost_usd must be absent entirely when None, not serialized as null.
    """
    mock_registry = _make_mock_registry("Hello from AutoBot")

    with (
        patch("api.openai_compat.get_provider_registry", return_value=mock_registry),
        patch("api.openai_compat._get_user", return_value=_SYNTHETIC_USER),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "autobot-model-1",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": False,
                },
            )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "usage" in data
    assert "cost_usd" not in data["usage"], (
        "cost_usd must be absent from the non-streaming usage object; " "strict OAI clients reject unknown fields"
    )


@pytest.mark.asyncio
async def test_non_streaming_x_llm_cost_header_present_and_numeric():
    """Non-streaming response must include x-llm-cost header with a numeric value."""
    mock_registry = _make_mock_registry("Hello")

    with (
        patch("api.openai_compat.get_provider_registry", return_value=mock_registry),
        patch("api.openai_compat._get_user", return_value=_SYNTHETIC_USER),
        patch("api.openai_compat.get_cost_tracker") as mock_tracker,
    ):
        mock_tracker.return_value.calculate_cost.return_value = 0.00123
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "autobot-model-1", "messages": [{"role": "user", "content": "Hi"}], "stream": False},
            )

    assert resp.status_code == 200
    assert "x-llm-cost" in resp.headers, "x-llm-cost header must be present"
    cost = float(resp.headers["x-llm-cost"])
    assert cost > 0, "x-llm-cost must be a positive float"


@pytest.mark.asyncio
async def test_list_models_returns_model_list():
    """GET /v1/models must return {object: 'list', data: [{id, object, ...}]}."""
    mock_registry = _make_mock_registry(models=["gpt-autobot-1", "gpt-autobot-2"])

    with (
        patch("api.openai_compat.get_provider_registry", return_value=mock_registry),
        patch("api.openai_compat._get_user", return_value=_SYNTHETIC_USER),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/models")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["object"] == "list"
    assert isinstance(data["data"], list)
    assert len(data["data"]) >= 1
    for model in data["data"]:
        assert "id" in model
        assert model["object"] == "model"


@pytest.mark.asyncio
async def test_chat_completions_streaming_returns_sse_done():
    """POST /v1/chat/completions (stream=true) must return SSE events and [DONE]."""
    mock_registry = _make_mock_registry()

    with (
        patch("api.openai_compat.get_provider_registry", return_value=mock_registry),
        patch("api.openai_compat._get_user", return_value=_SYNTHETIC_USER),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            async with client.stream(
                "POST",
                "/v1/chat/completions",
                json={
                    "model": "autobot-model-1",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": True,
                },
            ) as response:
                assert response.status_code == 200
                raw = await response.aread()

    text = raw.decode("utf-8")
    # Must end with [DONE]
    assert "data: [DONE]" in text
    # All data lines except [DONE] must be valid JSON with expected shape
    data_lines = [
        line[len("data: ") :].strip()
        for line in text.splitlines()
        if line.startswith("data: ") and line.strip() != "data: [DONE]"
    ]
    assert len(data_lines) >= 2, "Expected at least role chunk + content chunk"
    for raw_json in data_lines:
        chunk = json.loads(raw_json)
        assert chunk["object"] == "chat.completion.chunk"
        assert "choices" in chunk


def _stream_post(payload, *, mock_tracker=None):
    """Helper that issues the streaming POST and returns decoded SSE text."""
    import contextlib

    mock_registry = _make_mock_registry()

    async def _run():
        patches = [
            patch("api.openai_compat.get_provider_registry", return_value=mock_registry),
            patch("api.openai_compat._get_user", return_value=_SYNTHETIC_USER),
        ]
        if mock_tracker is not None:
            patches.append(patch("api.openai_compat.get_cost_tracker", return_value=mock_tracker))
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                async with client.stream("POST", "/v1/chat/completions", json=payload) as response:
                    assert response.status_code == 200
                    return (await response.aread()).decode("utf-8")

    return _run


def _parse_sse_chunks(text: str):
    """Return the list of parsed JSON chunks (excluding [DONE])."""
    return [
        json.loads(line[len("data: ") :])
        for line in text.splitlines()
        if line.startswith("data: ") and line.strip() != "data: [DONE]"
    ]


@pytest.mark.asyncio
async def test_streaming_emits_usage_when_include_usage_true():
    """When stream_options.include_usage=true, the final chunk before [DONE] must carry usage (#5019)."""
    text = await _stream_post(
        {
            "model": "autobot-model-1",
            "messages": [{"role": "user", "content": "Hello world"}],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
    )()
    assert "data: [DONE]" in text
    chunks = _parse_sse_chunks(text)
    usage_chunks = [c for c in chunks if c.get("usage") is not None]
    assert len(usage_chunks) == 1, "Expected exactly one chunk with usage"
    usage = usage_chunks[0]["usage"]
    assert usage["prompt_tokens"] >= 1
    assert usage["completion_tokens"] >= 1
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    # Usage chunk must be the last chunk before [DONE]
    assert chunks[-1] is usage_chunks[0]


@pytest.mark.asyncio
async def test_streaming_omits_usage_when_include_usage_false():
    """stream_options.include_usage=false → no usage chunk (#5019)."""
    text = await _stream_post(
        {
            "model": "autobot-model-1",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
            "stream_options": {"include_usage": False},
        }
    )()
    chunks = _parse_sse_chunks(text)
    assert all(c.get("usage") is None for c in chunks)


@pytest.mark.asyncio
async def test_streaming_omits_usage_when_stream_options_absent():
    """stream_options absent entirely → backwards compat: no usage chunk (#5019)."""
    text = await _stream_post(
        {
            "model": "autobot-model-1",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        }
    )()
    chunks = _parse_sse_chunks(text)
    assert all(c.get("usage") is None for c in chunks)


@pytest.mark.asyncio
async def test_streaming_cost_chunk_is_valid_chat_completion_chunk():
    """Cost SSE chunk must be a valid ChatCompletionChunk, not a bare dict (#7610)."""
    mock_tracker = MagicMock()
    mock_tracker.calculate_cost = MagicMock(return_value=0.00123)

    text = await _stream_post(
        {
            "model": "autobot-model-1",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        },
        mock_tracker=mock_tracker,
    )()

    assert "data: [DONE]" in text
    chunks = _parse_sse_chunks(text)
    # Every chunk must have the required ChatCompletionChunk fields
    for chunk in chunks:
        assert chunk.get("object") == "chat.completion.chunk", f"Invalid chunk: {chunk}"
        assert "choices" in chunk, f"Missing 'choices' in chunk: {chunk}"
        assert "id" in chunk, f"Missing 'id' in chunk: {chunk}"
        assert "model" in chunk, f"Missing 'model' in chunk: {chunk}"
    # The cost chunk (choices=[]) must carry cost_usd in usage
    cost_chunks = [c for c in chunks if c.get("usage") and c["usage"].get("cost_usd") is not None]
    assert len(cost_chunks) == 1, "Expected exactly one chunk with cost_usd in usage"
    assert cost_chunks[0]["usage"]["cost_usd"] == pytest.approx(0.00123)


@pytest.mark.asyncio
async def test_streaming_cost_embedded_in_usage_chunk_when_include_usage_true():
    """When include_usage=true and cost>0, cost_usd must appear in the usage chunk (#7610)."""
    mock_tracker = MagicMock()
    mock_tracker.calculate_cost = MagicMock(return_value=0.005)

    text = await _stream_post(
        {
            "model": "autobot-model-1",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
            "stream_options": {"include_usage": True},
        },
        mock_tracker=mock_tracker,
    )()

    chunks = _parse_sse_chunks(text)
    usage_chunks = [c for c in chunks if c.get("usage") is not None]
    assert len(usage_chunks) == 1, "Expected exactly one chunk with usage"
    usage = usage_chunks[0]["usage"]
    assert usage["prompt_tokens"] >= 1
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    assert usage.get("cost_usd") == pytest.approx(0.005)
