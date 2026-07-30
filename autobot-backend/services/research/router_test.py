# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for services.research.router (#12625).

Uses a REAL ``SearchProviderRegistry`` instance (not a mock of it) so these
tests exercise the registry's own credential-gating + graceful-fallback logic
end-to-end through the router, proving the design requirement ("Preserve the
registry's credential-gating + graceful fallback") rather than assuming it.
"""

from __future__ import annotations

import json
from typing import List, Optional
from unittest.mock import AsyncMock, patch

import agent_loop.search.registry  # noqa: F401 — force full (non-partial) module init, see orchestrator_test.py
from agent_loop.search.base import CATEGORY_GENERAL, SearchResult, WebSearchProvider
from agent_loop.search.config_declared_provider import ConfigDeclaredSearchProvider, load_source_definitions
from agent_loop.search.registry import SearchProviderRegistry
from services.research.router import infer_topic, route_search


class _FakeProvider(WebSearchProvider):
    """A minimal, in-test WebSearchProvider — no network, fully controllable."""

    def __init__(
        self,
        name: str,
        *,
        categories: tuple = (),
        available: bool = True,
        results: Optional[List[SearchResult]] = None,
        error: Optional[Exception] = None,
    ) -> None:
        super().__init__(settings={})
        self.provider_name = name
        self.supported_categories = categories
        self._available = available
        self._results = results or []
        self._error = error
        self.search_calls: List[str] = []

    async def is_available(self) -> bool:
        return self._available

    async def search(self, query: str, *, category: Optional[str] = None, count: int = 10) -> List[SearchResult]:
        self.search_calls.append(query)
        if self._error:
            raise self._error
        return self._results


def _registry(*providers: WebSearchProvider) -> SearchProviderRegistry:
    reg = SearchProviderRegistry()
    for provider in providers:
        reg.register(provider)
    return reg


class TestInferTopic:
    """Keyword-based inference (config/research_topics.yaml + built-in fallback)."""

    def test_academic_keyword_infers_academic_topic(self):
        assert infer_topic("What does this research paper conclude about gravity?") == "academic"

    def test_code_keyword_infers_code_topic(self):
        assert infer_topic("How do I use this library's function signature?") == "code"

    def test_news_keyword_infers_news_topic(self):
        assert infer_topic("What is today's breaking news on the election?") == "news"

    def test_unmatched_question_defaults_to_general(self):
        assert infer_topic("What color is the sky?") == CATEGORY_GENERAL


class TestRouteSearchPrefersSpecialist:
    """Acceptance: "fewer wasted general-web queries on specialized topics"."""

    async def test_specialized_provider_is_used_and_general_is_not_queried(self):
        specialist_results = [SearchResult(title="Paper", url="https://scholar.example/paper")]
        specialist = _FakeProvider("scholar", categories=("academic",), results=specialist_results)
        general = _FakeProvider("content_reach", results=[SearchResult(title="Web", url="https://web.example")])

        with patch("agent_loop.search.registry.get_search_registry", return_value=_registry(general, specialist)):
            results = await route_search("What does this research paper conclude?", count=5)

        assert [r.url for r in results] == ["https://scholar.example/paper"]
        assert specialist.search_calls == ["What does this research paper conclude?"]
        assert general.search_calls == []  # no wasted general-web query


class TestRouteSearchFallback:
    """Acceptance: default to general web when nothing matches; fallback preserved."""

    async def test_falls_back_to_general_web_when_no_specialist_registered(self):
        general = _FakeProvider("content_reach", results=[SearchResult(title="Web", url="https://web.example")])

        with patch("agent_loop.search.registry.get_search_registry", return_value=_registry(general)):
            results = await route_search("What does this research paper conclude?", count=5)

        assert [r.url for r in results] == ["https://web.example"]
        assert general.search_calls == ["What does this research paper conclude?"]

    async def test_credential_gated_specialist_unavailable_falls_back_gracefully(self):
        """A specialist that is registered but not credentialed (is_available=False)
        must never block the run — the registry's fallback chain takes over."""
        unavailable_specialist = _FakeProvider("scholar", categories=("academic",), available=False)
        general = _FakeProvider("content_reach", results=[SearchResult(title="Web", url="https://web.example")])

        with patch(
            "agent_loop.search.registry.get_search_registry",
            return_value=_registry(general, unavailable_specialist),
        ):
            results = await route_search("What does this research paper conclude?", count=5)

        assert [r.url for r in results] == ["https://web.example"]
        assert unavailable_specialist.search_calls == []  # never called — was skipped as unavailable

    async def test_specialist_error_falls_back_to_next_provider(self):
        """A specialist that errors mid-search must not sink the whole run (graceful fallback)."""
        erroring_specialist = _FakeProvider("scholar", categories=("academic",), error=RuntimeError("unreachable"))
        general = _FakeProvider("content_reach", results=[SearchResult(title="Web", url="https://web.example")])

        with patch(
            "agent_loop.search.registry.get_search_registry",
            return_value=_registry(general, erroring_specialist),
        ):
            results = await route_search("What does this research paper conclude?", count=5)

        assert [r.url for r in results] == ["https://web.example"]

    async def test_no_providers_registered_returns_empty_list(self):
        with patch("agent_loop.search.registry.get_search_registry", return_value=_registry()):
            results = await route_search("anything", count=5)
        assert results == []


class TestConfigDeclaredSourceEndToEndRouting:
    """Acceptance: "A new simple source can be added via config only (no Python),
    and the router picks it up" — proven end-to-end: YAML -> SourceDefinition ->
    ConfigDeclaredSearchProvider -> registered -> routed by topic, zero Python
    subclass authored for the source itself."""

    async def test_yaml_declared_source_is_routed_to_by_topic(self, tmp_path):
        config = tmp_path / "research_sources.yaml"
        config.write_text(
            "sources:\n"
            "  - name: docs_source\n"
            "    category: code\n"
            "    base_url: https://docs.example.com/search\n"
            "    query_param: q\n"
            "    result_path: results\n",
            encoding="utf-8",
        )
        definitions = load_source_definitions(str(config))
        assert len(definitions) == 1  # config-only source loaded, no Python class written for it

        config_source = ConfigDeclaredSearchProvider(definitions[0])
        general = _FakeProvider("content_reach", results=[SearchResult(title="Web", url="https://web.example")])
        payload = {"results": [{"title": "Docs", "url": "https://docs.example.com/x", "summary": "s"}]}

        with (
            patch("agent_loop.search.registry.get_search_registry", return_value=_registry(general, config_source)),
            patch("autobot_shared.url_safety.is_public_url_async", AsyncMock(return_value=True)),
            patch("autobot_shared.security.ssrf_guard.pinned_connector", AsyncMock(return_value=object())),
            patch("aiohttp.ClientSession") as fake_session_cls,
        ):
            fake_session_cls.return_value = _FakeAiohttpSession(200, json.dumps(payload).encode("utf-8"))
            results = await route_search("How do I use this library's function?", count=5)

        assert [r.url for r in results] == ["https://docs.example.com/x"]
        assert general.search_calls == []  # config-declared specialist satisfied it; no general-web fallback needed


class _FakeAiohttpContent:
    def __init__(self, body: bytes) -> None:
        self._body = body

    async def read(self, _n: int) -> bytes:
        return self._body


class _FakeAiohttpResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.content = _FakeAiohttpContent(body)

    async def __aenter__(self) -> "_FakeAiohttpResponse":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeAiohttpSession:
    def __init__(self, status: int, body: bytes) -> None:
        self._response = _FakeAiohttpResponse(status, body)

    def get(self, *_args, **_kwargs):
        return self._response

    async def __aenter__(self) -> "_FakeAiohttpSession":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False
