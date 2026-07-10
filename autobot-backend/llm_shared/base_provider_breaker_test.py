# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the BaseProvider completion circuit breaker (GH#11488).

``_chat_completion_impl`` must not raise (errors travel via
``LLMResponse.error``), so breaker accounting happens in
``BaseProvider._guarded_completion``: error responses count as failures,
rate-limit errors are exempt (owned by the GH#8502 backoff handler), and an
open breaker fails fast without invoking the provider.
"""

import re
from pathlib import Path
from typing import AsyncIterator, List

from constants import CircuitBreakerDefaults

from .base_provider import BaseProvider
from .models import LLMRequest, LLMResponse


def _request() -> LLMRequest:
    return LLMRequest(messages=[{"role": "user", "content": "hi"}])


class _ScriptedProvider(BaseProvider):
    """Provider whose _chat_completion_impl replays a scripted response list."""

    def __init__(self, name: str, responses: List[LLMResponse]) -> None:
        super().__init__({})
        self.provider_name = name
        self._responses = list(responses)
        self.impl_calls = 0

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        self.impl_calls += 1
        return self._responses.pop(0)

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        yield ""

    async def is_available(self) -> bool:
        return True

    async def list_models(self) -> List[str]:
        return []


def _ok(provider: str) -> LLMResponse:
    return LLMResponse(content="ok", provider=provider)


def _err(provider: str, error: str = "connection refused") -> LLMResponse:
    return LLMResponse(content="", provider=provider, error=error)


class TestGuardedCompletion:
    """Breaker accounting through _guarded_completion."""

    async def test_success_passes_through(self):
        provider = _ScriptedProvider("cbtest-success", [_ok("cbtest-success")])
        response = await provider._guarded_completion(_request())
        assert response.error is None
        assert response.content == "ok"
        assert provider.impl_calls == 1

    async def test_error_responses_open_breaker_and_fail_fast(self):
        threshold = CircuitBreakerDefaults.LLM_FAILURE_THRESHOLD
        provider = _ScriptedProvider(
            "cbtest-open",
            [_err("cbtest-open")] * threshold + [_ok("cbtest-open")],
        )

        for _ in range(threshold):
            response = await provider._guarded_completion(_request())
            assert response.error == "connection refused"  # original error preserved

        # Breaker is now open: fail fast, provider impl NOT invoked.
        blocked = await provider._guarded_completion(_request())
        assert blocked.error is not None
        assert "circuit breaker open" in blocked.error
        assert provider.impl_calls == threshold

    async def test_rate_limit_errors_do_not_trip_breaker(self):
        threshold = CircuitBreakerDefaults.LLM_FAILURE_THRESHOLD
        rate_limited = [_err("cbtest-ratelimit", "HTTP 429: rate limit exceeded")] * (threshold + 1)
        provider = _ScriptedProvider("cbtest-ratelimit", rate_limited + [_ok("cbtest-ratelimit")])

        for _ in range(threshold + 1):
            response = await provider._guarded_completion(_request())
            assert "rate limit" in response.error

        # Still closed: the next call reaches the provider implementation.
        response = await provider._guarded_completion(_request())
        assert response.error is None
        assert provider.impl_calls == threshold + 2

    async def test_success_resets_failure_count(self):
        threshold = CircuitBreakerDefaults.LLM_FAILURE_THRESHOLD
        script = [_err("cbtest-reset")] * (threshold - 1) + [_ok("cbtest-reset")] + [_err("cbtest-reset")]
        provider = _ScriptedProvider("cbtest-reset", script)

        for _ in range(len(script)):
            await provider._guarded_completion(_request())

        # threshold-1 failures, a success, then one failure — breaker never opened.
        assert provider.impl_calls == len(script)


class TestNoMethodLevelBreaker:
    """GH#11488: ``_chat_completion_impl`` must not carry a breaker decorator.

    The method returns errors via ``LLMResponse.error`` instead of raising, so
    a method-level ``@circuit_breaker_async`` never records real failures —
    and now it would double-wrap ``BaseProvider._guarded_completion``.
    """

    def test_no_breaker_decorator_on_chat_completion_impl(self):
        providers_dir = Path(__file__).parent / "providers"
        pattern = re.compile(r"@circuit_breaker_async[\s\S]{0,300}?async def _chat_completion_impl")
        offenders = [
            path.name
            for path in sorted(providers_dir.glob("*.py"))
            if pattern.search(path.read_text(encoding="utf-8"))
        ]
        assert not offenders, f"method-level breaker on _chat_completion_impl in: {offenders}"
