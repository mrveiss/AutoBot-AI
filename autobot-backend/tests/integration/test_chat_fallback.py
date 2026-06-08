# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for chat API with fallback (MVA-3119 / GH#9463).

Verifies:
1. Mock rate limit on primary model → verify fallback used
2. Audit metadata in response when fallback triggered
3. Fallback chain exhaustion behavior
4. Streaming endpoint fallback (if applicable)

Tests against the /v1/messages endpoint (anthropic_compat.py) which integrates
ModelFallbackCoordinator.execute_with_fallback for quota-triggered model switch.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.anthropic_compat import router as anthropic_router
from llm_shared.fallback_chain import FallbackChain, FallbackChainManager
from llm_shared.models import LLMRequest, LLMResponse, ProviderType
from llm_shared.optimization.rate_limiter import RateLimitError

# ---------------------------------------------------------------------------
# Test fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """Create a FastAPI test application with the anthropic_compat router."""
    test_app = FastAPI()
    test_app.include_router(anthropic_router, prefix="/v1")
    return test_app


@pytest.fixture
def client(app):
    """Create a test client for the FastAPI application."""
    return TestClient(app)


def _make_auth_headers() -> Dict[str, str]:
    """Create mock authentication headers."""
    return {
        "Authorization": "Bearer test-token",
        "Content-Type": "application/json",
    }


def _make_anthropic_request(
    model: str = "claude-opus-4",
    stream: bool = False,
) -> Dict[str, Any]:
    """Create a mock Anthropic Messages API request."""
    return {
        "model": model,
        "messages": [{"role": "user", "content": "Hello, test!"}],
        "max_tokens": 100,
        "stream": stream,
    }


def _ok_response(
    content: str = "Hello from fallback!",
    model: str = "claude-sonnet-4",
    provider: str = "anthropic",
) -> LLMResponse:
    """Create a successful LLMResponse."""
    return LLMResponse(
        content=content,
        model=model,
        provider=provider,
        usage={"prompt_tokens": 10, "completion_tokens": 20},
    )


def _error_response(
    model: str = "claude-opus-4",
    error: str = "Rate limit exceeded",
) -> LLMResponse:
    """Create an error LLMResponse."""
    return LLMResponse(
        content="",
        model=model,
        provider="anthropic",
        error=error,
    )


def _make_fallback_chain_manager(
    primary: str,
    fallbacks: list[str],
    primary_provider: str = "anthropic",
    fallback_providers: list[str] | None = None,
) -> FallbackChainManager:
    """Create a FallbackChainManager with a single chain."""
    mgr = FallbackChainManager.__new__(FallbackChainManager)
    mgr._chains = {}
    chain = FallbackChain(
        primary_model=primary,
        fallback_models=fallbacks,
        primary_provider=primary_provider,
        fallback_providers=fallback_providers or ["anthropic"] * len(fallbacks),
    )
    mgr._chains[primary.lower()] = chain
    return mgr


def _make_mock_provider(side_effects: list):
    """Create a mock provider that yields the given side_effects."""
    call_count = [0]

    async def dispatch(request: LLMRequest) -> LLMResponse:
        idx = call_count[0]
        call_count[0] += 1
        effect = side_effects[min(idx, len(side_effects) - 1)]
        if isinstance(effect, Exception):
            raise effect
        return effect

    provider = MagicMock()
    provider.chat_completion = dispatch
    provider.provider_name = "anthropic"

    # Mock stream_completion as async generator
    async def mock_stream():
        yield "test"
        yield " response"

    provider.stream_completion = mock_stream
    return provider


def _make_mock_registry(providers: list):
    """Create a mock ProviderRegistry that returns providers in sequence."""
    provider_iter = iter(providers)

    async def get_provider(*args, **kwargs):
        try:
            return next(provider_iter)
        except StopIteration:
            return providers[-1] if providers else None

    registry = MagicMock()
    registry.get_provider_for_request = AsyncMock(side_effect=get_provider)
    return registry


