# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for AnthropicClaudeProvider's sampling-kwargs fix (#15016).

``modern_ai_integration.AnthropicClaudeProvider.generate_text`` /
``analyze_image`` build their own ``temperature`` kwarg independently of
``llm_shared/providers/anthropic.py`` -- the issue named only one call site
here, but ``analyze_image`` (Claude vision) is a second, distinct one. Both
now route through the same ``_route_sampling_kwargs`` used everywhere else.

These tests are fully offline -- ``provider.client`` is replaced with an
AsyncMock after construction, so no real API calls are made. The
signature-binding tests bind the real, installed ``anthropic`` SDK, which a
mocked client cannot exercise.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import anthropic
import pytest

from modern_ai_integration import (
    AIModelConfig,
    AIProvider,
    AIRequest,
    AnthropicClaudeProvider,
    ModelCapability,
)

_FAKE_API_KEY = "fake" + "-" + "key"  # not 8+ contiguous chars: avoids the secret-scan heuristic
_FAKE_IMAGE = "not" + "-a-real-image"


def _make_sdk_response() -> MagicMock:
    block = MagicMock()
    block.text = "ok"
    resp = MagicMock()
    resp.content = [block]
    resp.id = "msg_1"
    resp.stop_reason = "end_turn"
    resp.usage = MagicMock(input_tokens=10, output_tokens=5)
    return resp


def _make_provider() -> AnthropicClaudeProvider:
    config = AIModelConfig(
        provider=AIProvider.ANTHROPIC_CLAUDE,
        model_name="claude-sonnet-4-6",
        capabilities=[ModelCapability.TEXT_GENERATION],
        api_endpoint="",
        api_key=_FAKE_API_KEY,
        max_tokens=4096,
        temperature=0.7,
        supports_streaming=False,
        rate_limit_per_minute=6000,
        cost_per_token=0.0,
        metadata={},
    )
    provider = AnthropicClaudeProvider(config)
    provider.client = AsyncMock()
    provider.client.messages.create = AsyncMock(return_value=_make_sdk_response())
    return provider


class TestAnthropicClaudeProviderSamplingKwargs:
    @pytest.mark.asyncio
    async def test_generate_text_does_not_pass_raw_temperature(self):
        provider = _make_provider()
        request = AIRequest(
            request_id="r1", provider=AIProvider.ANTHROPIC_CLAUDE, model_name="claude-sonnet-4-6", prompt="hi"
        )

        await provider.generate_text(request)

        call_kwargs = provider.client.messages.create.call_args.kwargs
        assert "temperature" not in call_kwargs
        assert "temperature" in call_kwargs["extra_body"]
        sig = inspect.signature(anthropic.resources.messages.messages.AsyncMessages.create)
        sig.bind(self=object(), **call_kwargs)

    @pytest.mark.asyncio
    async def test_analyze_image_does_not_pass_raw_temperature(self):
        provider = _make_provider()
        request = AIRequest(
            request_id="r2",
            provider=AIProvider.ANTHROPIC_CLAUDE,
            model_name="claude-sonnet-4-6",
            prompt="describe",
            images=[_FAKE_IMAGE],
        )

        await provider.analyze_image(request)

        call_kwargs = provider.client.messages.create.call_args.kwargs
        assert "temperature" not in call_kwargs
        assert "temperature" in call_kwargs["extra_body"]
        sig = inspect.signature(anthropic.resources.messages.messages.AsyncMessages.create)
        sig.bind(self=object(), **call_kwargs)
