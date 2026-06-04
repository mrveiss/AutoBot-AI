# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for observer registry notification chain (GH#9012).

Verifies that the notification chain works end-to-end:
- notify_request() → observer.on_request()
- notify_response() → observer.on_response()
- notify_error() → observer.on_error()
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@dataclass
class FakeRequest:
    """Minimal request stand-in for integration tests."""

    request_id: str = "req-1"
    model_name: str = "gpt-4o"
    messages: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    llm_type: str = "general"


@dataclass
class FakeResponse:
    """Minimal response stand-in for integration tests."""

    request_id: str = "req-1"
    content: str = "hello"
    usage: dict = field(default_factory=dict)
    tool_calls: list = field(default_factory=list)
    finish_reason: str = "stop"
    provider: str = "openai"
    error: str | None = None


class SpyObserver:
    """Test spy that records which observer methods were called."""

    def __init__(self):
        self.on_request_calls = []
        self.on_response_calls = []
        self.on_error_calls = []

    async def on_request(self, request, metadata: dict) -> None:
        self.on_request_calls.append((request, metadata))

    async def on_response(self, response, latency_ms: float, cost: float) -> None:
        self.on_response_calls.append((response, latency_ms, cost))

    async def on_error(self, exc: Exception, request) -> None:
        self.on_error_calls.append((exc, request))


class FailingObserver:
    """Observer that always raises exceptions (used to test error isolation)."""

    async def on_request(self, request, metadata: dict) -> None:
        raise RuntimeError("on_request failed")

    async def on_response(self, response, latency_ms: float, cost: float) -> None:
        raise RuntimeError("on_response failed")

    async def on_error(self, exc: Exception, request) -> None:
        raise RuntimeError("on_error failed")


@pytest.fixture()
def registry():
    """Import and provide the observer registry module.

    Since autobot-backend/conftest.py stubs llm_shared for most tests,
    we need to import the real module here.
    """
    import importlib.util
    import sys
    from pathlib import Path

    # Remove any stub that might be in sys.modules
    for key in list(sys.modules.keys()):
        if key == "llm_shared" or key.startswith("llm_shared."):
            del sys.modules[key]

    # Load the real modules directly
    backend_root = Path(__file__).parent.parent.parent

    # Load llm_shared package
    llm_shared_path = backend_root / "llm_shared" / "__init__.py"
    spec = importlib.util.spec_from_file_location("llm_shared", llm_shared_path)
    llm_shared = importlib.util.module_from_spec(spec)
    sys.modules["llm_shared"] = llm_shared
    spec.loader.exec_module(llm_shared)

    # Now import observability (will use the real llm_shared)
    from llm_shared import observability

    # Clear before test
    observability.clear()
    yield observability
    # Clear after test
    observability.clear()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestObserverRegistryNotificationChain:
    """Test that notify_* methods actually invoke registered observers."""

    @pytest.mark.asyncio
    async def test_notify_request_calls_observer_on_request(self, registry):
        """Verify notify_request() → observer.on_request()."""
        spy = SpyObserver()
        registry.register(spy)

        req = FakeRequest(request_id="r1")
        metadata = {"run_id": "run-1"}

        await registry.notify_request(req, metadata)

        assert len(spy.on_request_calls) == 1
        assert spy.on_request_calls[0] == (req, metadata)
        # Other methods should not be called
        assert len(spy.on_response_calls) == 0
        assert len(spy.on_error_calls) == 0

    @pytest.mark.asyncio
    async def test_notify_response_calls_observer_on_response(self, registry):
        """Verify notify_response() → observer.on_response()."""
        spy = SpyObserver()
        registry.register(spy)

        resp = FakeResponse(request_id="r2", content="test response")
        latency_ms = 123.45
        cost = 0.0042

        await registry.notify_response(resp, latency_ms, cost)

        assert len(spy.on_response_calls) == 1
        assert spy.on_response_calls[0] == (resp, latency_ms, cost)
        # Other methods should not be called
        assert len(spy.on_request_calls) == 0
        assert len(spy.on_error_calls) == 0

    @pytest.mark.asyncio
    async def test_notify_error_calls_observer_on_error(self, registry):
        """Verify notify_error() → observer.on_error()."""
        spy = SpyObserver()
        registry.register(spy)

        req = FakeRequest(request_id="r3")
        exc = ValueError("test error")

        await registry.notify_error(exc, req)

        assert len(spy.on_error_calls) == 1
        assert spy.on_error_calls[0] == (exc, req)
        # Other methods should not be called
        assert len(spy.on_request_calls) == 0
        assert len(spy.on_response_calls) == 0


