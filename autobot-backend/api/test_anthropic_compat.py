# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Anthropic-compatible /v1/messages endpoint (#6591).

Tests:
  1. POST /v1/messages (non-streaming) returns Anthropic-shaped response
  2. POST /v1/messages (streaming) returns correct Anthropic SSE event sequence
  3. Round-trip: Anthropic request → provider → Anthropic response shape
  4. stop_reason mapping from provider finish_reason
  5. x-llm-cost header present on non-streaming response
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.anthropic_compat import _map_finish_reason, router
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


def _make_mock_registry(content: str = "Hello from AutoBot"):
    """Return a mocked ProviderRegistry with one provider."""
    from llm_shared.models import LLMResponse

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

    mock_registry = MagicMock()
    mock_registry.get_provider_for_request = AsyncMock(return_value=mock_provider)
    return mock_registry


# ---------------------------------------------------------------------------
# Tests: non-streaming
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_messages_non_streaming_returns_anthropic_shape():
    """POST /v1/messages (non-streaming) must return Anthropic Messages response shape."""
    mock_registry = _make_mock_registry("Hello from AutoBot")

    with (
        patch("api.anthropic_compat.get_provider_registry", return_value=mock_registry),
        patch("api.anthropic_compat._resolve_auth", return_value=(_SYNTHETIC_USER, None)),
        patch("api.anthropic_compat._oai_limiter") as mock_limiter,
    ):
        mock_limiter.check_or_429 = AsyncMock(return_value=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "autobot-model-1",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": False,
                },
            )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["type"] == "message"
    assert data["role"] == "assistant"
    assert data["id"].startswith("msg_")
    assert isinstance(data["content"], list)
    assert len(data["content"]) == 1
    assert data["content"][0]["type"] == "text"
    assert "Hello from AutoBot" in data["content"][0]["text"]
    assert "usage" in data
    assert "input_tokens" in data["usage"]
    assert "output_tokens" in data["usage"]
    assert data["stop_reason"] == "end_turn"


@pytest.mark.asyncio
async def test_messages_non_streaming_x_llm_cost_header():
    """Non-streaming response must include x-llm-cost header when cost > 0."""
    mock_registry = _make_mock_registry("Hello")

    with (
        patch("api.anthropic_compat.get_provider_registry", return_value=mock_registry),
        patch("api.anthropic_compat._resolve_auth", return_value=(_SYNTHETIC_USER, None)),
        patch("api.anthropic_compat._oai_limiter") as mock_limiter,
        patch("api.anthropic_compat.get_cost_tracker") as mock_tracker,
    ):
        mock_limiter.check_or_429 = AsyncMock(return_value=None)
        mock_tracker.return_value.calculate_cost.return_value = 0.00123
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "autobot-model-1",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
            )

    assert resp.status_code == 200
    assert "x-llm-cost" in resp.headers
    assert float(resp.headers["x-llm-cost"]) == pytest.approx(0.00123)