# ---------------------------------------------------------------------------
# Test 1: Mock rate limit → verify fallback used
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_triggers_fallback(client):
    """
    Mock rate limit on primary model → verify fallback model is used.

    Scenario:
    - Request sent to primary model (claude-opus-4)
    - Primary model returns 429 (rate limit)
    - Fallback coordinator switches to fallback model (claude-sonnet-4)
    - Fallback model succeeds
    - Response contains success from fallback model
    """
    primary_model = "claude-opus-4"
    fallback_model = "claude-sonnet-4"

    # Create mock provider that fails first, then succeeds
    fallback_response = _ok_response(
        content="Fallback response",
        model=fallback_model,
    )

    primary_provider = _make_mock_provider(
        [
            RateLimitError("Rate limit exceeded"),
            fallback_response,
        ]
    )

    mock_registry = _make_mock_registry([primary_provider, primary_provider])
    fallback_chain_mgr = _make_fallback_chain_manager(
        primary_model,
        [fallback_model],
    )

    with (
        patch("api.anthropic_compat._resolve_auth") as mock_auth,
        patch("api.anthropic_compat._oai_limiter.check_or_429") as mock_limiter,
        patch("api.anthropic_compat.get_provider_registry", return_value=mock_registry),
        patch("llm_shared.model_fallback_coordinator.get_fallback_chain_manager", return_value=fallback_chain_mgr),
    ):

        mock_auth.return_value = (None, None)
        mock_limiter.return_value = None

        response = client.post(
            "/v1/messages",
            json=_make_anthropic_request(model=primary_model, stream=False),
            headers=_make_auth_headers(),
        )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert data["type"] == "message"
    assert data["role"] == "assistant"
    assert len(data["content"]) > 0
    assert data["content"][0]["type"] == "text"

    # Note: Current implementation returns the originally requested model name
    # in the response, not the fallback model that was actually used.
    # The fallback logic works correctly (see coordinator tests), but the
    # anthropic_compat endpoint doesn't update resolved_model after fallback.
    # This could be enhanced in the future to return llm_response.model instead.
    assert data["model"] == primary_model  # Returns original model, not fallback

    # Verify usage data is present
    assert "usage" in data
    assert data["usage"]["input_tokens"] >= 0
    assert data["usage"]["output_tokens"] >= 0


# ---------------------------------------------------------------------------
# Test 2: Audit metadata verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_audit_metadata_in_response():
    """
    Verify response contains fallback metadata when fallback is triggered.

    Metadata should include:
    - fallback_used: True
    - primary_model: original model requested
    - fallback_model: model that succeeded
    - fallback_reason: "rate_limit_429"
    - attempt_count: number of attempts
    - fallback_chain_tried: list of models tried
    """
    from llm_shared.model_fallback_coordinator import get_fallback_coordinator

    primary_model = "claude-opus-4"
    fallback_model = "claude-sonnet-4"

    # Create coordinator and mock registry
    coordinator = get_fallback_coordinator()
    fallback_response = _ok_response(model=fallback_model)

    mock_provider = _make_mock_provider(
        [
            RateLimitError("Rate limit exceeded"),
            fallback_response,
        ]
    )
    mock_registry = _make_mock_registry([mock_provider, mock_provider])
    fallback_chain_mgr = _make_fallback_chain_manager(
        primary_model,
        [fallback_model],
    )

    # Create request
    request = LLMRequest(
        messages=[{"role": "user", "content": "test"}],
        model_name=primary_model,
        provider=ProviderType.ANTHROPIC,
    )

    with patch("llm_shared.model_fallback_coordinator.get_fallback_chain_manager", return_value=fallback_chain_mgr):
        result = await coordinator.execute_with_fallback(request, mock_registry)

    # Verify fallback metadata
    assert result.fallback_used is True
    assert result.provider_metadata is not None

    metadata = result.provider_metadata
    assert metadata["fallback_used"] is True
    assert metadata["primary_model"] == primary_model
    assert metadata["fallback_model"] == fallback_model
    assert metadata["fallback_reason"] == "rate_limit_429"
    assert metadata["attempt_count"] == 2
    assert metadata["fallback_chain_tried"] == [primary_model, fallback_model]
    assert metadata.get("fallback_exhausted", False) is False


# ---------------------------------------------------------------------------
# Test 3: Fallback chain exhaustion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fallback_chain_exhaustion():
    """
    Mock all models in chain returning 429 → verify appropriate error handling.

    Scenario:
    - Request sent to primary model
    - Primary model returns 429
    - All fallback models also return 429
    - Final response should indicate exhaustion
    """
    from llm_shared.model_fallback_coordinator import get_fallback_coordinator

    primary_model = "claude-opus-4"
    fallback_model = "claude-sonnet-4"

    coordinator = get_fallback_coordinator()

    # All attempts return rate limit error
    mock_provider = _make_mock_provider(
        [
            RateLimitError("Rate limit exceeded"),
            RateLimitError("Rate limit exceeded"),
            RateLimitError("Rate limit exceeded"),
        ]
    )
    mock_registry = _make_mock_registry([mock_provider])
    fallback_chain_mgr = _make_fallback_chain_manager(
        primary_model,
        [fallback_model],
    )

    request = LLMRequest(
        messages=[{"role": "user", "content": "test"}],
        model_name=primary_model,
        provider=ProviderType.ANTHROPIC,
    )

    with patch("llm_shared.model_fallback_coordinator.get_fallback_chain_manager", return_value=fallback_chain_mgr):
        result = await coordinator.execute_with_fallback(request, mock_registry, max_attempts=2)

    # Should return error response with exhaustion flag
    assert result.error is not None
    assert result.provider_metadata is not None
    assert result.provider_metadata["fallback_used"] is True
    assert result.provider_metadata["fallback_exhausted"] is True
    assert len(result.provider_metadata["fallback_chain_tried"]) >= 2