class TestMultipleObservers:
    """Test that all registered observers receive notifications."""

    @pytest.mark.asyncio
    async def test_all_observers_notified_on_request(self, registry):
        """Multiple observers registered, all get notified."""
        spy1 = SpyObserver()
        spy2 = SpyObserver()
        spy3 = SpyObserver()

        registry.register(spy1)
        registry.register(spy2)
        registry.register(spy3)

        req = FakeRequest(request_id="r4")
        metadata = {"test": "data"}

        await registry.notify_request(req, metadata)

        # All three spies should have been called
        assert len(spy1.on_request_calls) == 1
        assert len(spy2.on_request_calls) == 1
        assert len(spy3.on_request_calls) == 1

        # Verify they all got the same data
        assert spy1.on_request_calls[0] == (req, metadata)
        assert spy2.on_request_calls[0] == (req, metadata)
        assert spy3.on_request_calls[0] == (req, metadata)

    @pytest.mark.asyncio
    async def test_all_observers_notified_on_response(self, registry):
        """Multiple observers all receive response notifications."""
        spy1 = SpyObserver()
        spy2 = SpyObserver()

        registry.register(spy1)
        registry.register(spy2)

        resp = FakeResponse(request_id="r5")
        latency_ms = 100.0
        cost = 0.01

        await registry.notify_response(resp, latency_ms, cost)

        assert len(spy1.on_response_calls) == 1
        assert len(spy2.on_response_calls) == 1

    @pytest.mark.asyncio
    async def test_all_observers_notified_on_error(self, registry):
        """Multiple observers all receive error notifications."""
        spy1 = SpyObserver()
        spy2 = SpyObserver()

        registry.register(spy1)
        registry.register(spy2)

        req = FakeRequest(request_id="r6")
        exc = RuntimeError("test error")

        await registry.notify_error(exc, req)

        assert len(spy1.on_error_calls) == 1
        assert len(spy2.on_error_calls) == 1


class TestObserverExceptionIsolation:
    """Test that observer exceptions don't break the notification chain."""

    @pytest.mark.asyncio
    async def test_failing_observer_does_not_break_request_notification(self, registry):
        """Observer exception doesn't break notify_request()."""
        failing = FailingObserver()
        spy = SpyObserver()

        # Register failing observer first, then spy
        registry.register(failing)
        registry.register(spy)

        req = FakeRequest(request_id="r7")
        metadata = {"test": "resilient"}

        # Should not raise even though failing observer raises
        await registry.notify_request(req, metadata)

        # Spy should still have been called despite failing observer
        assert len(spy.on_request_calls) == 1
        assert spy.on_request_calls[0] == (req, metadata)

    @pytest.mark.asyncio
    async def test_failing_observer_does_not_break_response_notification(self, registry):
        """Observer exception doesn't break notify_response()."""
        failing = FailingObserver()
        spy = SpyObserver()

        registry.register(failing)
        registry.register(spy)

        resp = FakeResponse(request_id="r8")
        latency_ms = 50.0
        cost = 0.005

        # Should not raise
        await registry.notify_response(resp, latency_ms, cost)

        # Spy should still have been called
        assert len(spy.on_response_calls) == 1

    @pytest.mark.asyncio
    async def test_failing_observer_does_not_break_error_notification(self, registry):
        """Observer exception doesn't break notify_error()."""
        failing = FailingObserver()
        spy = SpyObserver()

        registry.register(failing)
        registry.register(spy)

        req = FakeRequest(request_id="r9")
        exc = ValueError("original error")

        # Should not raise even though failing observer raises
        await registry.notify_error(exc, req)

        # Spy should still have been called
        assert len(spy.on_error_calls) == 1
        assert spy.on_error_calls[0][0] == exc

    @pytest.mark.asyncio
    async def test_multiple_failing_observers_isolated(self, registry):
        """Multiple failing observers don't break the chain."""
        failing1 = FailingObserver()
        failing2 = FailingObserver()
        spy = SpyObserver()

        registry.register(failing1)
        registry.register(failing2)
        registry.register(spy)

        req = FakeRequest(request_id="r10")
        metadata = {}

        # Should not raise despite two failing observers
        await registry.notify_request(req, metadata)

        # Spy should still work
        assert len(spy.on_request_calls) == 1
