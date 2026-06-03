# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for LangSmithObserver (GH#9012)."""

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
class FakeResponse:
    request_id: str = "req-1"
    content: str = "hello"
    usage: dict = field(default_factory=dict)
    finish_reason: str = "stop"
    provider: str = "openai"
    error: str | None = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_langsmith_module():
    """Patch the langsmith module so tests work without the real package."""
    fake_client = MagicMock()
    fake_client.create_run = MagicMock()
    fake_client.update_run = MagicMock()

    with patch.dict(
        "sys.modules", {"langsmith": MagicMock(Client=MagicMock(return_value=fake_client))}
    ):
        yield fake_client


@pytest.fixture()
def config():
    from llm_shared.observability.tracing_config import LangSmithTracingConfig

    return LangSmithTracingConfig(api_url="http://ls", api_key="key-123", project="test-project")


@pytest.fixture()
def observer(mock_langsmith_module, config):
    from llm_shared.observability.langsmith_observer import LangSmithObserver

    return LangSmithObserver(config)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLangSmithObserverOnRequest:
    @pytest.mark.asyncio
    async def test_creates_run_and_stores_pending(self, observer, mock_langsmith_module):
        fake_client = mock_langsmith_module
        req = FakeRequest(
            request_id="r1",
            messages=[{"role": "user", "content": "test"}],
            metadata={"run_id": "run-x", "agent_id": "ag-1"},
        )
        await observer.on_request(req, {})
        fake_client.create_run.assert_called_once()
        call_kwargs = fake_client.create_run.call_args.kwargs
        assert call_kwargs["name"] == "llm.inference"
        assert call_kwargs["run_type"] == "llm"
        assert call_kwargs["project_name"] == "test-project"
        assert "r1" in observer._pending

    @pytest.mark.asyncio
    async def test_graceful_when_metadata_absent(self, observer, mock_langsmith_module):
        """No KeyError when agent_id / run_id absent from metadata."""
        req = FakeRequest(request_id="r2", metadata={})
        await observer.on_request(req, {})
        assert "r2" in observer._pending

    @pytest.mark.asyncio
    async def test_evicts_overflow_before_creating_run(self, observer, mock_langsmith_module):
        """Overflow eviction is called before creating a new run."""
        # Pre-fill pending dict to exactly 1001 entries
        for i in range(1001):
            observer._pending[f"old-{i}"] = f"run-{i}"

        req = FakeRequest(request_id="new-entry")
        await observer.on_request(req, {})

        # oldest key evicted, new entry present
        assert "old-0" not in observer._pending
        assert "new-entry" in observer._pending
        # total stays at 1001 (evict one, add one)
        assert len(observer._pending) == 1001


class TestLangSmithObserverOnResponse:
    @pytest.mark.asyncio
    async def test_updates_run_and_removes_pending(self, observer, mock_langsmith_module):
        fake_client = mock_langsmith_module
        req = FakeRequest(request_id="r3")
        await observer.on_request(req, {})
        resp = FakeResponse(request_id="r3", usage={"prompt_tokens": 10, "completion_tokens": 5})
        await observer.on_response(resp, latency_ms=100.0, cost=0.001)

        fake_client.update_run.assert_called_once()
        call_args = fake_client.update_run.call_args
        run_id = call_args[0][0]
        assert run_id is not None
        assert call_args.kwargs["outputs"] == {"content": "hello"}
        assert "r3" not in observer._pending

    @pytest.mark.asyncio
    async def test_no_op_when_no_pending(self, observer, mock_langsmith_module):
        fake_client = mock_langsmith_module
        resp = FakeResponse(request_id="unknown")
        await observer.on_response(resp, latency_ms=50.0, cost=0.0)
        fake_client.update_run.assert_not_called()


class TestLangSmithObserverOnError:
    @pytest.mark.asyncio
    async def test_updates_run_with_error(self, observer, mock_langsmith_module):
        fake_client = mock_langsmith_module
        req = FakeRequest(request_id="r5")
        await observer.on_request(req, {})
        await observer.on_error(ValueError("boom"), req)

        fake_client.update_run.assert_called_once()
        call_args = fake_client.update_run.call_args
        run_id = call_args[0][0]
        assert run_id is not None
        assert call_args.kwargs["error"] == "boom"
        assert "r5" not in observer._pending

    @pytest.mark.asyncio
    async def test_no_op_when_no_pending(self, observer, mock_langsmith_module):
        fake_client = mock_langsmith_module
        req = FakeRequest(request_id="gone")
        await observer.on_error(RuntimeError("x"), req)
        fake_client.update_run.assert_not_called()


class TestLangSmithObserverOverflowEviction:
    @pytest.mark.asyncio
    async def test_evicts_oldest_when_over_1000(self, observer, mock_langsmith_module):
        """When _pending exceeds 1000, oldest entry is evicted."""
        # Pre-fill pending dict to exactly 1000 entries
        for i in range(1000):
            observer._pending[f"old-{i}"] = f"run-{i}"

        req = FakeRequest(request_id="new-entry")
        await observer.on_request(req, {})

        # oldest key evicted, new entry present
        assert "old-0" not in observer._pending
        assert "new-entry" in observer._pending
        # total stays at 1000 (evict one, add one)
        assert len(observer._pending) == 1000

    @pytest.mark.asyncio
    async def test_no_eviction_when_under_threshold(self, observer, mock_langsmith_module):
        """No eviction occurs when _pending is under 1000."""
        # Add 500 entries
        for i in range(500):
            observer._pending[f"req-{i}"] = f"run-{i}"

        req = FakeRequest(request_id="new-entry")
        await observer.on_request(req, {})

        # All entries should still be present
        assert "req-0" in observer._pending
        assert "new-entry" in observer._pending
        assert len(observer._pending) == 501


class TestLangSmithObserverMissingPackage:
    def test_raises_runtime_error_when_langsmith_missing(self, config):
        """Observer raises RuntimeError when langsmith package is not installed."""
        with patch.dict("sys.modules", {"langsmith": None}):
            from llm_shared.observability.langsmith_observer import LangSmithObserver

            with pytest.raises(RuntimeError, match="langsmith package not installed"):
                LangSmithObserver(config)


class TestLangSmithObserverFlush:
    def test_flush_is_noop(self, observer):
        """flush() is a no-op since langsmith client auto-flushes."""
        # Should not raise
        observer.flush()
