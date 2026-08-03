# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Contract tests for ``api.chat._generate_ai_response`` (#7047).

Two regressions shipped silently in the same helper after the #3185
LLMInterface retirement:

  1. ``api/chat.py:106`` imported from a non-existent ``llm_service`` module
     (canonical path is ``services.llm_service``); function-scoped, so it
     fired only on first call.

  2. ``api/chat.py:543`` had ``hasattr(llm_service, "generate_response")``
     guarding a method that LLMService never exposed. The else-branch ran
     for every chat request — users got a canned "I'm currently unable
     to generate a response" string instead of the model's reply.

These tests pin the migrated shape so the same class of drift can't
recur silently.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from tests.fixtures import make_llm_response as _make_llm_response_factory


@pytest.fixture
def make_llm_response():
    """Canonical LLMResponse factory (#7134) — wraps the shared
    ``tests.fixtures.make_llm_response`` so each test reads the same shape.
    """
    return _make_llm_response_factory


@pytest.mark.asyncio
async def test_generate_ai_response_returns_model_content_on_success(make_llm_response: Any) -> None:
    """Happy path: LLMResponse.content surfaces in the result dict."""
    from api.chat import _generate_ai_response

    llm_service = AsyncMock()
    llm_service.chat = AsyncMock(return_value=make_llm_response(content="Hello, world!", error=None))

    ai_response, llm_response = await _generate_ai_response(
        llm_service=llm_service,
        llm_context=[{"role": "user", "content": "hi"}],
        session_id="s-123",
        request_id="r-abc",
    )

    # #9043: helper returns (dict, LLMResponse) for token tracking.
    assert ai_response == {"content": "Hello, world!", "role": "assistant"}
    assert llm_response is not None
    # Pin the call shape — confirms migrated args reach LLMService.chat correctly.
    # #11585: model_name/provider_name default to None (no per-request override).
    llm_service.chat.assert_awaited_once_with(
        messages=[{"role": "user", "content": "hi"}],
        conversation_id="s-123",
        provider_name=None,
        model_name=None,
        request_id="r-abc",
    )


@pytest.mark.asyncio
async def test_generate_ai_response_falls_back_when_llm_returns_error(make_llm_response: Any) -> None:
    """LLMResponse.error truthy → user-friendly fallback message."""
    from api.chat import _generate_ai_response

    llm_service = AsyncMock()
    llm_service.chat = AsyncMock(return_value=make_llm_response(content="", error="rate limit exceeded"))

    ai_response, llm_response = await _generate_ai_response(
        llm_service=llm_service,
        llm_context=[{"role": "user", "content": "hi"}],
        session_id="s-1",
        request_id="r-1",
    )

    assert ai_response["role"] == "assistant"
    assert llm_response is None
    # Must NOT leak the underlying error message to the user — fallback string only.
    assert "I encountered an error" in ai_response["content"]
    assert "rate limit" not in ai_response["content"]


@pytest.mark.asyncio
async def test_generate_ai_response_falls_back_when_chat_raises(make_llm_response: Any) -> None:
    """Network/runtime exception in chat() → user-friendly fallback."""
    from api.chat import _generate_ai_response

    llm_service = AsyncMock()
    llm_service.chat = AsyncMock(side_effect=RuntimeError("boom"))

    ai_response, llm_response = await _generate_ai_response(
        llm_service=llm_service,
        llm_context=[{"role": "user", "content": "hi"}],
        session_id="s-1",
        request_id="r-1",
    )

    assert ai_response["role"] == "assistant"
    assert llm_response is None
    assert "I encountered an error" in ai_response["content"]
    # Underlying exception detail must not surface in user-facing string.
    assert "boom" not in ai_response["content"]


@pytest.mark.asyncio
async def test_generate_ai_response_does_not_call_legacy_generate_response(make_llm_response: Any) -> None:
    """Regression pin: post-#3185 the helper must call .chat(), never
    .generate_response() (which was the deleted LLMInterface method).
    Catches the original #7047 silent-fallback bug if reintroduced.
    """
    from api.chat import _generate_ai_response

    llm_service = AsyncMock()
    llm_service.chat = AsyncMock(return_value=make_llm_response(content="ok", error=None))
    # If a future caller hits this attribute, the test fails — locks the migration.
    llm_service.generate_response = AsyncMock(side_effect=AssertionError("legacy method"))

    ai_response, _llm_response = await _generate_ai_response(
        llm_service=llm_service,
        llm_context=[{"role": "user", "content": "hi"}],
        session_id="s-1",
        request_id="r-1",
    )

    assert ai_response["content"] == "ok"
    llm_service.generate_response.assert_not_awaited()
    llm_service.chat.assert_awaited_once()


class TestGetLlmServiceResolvesTheCanonicalModule:
    """#7047's first defect: a function-scoped ``from llm_service import ...``
    naming a module that does not exist, so it raised ModuleNotFoundError on
    the first chat request rather than at import time.

    This used to assert the import *statement* appeared in
    ``inspect.getsource(get_llm_service)`` (#13311) -- which passes when the
    literal sits in a dead branch and fails on any refactor that moves it.
    Swapping the module in ``sys.modules`` and observing which class the
    accessor constructs proves the lookup actually happens, and where.
    """

    @pytest.fixture
    def canonical_module(self, monkeypatch):
        """Install a sentinel at the canonical path and yield its class."""
        sentinel_cls = type("SentinelLLMService", (), {})
        module = types.ModuleType("services.llm_service")
        module.LLMService = sentinel_cls
        monkeypatch.setitem(sys.modules, "services.llm_service", module)
        return sentinel_cls

    @staticmethod
    def _request():
        return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    def test_constructs_the_class_from_services_llm_service(self, canonical_module) -> None:
        from api.chat import get_llm_service

        service = get_llm_service(self._request())

        assert isinstance(service, canonical_module), (
            "get_llm_service resolved something other than "
            "services.llm_service.LLMService -- the canonical post-#3185 path"
        )

    def test_result_is_cached_on_app_state(self, canonical_module) -> None:
        """Lazy init is what let the broken import fire late; the caching half
        of that contract still has to hold."""
        from api.chat import get_llm_service

        request = self._request()
        first = get_llm_service(request)
        second = get_llm_service(request)

        assert first is second
        assert request.app.state.llm_service is first

    def test_the_legacy_module_name_does_not_exist(self) -> None:
        """The bug shape only worked if a top-level ``llm_service`` existed.

        Asserting it does not is what makes the reintroduced import fatal --
        and fatal at the seam this test drives, not somewhere in production.
        """
        import importlib

        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("llm_service")

    def test_a_broken_import_surfaces_rather_than_silently_returning_none(self, monkeypatch) -> None:
        """``lazy_init_singleton`` swallows factory exceptions and returns None.

        That is exactly how #7047 stayed invisible, so pin the observable:
        a caller must be able to tell resolution failed.
        """
        from api.chat import get_llm_service

        broken = types.ModuleType("services.llm_service")

        def _explode(*_args, **_kwargs):
            raise ModuleNotFoundError("No module named 'llm_service'")

        broken.LLMService = _explode
        monkeypatch.setitem(sys.modules, "services.llm_service", broken)

        assert get_llm_service(self._request()) is None
