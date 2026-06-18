# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Registry selection + graceful-fallback tests (#9022/#9023)."""

from __future__ import annotations

from typing import List, Optional

import pytest

from agent_loop.search.base import SearchResult, WebSearchProvider
from agent_loop.search.registry import SearchProviderRegistry


class _StubProvider(WebSearchProvider):
    """Configurable stub: available flag, fixed results, or raises."""

    def __init__(self, name: str, *, available: bool = True, results=None, raises: bool = False) -> None:
        super().__init__()
        self.provider_name = name
        self._available = available
        self._results = results if results is not None else []
        self._raises = raises
        self.search_calls = 0

    async def is_available(self) -> bool:
        return self._available

    async def search(self, query: str, *, category: Optional[str] = None, count: int = 10) -> List[SearchResult]:
        self.search_calls += 1
        if self._raises:
            raise RuntimeError(f"{self.provider_name} boom")
        return list(self._results)


def _result(url: str) -> SearchResult:
    return SearchResult(title=url, url=url, snippet="s")


@pytest.mark.asyncio
async def test_empty_registry_returns_no_results():
    registry = SearchProviderRegistry()
    assert await registry.search("q") == []


@pytest.mark.asyncio
async def test_preferred_provider_selected():
    primary = _StubProvider("brave", results=[_result("https://b/1")])
    secondary = _StubProvider("searxng", results=[_result("https://s/1")])
    registry = SearchProviderRegistry()
    registry.register(primary)
    registry.register(secondary)

    results = await registry.search("q", provider="searxng")

    assert results[0].url == "https://s/1"
    assert secondary.search_calls == 1
    assert primary.search_calls == 0


@pytest.mark.asyncio
async def test_fallback_on_provider_error():
    failing = _StubProvider("brave", raises=True)
    backup = _StubProvider("searxng", results=[_result("https://s/1")])
    registry = SearchProviderRegistry()
    registry.register(failing)
    registry.register(backup)

    results = await registry.search("q")

    assert results[0].url == "https://s/1"
    assert failing.search_calls == 1
    assert backup.search_calls == 1


@pytest.mark.asyncio
async def test_unavailable_provider_skipped():
    off = _StubProvider("brave", available=False, results=[_result("https://b/1")])
    on = _StubProvider("searxng", results=[_result("https://s/1")])
    registry = SearchProviderRegistry()
    registry.register(off)
    registry.register(on)

    results = await registry.search("q")

    assert results[0].url == "https://s/1"
    assert off.search_calls == 0


@pytest.mark.asyncio
async def test_all_fail_returns_empty():
    a = _StubProvider("brave", raises=True)
    b = _StubProvider("searxng", raises=True)
    registry = SearchProviderRegistry()
    registry.register(a)
    registry.register(b)

    assert await registry.search("q") == []


def test_register_dedupes_fallback_chain():
    registry = SearchProviderRegistry()
    registry.register(_StubProvider("brave"))
    registry.register(_StubProvider("brave"))
    assert registry.list_providers() == ["brave"]
