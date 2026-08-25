# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the Anthropic sampling-kwargs fix (#15016).

anthropic>=1.0 removed temperature/top_p/top_k from messages.create()/
.stream()'s signature -- passing one as a keyword now raises TypeError
before any request is made. ``_route_sampling_kwargs`` moves a genuinely
set value into ``extra_body`` instead, which the API still honours.

``TestKwargsMatchRealSdkSignature`` is the regression test that would have
caught the original bug: a MagicMock/AsyncMock client accepts any keyword
argument, so it cannot catch a kwarg the SDK itself no longer declares.
``inspect.Signature.bind()`` against the REAL, installed ``anthropic`` SDK
performs exactly the check the SDK does at call time, with no network
request. Split out of ``test_anthropic_provider.py`` to keep that file
under the repo's file-size ceiling (#14236).
"""

from __future__ import annotations

import inspect

import anthropic
import pytest

from llm_shared.models import LLMRequest
from llm_shared.providers.anthropic import (
    AnthropicProvider,
    _route_sampling_kwargs,
    _thinking_budget_to_effort,
)


class TestRouteSamplingKwargs:
    def test_none_value_is_dropped_not_routed(self):
        kwargs = _route_sampling_kwargs({"model": "m", "temperature": None})
        assert "temperature" not in kwargs
        assert "extra_body" not in kwargs

    def test_set_value_moved_to_extra_body(self):
        kwargs = _route_sampling_kwargs({"model": "m", "temperature": 0.4})
        assert "temperature" not in kwargs
        assert kwargs["extra_body"] == {"temperature": 0.4}

    def test_top_p_and_top_k_also_routed(self):
        kwargs = _route_sampling_kwargs({"model": "m", "top_p": 0.9, "top_k": 40})
        assert "top_p" not in kwargs and "top_k" not in kwargs
        assert kwargs["extra_body"] == {"top_p": 0.9, "top_k": 40}

    def test_merges_into_existing_extra_body(self):
        kwargs = _route_sampling_kwargs({"model": "m", "temperature": 1, "extra_body": {"foo": "bar"}})
        assert kwargs["extra_body"] == {"foo": "bar", "temperature": 1}

    def test_no_sampling_keys_is_a_noop(self):
        kwargs = _route_sampling_kwargs({"model": "m", "max_tokens": 10})
        assert kwargs == {"model": "m", "max_tokens": 10}

    def test_temperature_dropped_not_routed_when_thinking_active(self):
        """#15042: current models reject a sampling kwarg outright once
        thinking is enabled, regardless of its value -- extra_body would
        just move the 400 server-side rather than avoid it."""
        kwargs = _route_sampling_kwargs({"model": "m", "temperature": 0.7, "thinking": {"type": "adaptive"}})
        assert "temperature" not in kwargs
        assert "extra_body" not in kwargs

    def test_top_p_and_top_k_also_dropped_when_thinking_active(self):
        kwargs = _route_sampling_kwargs(
            {"model": "m", "top_p": 0.9, "top_k": 40, "thinking": {"type": "enabled", "budget_tokens": 8000}}
        )
        assert "top_p" not in kwargs and "top_k" not in kwargs
        assert "extra_body" not in kwargs


class TestThinkingBudgetToEffort:
    @pytest.mark.parametrize(
        "budget_tokens,expected",
        [(1, "low"), (2000, "low"), (2001, "medium"), (10000, "high"), (10001, "xhigh"), (100000, "max")],
    )
    def test_tier_boundaries(self, budget_tokens, expected):
        assert _thinking_budget_to_effort(budget_tokens) == expected


# ---------------------------------------------------------------------------
# Kwargs bind against the REAL, installed anthropic SDK signature (#15016)
#
# A MagicMock/AsyncMock client accepts any keyword argument, so it cannot
# catch a kwarg the SDK no longer declares (anthropic 1.x removed temperature/
# top_p/top_k, raising TypeError). inspect.Signature.bind() performs exactly
# the check the real SDK method does at call time, with no network request.
# ---------------------------------------------------------------------------


class TestKwargsMatchRealSdkSignature:
    def _call_kwargs(self, request: LLMRequest, model: str = "claude-sonnet-4-6") -> dict:
        provider = AnthropicProvider(settings={"api_key": "test-key"})
        kwargs, extra_headers, _ = provider._build_request_kwargs(model, request)
        call_kwargs = dict(kwargs)
        if extra_headers:
            call_kwargs["extra_headers"] = extra_headers
        return call_kwargs

    def test_default_request_binds_to_real_create_signature(self):
        request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
        call_kwargs = self._call_kwargs(request)
        sig = inspect.signature(anthropic.resources.messages.messages.AsyncMessages.create)
        sig.bind(self=object(), **call_kwargs)

    def test_streaming_call_binds_to_real_stream_signature(self):
        request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
        call_kwargs = self._call_kwargs(request)
        sig = inspect.signature(anthropic.resources.messages.messages.AsyncMessages.stream)
        sig.bind(self=object(), **call_kwargs)

    def test_extended_thinking_request_binds_to_real_create_signature(self):
        request = LLMRequest(
            messages=[{"role": "user", "content": "hi"}],
            metadata={"api_kwargs": {"thinking_tokens": 8000}},
        )
        call_kwargs = self._call_kwargs(request, model="claude-opus-4-6")
        sig = inspect.signature(anthropic.resources.messages.messages.AsyncMessages.create)
        sig.bind(self=object(), **call_kwargs)
