# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
import pytest

from circuit_breaker import CircuitBreakerOpenError
from content_reach.base import BackendError, ContentBackend, ContentRequest, ContentResult
from content_reach.chain import ContentSourceChain
from content_reach.registry import ContentSourceRegistry
from source_attribution import SourceType


class StubBackend(ContentBackend):
    def __init__(self, name, *, live=True, mode="ok"):
        self.name = name
        self.source_type = SourceType.WEB_SEARCH
        self._live = live
        self._mode = mode  # ok | fail_exc | fail_result
        self.fetch_calls = 0

    async def probe(self):
        return self._live

    async def fetch(self, request):
        self.fetch_calls += 1
        if self._mode == "fail_exc":
            raise BackendError("nope")
        if self._mode == "fail_result":
            return ContentResult.failure(self.source_type, "empty")
        if self._mode == "cb_open":
            raise CircuitBreakerOpenError("stub", 1, 0.0)
        return ContentResult(
            success=True,
            source_type=self.source_type,
            backend_used=self.name,
            text="ok-" + self.name,
        )


def _registry(*backends):
    reg = ContentSourceRegistry()
    reg.register_chain(
        ContentSourceChain(source="web_search", source_type=SourceType.WEB_SEARCH, backends=list(backends))
    )
    return reg


@pytest.mark.asyncio
async def test_first_success_wins():
    primary, fallback = StubBackend("a"), StubBackend("b")
    reg = _registry(primary, fallback)
    res = await reg.fetch("web_search", ContentRequest(query="q"))
    assert res.success and res.backend_used == "a"
    assert fallback.fetch_calls == 0


@pytest.mark.asyncio
async def test_falls_through_dead_probe():
    dead, alive = StubBackend("a", live=False), StubBackend("b")
    res = await _registry(dead, alive).fetch("web_search", ContentRequest(query="q"))
    assert res.success and res.backend_used == "b"
    assert dead.fetch_calls == 0


@pytest.mark.asyncio
async def test_falls_through_exception_then_result_failure():
    boom, empty, good = StubBackend("a", mode="fail_exc"), StubBackend("b", mode="fail_result"), StubBackend("c")
    res = await _registry(boom, empty, good).fetch("web_search", ContentRequest(query="q"))
    assert res.success and res.backend_used == "c"
    assert boom.fetch_calls == 1


@pytest.mark.asyncio
async def test_circuit_open_advances_without_cache_evict():
    cb, good = StubBackend("a", mode="cb_open"), StubBackend("b")
    reg = _registry(cb, good)
    res = await reg.fetch("web_search", ContentRequest(query="q"))
    assert res.success and res.backend_used == "b"
    assert cb.fetch_calls == 1  # it was attempted
    # CB-open is transient: the failed backend's probe cache entry is NOT evicted
    assert "a" in reg._probe_cache


@pytest.mark.asyncio
async def test_all_fail_returns_failure_result():
    res = await _registry(StubBackend("a", mode="fail_exc")).fetch("web_search", ContentRequest(query="q"))
    assert res.success is False
    assert res.source_type is SourceType.WEB_SEARCH
    assert "all backends failed" in res.metadata["error"]


@pytest.mark.asyncio
async def test_unknown_source_returns_failure():
    res = await ContentSourceRegistry().fetch("nope", ContentRequest(query="q"))
    assert res.success is False
    assert "unknown source" in res.metadata["error"]


@pytest.mark.asyncio
async def test_probe_result_is_cached(monkeypatch):
    b = StubBackend("a")
    calls = {"n": 0}
    orig = b.probe

    async def counting_probe():
        calls["n"] += 1
        return await orig()

    b.probe = counting_probe
    reg = _registry(b)
    await reg.fetch("web_search", ContentRequest(query="q"))
    await reg.fetch("web_search", ContentRequest(query="q"))
    assert calls["n"] == 1  # second fetch used the cache


@pytest.mark.asyncio
async def test_probe_all_lists_live_backends():
    reg = _registry(StubBackend("a"), StubBackend("b", live=False))
    live = await reg.probe_all()
    assert live == {"web_search": ["a"]}


def test_list_sources():
    reg = _registry(StubBackend("a"), StubBackend("b"))
    assert reg.list_sources() == {"web_search": ["a", "b"]}
