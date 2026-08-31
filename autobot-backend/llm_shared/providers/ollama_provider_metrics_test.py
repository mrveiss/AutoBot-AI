# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for the Ollama double-notify bug (#14211).

``BaseProvider.chat_completion`` is the one seam that should notify
``llm_shared.observability.registry`` (GH#6593). Before this fix,
``llm_shared/providers/ollama.py``'s inner delegate ALSO called
``obs_registry.notify_response``/``notify_error`` directly, on top of
``BaseProvider.chat_completion``'s own call — so every Ollama request would
have double-counted every LLM provider metric (``requests_total``,
``tokens_total``, the in-flight gauge, cost, latency samples) the moment
they were wired up.

A double-counted metric is the failure mode #14211 is really about: it looks
like traffic, not an error. Nothing goes red on its own — the dashboard
looks alive and the numbers are simply wrong. This asserts the notification
COUNT, not merely that it eventually fires, and drives the request through
``llm_shared.providers.ollama_provider.OllamaProvider`` — the real
``BaseProvider`` subclass production code dispatches to — with only the HTTP
transport faked, never the observer registry or recorder directly.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from llm_shared.models import LLMRequest
from llm_shared.observability import registry as obs_registry
from llm_shared.providers.ollama_provider import OllamaProvider


class _SpyObserver:
    """Counts notify_* calls rather than just recording that they happened —
    a double-notify regression is invisible to a spy that only checks
    "was on_response ever called"."""

    def __init__(self) -> None:
        self.request_calls = 0
        self.response_calls = 0
        self.error_calls = 0

    async def on_request(self, request, metadata: dict) -> None:
        self.request_calls += 1

    async def on_response(self, response, latency_ms: float, cost: float) -> None:
        self.response_calls += 1

    async def on_error(self, exc: Exception, request) -> None:
        self.error_calls += 1


@pytest.fixture(autouse=True)
def _isolated_registry():
    obs_registry.clear()
    yield
    obs_registry.clear()


def _canned_ollama_response() -> dict:
    return {
        "message": {"role": "assistant", "content": "hello from ollama"},
        "model": "llama3.1",
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }


async def _drive_one_request(spy: _SpyObserver):
    obs_registry.register(spy)

    provider = OllamaProvider({})
    delegate = provider._ensure_delegate()
    # #14211: the transport is what's faked — never notify_* or the recorder.
    # AsyncMock, not MagicMock: this callee is `async def`, and a sync mock
    # would never be awaited, silently testing nothing.
    delegate._execute_request = AsyncMock(return_value=_canned_ollama_response())

    request = LLMRequest(messages=[{"role": "user", "content": "hi"}], model_name="llama3.1")

    before = set(asyncio.all_tasks())
    response = await provider.chat_completion(request)
    # base_provider.py's notify_* calls are fire-and-forget (asyncio.create_task);
    # wait for anything still pending so the counts below are final.
    spawned = set(asyncio.all_tasks()) - before - {asyncio.current_task()}
    if spawned:
        await asyncio.wait_for(asyncio.gather(*spawned, return_exceptions=True), timeout=5.0)

    return response


class TestOllamaNotifiesExactlyOnce:
    """#14211 regression: the Ollama delegate must not notify a second time."""

    async def test_successful_request_notifies_exactly_once(self):
        spy = _SpyObserver()
        response = await _drive_one_request(spy)

        assert response.content == "hello from ollama"
        assert response.error is None

        assert spy.request_calls == 1, "notify_request must fire exactly once per request"
        assert spy.response_calls == 1, (
            "notify_response fired more than once — this is the #14211 double-notify "
            "regression: llm_shared/providers/ollama.py's delegate is calling "
            "obs_registry.notify_response a second time on top of "
            "BaseProvider.chat_completion's own call, which double-counts every LLM "
            "provider metric (requests_total, tokens_total, in-flight gauge, cost, "
            "latency) for every Ollama request."
        )
        assert spy.error_calls == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
