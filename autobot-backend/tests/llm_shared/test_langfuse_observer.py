# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for LangFuseObserver (GH#9012)."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Minimal LLMRequest / LLMResponse stand-ins so tests don't need the full
# backend import chain.
# ---------------------------------------------------------------------------


@dataclass
class FakeRequest:
    request_id: str = "req-1"
    model_name: str = "gpt-4o"
    messages: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    llm_type: str = "general"


@dataclass
class FakeToolCall:
    name: str


@dataclass
class FakeResponse:
    request_id: str = "req-1"
    content: str = "hello"
    usage: dict = field(default_factory=dict)
    tool_calls: list = field(default_factory=list)
    finish_reason: str = "stop"
    provider: str = "openai"
    error: str | None = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_langfuse_module():
    """Patch the langfuse module so tests work without the real package."""
    fake_gen = MagicMock()
    fake_lf = MagicMock()
    fake_lf.generation.return_value = fake_gen

    with patch.dict("sys.modules", {"langfuse": MagicMock(Langfuse=MagicMock(return_value=fake_lf))}):
        yield fake_lf, fake_gen


@pytest.fixture()
def config():
    from llm_shared.observability.tracing_config import LangFuseTracingConfig

    return LangFuseTracingConfig(host="http://lf", public_key="pub", secret_key="sec")


@pytest.fixture()
def observer(mock_langfuse_module, config):
    from llm_shared.observability.langfuse_observer import LangFuseObserver

    return LangFuseObserver(config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLangFuseObserverOnRequest:
    @pytest.mark.asyncio
    async def test_creates_generation_and_stores_pending(self, observer, mock_langfuse_module):
        fake_lf, fake_gen = mock_langfuse_module
        req = FakeRequest(request_id="r1", metadata={"run_id": "run-x", "agent_id": "ag-1"})
        await observer.on_request(req, {})
        fake_lf.generation.assert_called_once()
        assert "r1" in observer._pending

    @pytest.mark.asyncio
    async def test_graceful_when_metadata_absent(self, observer, mock_langfuse_module):
        """No KeyError when agent_id / run_id absent from metadata."""
        req = FakeRequest(request_id="r2", metadata={})
        await observer.on_request(req, {})
        assert "r2" in observer._pending


class TestLangFuseObserverOnResponse:
    @pytest.mark.asyncio
    async def test_ends_generation_and_removes_pending(self, observer, mock_langfuse_module):
        fake_lf, fake_gen = mock_langfuse_module
        req = FakeRequest(request_id="r3")
        await observer.on_request(req, {})
        resp = FakeResponse(request_id="r3", usage={"prompt_tokens": 10, "completion_tokens": 5})
        await observer.on_response(resp, latency_ms=100.0, cost=0.001)
        fake_gen.end.assert_called_once()
        assert "r3" not in observer._pending

    @pytest.mark.asyncio
    async def test_no_op_when_no_pending(self, observer, mock_langfuse_module):
        _, fake_gen = mock_langfuse_module
        resp = FakeResponse(request_id="unknown")
        await observer.on_response(resp, latency_ms=50.0, cost=0.0)
        fake_gen.end.assert_not_called()

    @pytest.mark.asyncio
    async def test_level_error_on_response_error(self, observer, mock_langfuse_module):
        _, fake_gen = mock_langfuse_module
        req = FakeRequest(request_id="r4")
        await observer.on_request(req, {})
        resp = FakeResponse(request_id="r4", error="timeout")
        await observer.on_response(resp, latency_ms=0.0, cost=0.0)
        call_kwargs = fake_gen.end.call_args.kwargs
        assert call_kwargs.get("level") == "ERROR"


class TestLangFuseObserverOnError:
    @pytest.mark.asyncio
    async def test_ends_generation_with_error_level(self, observer, mock_langfuse_module):
        _, fake_gen = mock_langfuse_module
        req = FakeRequest(request_id="r5")
        await observer.on_request(req, {})
        await observer.on_error(ValueError("boom"), req)
        fake_gen.end.assert_called_once()
        call_kwargs = fake_gen.end.call_args.kwargs
        assert call_kwargs.get("level") == "ERROR"
        assert "r5" not in observer._pending

    @pytest.mark.asyncio
    async def test_no_op_when_no_pending(self, observer, mock_langfuse_module):
        _, fake_gen = mock_langfuse_module
        req = FakeRequest(request_id="gone")
        await observer.on_error(RuntimeError("x"), req)
        fake_gen.end.assert_not_called()


class TestLangFuseObserverOverflowEviction:
    @pytest.mark.asyncio
    async def test_evicts_oldest_when_over_1000(self, observer, mock_langfuse_module):
        fake_lf, _ = mock_langfuse_module
        # Pre-fill pending dict to exactly 1000 entries
        for i in range(1000):
            observer._pending[f"old-{i}"] = MagicMock()

        req = FakeRequest(request_id="new-entry")
        await observer.on_request(req, {})

        # oldest key evicted, new entry present
        assert "old-0" not in observer._pending
        assert "new-entry" in observer._pending
        # total stays at 1000 (evict one, add one)
        assert len(observer._pending) == 1000


class TestLangFuseObserverMissingPackage:
    def test_raises_runtime_error_when_langfuse_missing(self, config):
        with patch.dict("sys.modules", {"langfuse": None}):
            from llm_shared.observability.langfuse_observer import LangFuseObserver

            with pytest.raises(RuntimeError, match="langfuse package not installed"):
                LangFuseObserver(config)