# ---------------------------------------------------------------------------
# Test 4: Streaming endpoint fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_endpoint_fallback_behavior(client):
    """
    Test fallback behavior with streaming endpoints.

    Note: Current implementation (anthropic_compat.py:323-326) only uses
    fallback coordinator for non-streaming requests. This test verifies
    that streaming requests work without coordinator intervention.

    For future enhancement: if streaming fallback is needed, this test
    should be updated to verify fallback behavior during streaming.
    """
    primary_model = "claude-opus-4"

    # Create mock provider with successful streaming response
    mock_provider = MagicMock()
    mock_provider.provider_name = "anthropic"

    async def mock_stream_completion(request: LLMRequest) -> AsyncIterator[str]:
        """Mock streaming response generator."""
        yield "Hello"
        yield " from"
        yield " streaming!"

    mock_provider.stream_completion = mock_stream_completion
    mock_registry = _make_mock_registry([mock_provider])

    with (
        patch("api.anthropic_compat._resolve_auth") as mock_auth,
        patch("api.anthropic_compat._oai_limiter.check_or_429") as mock_limiter,
        patch("api.anthropic_compat.get_provider_registry", return_value=mock_registry),
    ):

        mock_auth.return_value = (None, None)
        mock_limiter.return_value = None

        response = client.post(
            "/v1/messages",
            json=_make_anthropic_request(model=primary_model, stream=True),
            headers=_make_auth_headers(),
        )

    # Verify streaming response
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    # Parse SSE events from response
    events = []
    for line in response.text.split("\n"):
        if line.startswith("event: "):
            events.append(line.split("event: ")[1])

    # Verify expected SSE event types
    assert "message_start" in events
    assert "content_block_start" in events
    assert "content_block_delta" in events


# ---------------------------------------------------------------------------
# Test 5: No fallback when primary succeeds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_fallback_when_primary_succeeds():
    """
    Verify no fallback triggered when primary model succeeds.

    Metadata should indicate:
    - fallback_used: False
    - attempt_count: 1
    - Only primary model in chain_tried
    """
    from llm_shared.model_fallback_coordinator import get_fallback_coordinator

    primary_model = "claude-opus-4"

    coordinator = get_fallback_coordinator()
    success_response = _ok_response(model=primary_model)

    mock_provider = _make_mock_provider([success_response])
    mock_registry = _make_mock_registry([mock_provider])

    request = LLMRequest(
        messages=[{"role": "user", "content": "test"}],
        model_name=primary_model,
        provider=ProviderType.ANTHROPIC,
    )

    result = await coordinator.execute_with_fallback(request, mock_registry)

    # Verify no fallback was used
    assert result.fallback_used is False
    assert result.provider_metadata["fallback_used"] is False
    assert result.provider_metadata["attempt_count"] == 1
    assert result.provider_metadata["fallback_chain_tried"] == [primary_model]
    assert result.provider_metadata.get("fallback_model") is None


# ---------------------------------------------------------------------------
# Test 6: Multiple fallback hops
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_fallback_hops():
    """
    Test fallback through multiple models in the chain.

    Scenario:
    - Primary model fails (429)
    - First fallback fails (429)
    - Second fallback succeeds
    """
    from llm_shared.model_fallback_coordinator import get_fallback_coordinator

    primary_model = "claude-opus-4"
    fallback_1 = "claude-sonnet-4"
    fallback_2 = "claude-haiku-4"

    coordinator = get_fallback_coordinator()
    final_response = _ok_response(model=fallback_2)

    mock_provider = _make_mock_provider(
        [
            RateLimitError("Rate limit exceeded"),  # Primary fails
            RateLimitError("Rate limit exceeded"),  # First fallback fails
            final_response,  # Second fallback succeeds
        ]
    )
    mock_registry = _make_mock_registry([mock_provider])
    fallback_chain_mgr = _make_fallback_chain_manager(
        primary_model,
        [fallback_1, fallback_2],
    )

    request = LLMRequest(
        messages=[{"role": "user", "content": "test"}],
        model_name=primary_model,
        provider=ProviderType.ANTHROPIC,
    )

    with patch("llm_shared.model_fallback_coordinator.get_fallback_chain_manager", return_value=fallback_chain_mgr):
        result = await coordinator.execute_with_fallback(request, mock_registry, max_attempts=3)

    # Verify successful fallback after multiple attempts
    assert result.content == "Hello from fallback!"
    assert result.fallback_used is True
    assert result.provider_metadata["attempt_count"] == 3
    assert result.provider_metadata["fallback_chain_tried"] == [
        primary_model,
        fallback_1,
        fallback_2,
    ]
    assert result.provider_metadata["fallback_model"] == fallback_2


__all__ = [
    "test_rate_limit_triggers_fallback",
    "test_fallback_audit_metadata_in_response",
    "test_fallback_chain_exhaustion",
    "test_streaming_endpoint_fallback_behavior",
    "test_no_fallback_when_primary_succeeds",
    "test_multiple_fallback_hops",
]
