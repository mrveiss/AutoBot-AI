# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for ModelFallbackCoordinator (GH#8998)."""

from __future__ import annotations

from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_shared.fallback_chain import FallbackChain, FallbackChainManager
from llm_shared.model_fallback_coordinator import ModelFallbackCoordinator
from llm_shared.models import LLMRequest, LLMResponse
from llm_shared.optimization.rate_limiter import RateLimitError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(model: str = "claude-opus-4", provider: str | None = None) -> LLMRequest:
    req = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    req.model_name = model
    if provider:
        from llm_shared.models import ProviderType

        try:
            req.provider = ProviderType(provider)
        except ValueError:
            req.provider = None
    return req


def _ok_response(model: str = "claude-opus-4") -> LLMResponse:
    return LLMResponse(content="hello", model=model, provider="anthropic")


def _make_registry(side_effects: list) -> MagicMock:
    """Registry whose get_provider_for_request returns a provider that yields side_effects."""
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
    provider.stream_completion = AsyncMock()

    registry = MagicMock()
    registry.get_provider_for_request = AsyncMock(return_value=provider)
    return registry


def _chain_manager_with(
    primary: str,
    fallbacks: list[str],
    primary_provider: str = "anthropic",
    fallback_providers: Optional[list[str]] = None,
) -> FallbackChainManager:
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_primary_succeeds_no_fallback():
    """No fallback triggered when primary model succeeds."""
    coordinator = ModelFallbackCoordinator()
    response = _ok_response()
    registry = _make_registry([response])

    result = await coordinator.execute_with_fallback(_make_request(), registry)

    assert result.content == "hello"
    assert result.fallback_used is False
    assert result.provider_metadata["fallback_used"] is False
    assert result.provider_metadata["attempt_count"] == 1


@pytest.mark.asyncio
async def test_rate_limit_triggers_fallback():
    """Primary 429 → fallback model succeeds."""
    coordinator = ModelFallbackCoordinator()
    fallback_response = _ok_response("claude-sonnet-4")
    registry = _make_registry([RateLimitError("quota hit"), fallback_response])

    mgr = _chain_manager_with("claude-opus-4", ["claude-sonnet-4"])

    with patch("llm_shared.model_fallback_coordinator.get_fallback_chain_manager", return_value=mgr):
        result = await coordinator.execute_with_fallback(_make_request("claude-opus-4"), registry)

    assert result.content == "hello"
    assert result.fallback_used is True
    assert result.provider_metadata["primary_model"] == "claude-opus-4"
    assert result.provider_metadata["fallback_model"] == "claude-sonnet-4"
    assert result.provider_metadata["fallback_reason"] == "rate_limit_429"
    assert result.provider_metadata["attempt_count"] == 2


@pytest.mark.asyncio
async def test_multiple_fallback_hops():
    """Two rate limits → succeeds on third model in chain."""
    coordinator = ModelFallbackCoordinator()
    ok = _ok_response("claude-haiku-4")
    registry = _make_registry(
        [
            RateLimitError("quota"),
            RateLimitError("quota"),
            ok,
        ]
    )

    mgr = _chain_manager_with("claude-opus-4", ["claude-sonnet-4", "claude-haiku-4"])

    with patch("llm_shared.model_fallback_coordinator.get_fallback_chain_manager", return_value=mgr):
        result = await coordinator.execute_with_fallback(_make_request("claude-opus-4"), registry, max_attempts=3)

    assert result.content == "hello"
    assert result.provider_metadata["attempt_count"] == 3
    assert result.provider_metadata["fallback_chain_tried"] == ["claude-opus-4", "claude-sonnet-4", "claude-haiku-4"]


@pytest.mark.asyncio
async def test_all_fallbacks_exhausted():
    """All models rate-limited → returns error response, no exception."""
    coordinator = ModelFallbackCoordinator()
    registry = _make_registry([RateLimitError("quota")] * 10)

    mgr = _chain_manager_with("claude-opus-4", ["claude-sonnet-4"])

    with patch("llm_shared.model_fallback_coordinator.get_fallback_chain_manager", return_value=mgr):
        result = await coordinator.execute_with_fallback(_make_request("claude-opus-4"), registry, max_attempts=2)

    assert result.content == ""
    assert result.error is not None
    assert result.provider_metadata["fallback_exhausted"] is True


@pytest.mark.asyncio
async def test_no_chain_registered_returns_error():
    """No fallback chain for model → first error returned cleanly."""
    coordinator = ModelFallbackCoordinator()
    registry = _make_registry([RateLimitError("quota")])

    empty_mgr = FallbackChainManager.__new__(FallbackChainManager)
    empty_mgr._chains = {}

    with patch("llm_shared.model_fallback_coordinator.get_fallback_chain_manager", return_value=empty_mgr):
        result = await coordinator.execute_with_fallback(_make_request("unknown-model"), registry)

    assert result.error is not None
    assert result.provider_metadata["fallback_exhausted"] is True


@pytest.mark.asyncio
async def test_fallback_disabled_skips_coordinator():
    """request.fallback_enabled=False bypasses fallback logic."""
    coordinator = ModelFallbackCoordinator()
    registry = _make_registry([RateLimitError("quota")])

    req = _make_request("claude-opus-4")
    req.fallback_enabled = False

    with pytest.raises(RateLimitError):
        await coordinator.execute_with_fallback(req, registry)


@pytest.mark.asyncio
async def test_audit_metadata_on_no_fallback():
    """Non-fallback response metadata is correct."""
    coordinator = ModelFallbackCoordinator()
    registry = _make_registry([_ok_response()])

    result = await coordinator.execute_with_fallback(_make_request("claude-opus-4"), registry)

    md = result.provider_metadata
    assert md["fallback_used"] is False
    assert md["fallback_model"] is None
    assert md["fallback_reason"] is None
    assert md["fallback_exhausted"] is False
    assert md["fallback_chain_tried"] == ["claude-opus-4"]


@pytest.mark.asyncio
async def test_provider_none_returns_error_response():
    """Registry returns None provider → error response without exception."""
    coordinator = ModelFallbackCoordinator()
    registry = MagicMock()
    registry.get_provider_for_request = AsyncMock(return_value=None)

    result = await coordinator.execute_with_fallback(_make_request(), registry)

    assert result.error == "All providers unavailable"