@pytest.mark.asyncio
async def test_messages_with_system_prompt():
    """System field must be accepted and forwarded without error."""
    mock_registry = _make_mock_registry("OK")

    with (
        patch("api.anthropic_compat.get_provider_registry", return_value=mock_registry),
        patch("api.anthropic_compat._resolve_auth", return_value=(_SYNTHETIC_USER, None)),
        patch("api.anthropic_compat._oai_limiter") as mock_limiter,
    ):
        mock_limiter.check_or_429 = AsyncMock(return_value=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "autobot-model-1",
                    "max_tokens": 50,
                    "system": "You are a helpful assistant.",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["type"] == "message"


# ---------------------------------------------------------------------------
# Tests: streaming SSE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_messages_streaming_returns_anthropic_sse_events():
    """POST /v1/messages (stream=true) must return correct Anthropic SSE event sequence."""
    mock_registry = _make_mock_registry()

    with (
        patch("api.anthropic_compat.get_provider_registry", return_value=mock_registry),
        patch("api.anthropic_compat._resolve_auth", return_value=(_SYNTHETIC_USER, None)),
        patch("api.anthropic_compat._oai_limiter") as mock_limiter,
    ):
        mock_limiter.check_or_429 = AsyncMock(return_value=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            async with client.stream(
                "POST",
                "/v1/messages",
                json={
                    "model": "autobot-model-1",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": True,
                },
            ) as response:
                assert response.status_code == 200
                raw = await response.aread()

    text = raw.decode("utf-8")

    # Parse event types from SSE
    event_types = []
    for line in text.splitlines():
        if line.startswith("event: "):
            event_types.append(line[len("event: ") :].strip())

    # Required Anthropic SSE event order
    assert "message_start" in event_types
    assert "content_block_start" in event_types
    assert "ping" in event_types
    assert "content_block_delta" in event_types
    assert "content_block_stop" in event_types
    assert "message_delta" in event_types
    assert "message_stop" in event_types

    # message_start must come first
    assert event_types[0] == "message_start"
    # message_stop must come last
    assert event_types[-1] == "message_stop"


@pytest.mark.asyncio
async def test_messages_streaming_data_lines_are_valid_json():
    """All data: lines in streaming response must be valid JSON dicts."""
    mock_registry = _make_mock_registry()

    with (
        patch("api.anthropic_compat.get_provider_registry", return_value=mock_registry),
        patch("api.anthropic_compat._resolve_auth", return_value=(_SYNTHETIC_USER, None)),
        patch("api.anthropic_compat._oai_limiter") as mock_limiter,
    ):
        mock_limiter.check_or_429 = AsyncMock(return_value=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            async with client.stream(
                "POST",
                "/v1/messages",
                json={
                    "model": "autobot-model-1",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": True,
                },
            ) as response:
                raw = await response.aread()

    text = raw.decode("utf-8")
    data_lines = [line[len("data: ") :].strip() for line in text.splitlines() if line.startswith("data: ")]
    assert len(data_lines) >= 1
    for raw_json in data_lines:
        parsed = json.loads(raw_json)
        assert "type" in parsed, f"Missing 'type' in: {parsed}"


@pytest.mark.asyncio
async def test_messages_streaming_content_delta_carries_text():
    """content_block_delta events must carry the provider text chunks."""
    mock_registry = _make_mock_registry()

    with (
        patch("api.anthropic_compat.get_provider_registry", return_value=mock_registry),
        patch("api.anthropic_compat._resolve_auth", return_value=(_SYNTHETIC_USER, None)),
        patch("api.anthropic_compat._oai_limiter") as mock_limiter,
    ):
        mock_limiter.check_or_429 = AsyncMock(return_value=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            async with client.stream(
                "POST",
                "/v1/messages",
                json={
                    "model": "autobot-model-1",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": True,
                },
            ) as response:
                raw = await response.aread()

    text = raw.decode("utf-8")
    # Collect all data payloads
    data_payloads = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("event: content_block_delta") and i + 1 < len(lines):
            data_line = lines[i + 1]
            if data_line.startswith("data: "):
                data_payloads.append(json.loads(data_line[len("data: ") :]))

    assert len(data_payloads) >= 1, "Expected at least one content_block_delta"
    combined = "".join(p["delta"]["text"] for p in data_payloads)
    assert "Hello" in combined


# ---------------------------------------------------------------------------
# Tests: stop_reason mapping
# ---------------------------------------------------------------------------


def test_map_finish_reason_stop():
    assert _map_finish_reason("stop") == "end_turn"
    assert _map_finish_reason(None) == "end_turn"


def test_map_finish_reason_length():
    assert _map_finish_reason("length") == "max_tokens"
    assert _map_finish_reason("max_tokens") == "max_tokens"


def test_map_finish_reason_tool_use():
    assert _map_finish_reason("tool_calls") == "tool_use"
    assert _map_finish_reason("tool_use") == "tool_use"


# ---------------------------------------------------------------------------
# Tests: round-trip conversion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_round_trip_anthropic_request_openai_provider_anthropic_response():
    """Round-trip: Anthropic-format request → provider → Anthropic-format response."""
    mock_registry = _make_mock_registry("Round-trip success")

    with (
        patch("api.anthropic_compat.get_provider_registry", return_value=mock_registry),
        patch("api.anthropic_compat._resolve_auth", return_value=(_SYNTHETIC_USER, None)),
        patch("api.anthropic_compat._oai_limiter") as mock_limiter,
    ):
        mock_limiter.check_or_429 = AsyncMock(return_value=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/messages",
                json={
                    "model": "autobot-model-1",
                    "max_tokens": 256,
                    "system": "Be concise.",
                    "messages": [
                        {"role": "user", "content": "What is 2+2?"},
                        {"role": "assistant", "content": "4"},
                        {"role": "user", "content": "And 3+3?"},
                    ],
                },
            )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Must be valid Anthropic response shape
    assert data["type"] == "message"
    assert data["role"] == "assistant"
    assert data["id"].startswith("msg_")
    assert data["content"][0]["text"] == "Round-trip success"
    assert data["stop_reason"] == "end_turn"
    assert "usage" in data
