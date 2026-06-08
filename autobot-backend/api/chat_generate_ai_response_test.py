# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

    result = await _generate_ai_response(
        llm_service=llm_service,
        llm_context=[{"role": "user", "content": "hi"}],
        session_id="s-123",
        request_id="r-abc",
    )

    assert result == {"content": "Hello, world!", "role": "assistant"}
    # Pin the call shape — confirms migrated args reach LLMService.chat correctly.
    llm_service.chat.assert_awaited_once_with(
        messages=[{"role": "user", "content": "hi"}],
        conversation_id="s-123",
        request_id="r-abc",
    )


@pytest.mark.asyncio
async def test_generate_ai_response_falls_back_when_llm_returns_error(make_llm_response: Any) -> None:
    """LLMResponse.error truthy → user-friendly fallback message."""
    from api.chat import _generate_ai_response

    llm_service = AsyncMock()
    llm_service.chat = AsyncMock(return_value=make_llm_response(content="", error="rate limit exceeded"))

    result = await _generate_ai_response(
        llm_service=llm_service,
        llm_context=[{"role": "user", "content": "hi"}],
        session_id="s-1",
        request_id="r-1",
    )

    assert result["role"] == "assistant"
    # Must NOT leak the underlying error message to the user — fallback string only.
    assert "I encountered an error" in result["content"]
    assert "rate limit" not in result["content"]


@pytest.mark.asyncio
async def test_generate_ai_response_falls_back_when_chat_raises(make_llm_response: Any) -> None:
    """Network/runtime exception in chat() → user-friendly fallback."""
    from api.chat import _generate_ai_response

    llm_service = AsyncMock()
    llm_service.chat = AsyncMock(side_effect=RuntimeError("boom"))

    result = await _generate_ai_response(
        llm_service=llm_service,
        llm_context=[{"role": "user", "content": "hi"}],
        session_id="s-1",
        request_id="r-1",
    )

    assert result["role"] == "assistant"
    assert "I encountered an error" in result["content"]
    # Underlying exception detail must not surface in user-facing string.
    assert "boom" not in result["content"]


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

    result = await _generate_ai_response(
        llm_service=llm_service,
        llm_context=[{"role": "user", "content": "hi"}],
        session_id="s-1",
        request_id="r-1",
    )

    assert result["content"] == "ok"
    llm_service.generate_response.assert_not_awaited()
    llm_service.chat.assert_awaited_once()


def test_get_llm_service_imports_canonical_module_path() -> None:
    """Regression pin: the lazy import inside ``get_llm_service`` must
    resolve to ``services.llm_service.LLMService`` (the canonical post-#3185
    location), not a non-existent top-level ``llm_service`` module.
    """
    import inspect

    from api import chat

    src = inspect.getsource(chat.get_llm_service)
    assert "from services.llm_service import LLMService" in src, (
        "get_llm_service must import from services.llm_service "
        "(canonical post-#3185 path); the older 'from llm_service import' "
        "raises ModuleNotFoundError at first call."
    )
