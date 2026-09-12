# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the BaseProvider per-provider concurrency cap (GH#16527).

``ProviderConfig.max_concurrent_requests`` / ``LLMSettings.max_concurrent_requests``
was a real config field nothing read. ``BaseProvider.__init__`` now sizes an
``asyncio.Semaphore`` from it (settings-dict override, else the documented
config default) and ``chat_completion`` acquires it around the real request —
a burst past the cap queues on the semaphore rather than running unbounded.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, List

from .base_provider import BaseProvider
from .models import LLMRequest, LLMResponse, LLMSettings


def _request() -> LLMRequest:
    return LLMRequest(messages=[{"role": "user", "content": "hi"}])


class _GatedProvider(BaseProvider):
    """``_chat_completion_impl`` blocks on a shared gate until released, so a
    test can observe exactly how many calls are in flight at once."""

    def __init__(self, name: str, settings: dict | None = None) -> None:
        super().__init__(settings or {})
        self.provider_name = name
        self.in_flight = 0
        self.peak_in_flight = 0
        self.release = asyncio.Event()

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        await self.release.wait()
        self.in_flight -= 1
        return LLMResponse(content="ok", provider=self.provider_name)

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        yield ""

    async def is_available(self) -> bool:
        return True

    async def list_models(self) -> List[str]:
        return []


class TestConcurrencyCapConfig:
    def test_default_cap_comes_from_documented_config(self):
        """No settings override → LLMSettings.max_concurrent_requests (env
        LLM_MAX_CONCURRENT, default ModelConfig.DEFAULT_MAX_CONCURRENT_REQUESTS)."""
        provider = _GatedProvider("cctest-default")
        expected = LLMSettings().max_concurrent_requests
        assert provider._concurrency_semaphore._value == expected

    def test_per_instance_override_via_settings(self):
        provider = _GatedProvider("cctest-override", settings={"max_concurrent_requests": 3})
        assert provider._concurrency_semaphore._value == 3

    def test_each_provider_instance_gets_its_own_semaphore(self):
        """Per-provider, not global — one provider's cap cannot starve another's."""
        a = _GatedProvider("cctest-a", settings={"max_concurrent_requests": 1})
        b = _GatedProvider("cctest-b", settings={"max_concurrent_requests": 5})
        assert a._concurrency_semaphore is not b._concurrency_semaphore
        assert a._concurrency_semaphore._value != b._concurrency_semaphore._value


class TestConcurrencyCapEnforcement:
    async def test_burst_past_cap_queues_rather_than_running_unbounded(self):
        """4 concurrent requests against a cap of 2: only 2 ever reach the
        provider implementation at once — the rest queue on the semaphore."""
        provider = _GatedProvider("cctest-burst", settings={"max_concurrent_requests": 2})

        tasks = [asyncio.create_task(provider.chat_completion(_request())) for _ in range(4)]
        # Let the loop advance every task up to the gate inside _chat_completion_impl.
        await asyncio.sleep(0.05)
        assert provider.peak_in_flight == 2

        provider.release.set()
        responses = await asyncio.gather(*tasks)
        # Queued, not rejected: every request still completes successfully once
        # capacity frees up.
        assert all(r.error is None and r.content == "ok" for r in responses)

    async def test_cap_of_one_serializes_requests(self):
        provider = _GatedProvider("cctest-serial", settings={"max_concurrent_requests": 1})

        tasks = [asyncio.create_task(provider.chat_completion(_request())) for _ in range(3)]
        await asyncio.sleep(0.05)
        assert provider.peak_in_flight == 1

        provider.release.set()
        responses = await asyncio.gather(*tasks)
        assert len(responses) == 3
        assert all(r.error is None for r in responses)
