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
    from llm_interface_pkg.models import LLMResponse

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

    mock_provider.stream_completion = MagicMock(side_effect=lambda r: _fake_stream(r))
    mock_provider.list_models = AsyncMock(return_value=models)

    mock_registry = MagicMock()
    mock_registry.get_provider_for_request = AsyncMock(return_value=mock_provider)
    mock_registry.list_providers = MagicMock(
        return_value=[{"name": "mock_provider"}]
    )
    mock_registry._providers = {"mock_provider": mock_provider}
    return mock_registry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_completions_non_streaming_returns_oai_shape():
    """POST /v1/chat/completions (non-streaming) must return OpenAI-shaped JSON."""
    mock_registry = _make_mock_registry("Hello from AutoBot")

    with patch(
        "api.openai_compat.get_provider_registry", return_value=mock_registry
    ), patch("api.openai_compat._get_user", return_value=_SYNTHETIC_USER):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
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
async def test_list_models_returns_model_list():
    """GET /v1/models must return {object: 'list', data: [{id, object, ...}]}."""
    mock_registry = _make_mock_registry(models=["gpt-autobot-1", "gpt-autobot-2"])

    with patch(
        "api.openai_compat.get_provider_registry", return_value=mock_registry
    ), patch("api.openai_compat._get_user", return_value=_SYNTHETIC_USER):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
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

    with patch(
        "api.openai_compat.get_provider_registry", return_value=mock_registry
    ), patch("api.openai_compat._get_user", return_value=_SYNTHETIC_USER):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
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
        line[len("data: "):].strip()
        for line in text.splitlines()
        if line.startswith("data: ") and line.strip() != "data: [DONE]"
    ]
    assert len(data_lines) >= 2, "Expected at least role chunk + content chunk"
    for raw_json in data_lines:
        chunk = json.loads(raw_json)
        assert chunk["object"] == "chat.completion.chunk"
        assert "choices" in chunk
