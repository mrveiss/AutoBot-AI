# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit + SSRF-hostile-path tests for ConfigDeclaredSearchProvider (#12625).

The DNS-mocking technique (patching ``autobot_shared.url_safety.socket.getaddrinfo``)
mirrors ``api/tests/test_provider_auth_ssrf.py`` — ``asyncio``'s default
``loop.getaddrinfo`` runs the very same ``socket.getaddrinfo`` in an executor,
so this exercises the REAL ``ssrf_guard.pinned_connector`` / ``resolve_safe_ip``
guard rather than mocking it away.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from agent_loop.search.config_declared_provider import (
    ConfigDeclaredSearchProvider,
    SourceDefinition,
    _validate_definition,
    load_source_definitions,
)


def _definition(**overrides) -> SourceDefinition:
    base = dict(
        name="test_source",
        category="academic",
        base_url="https://docs.example.com/api/search",
        query_param="q",
        extra_params={"format": "json"},
        result_path="results",
        title_field="title",
        url_field="url",
        snippet_field="summary",
    )
    base.update(overrides)
    return SourceDefinition(**base)


class _FakeContent:
    def __init__(self, body: bytes) -> None:
        self._body = body

    async def read(self, _n: int) -> bytes:
        return self._body


class _FakeResponse:
    def __init__(self, status: int, body: bytes = b"", headers: dict | None = None) -> None:
        self.status = status
        self.content = _FakeContent(body)
        self.headers = headers or {}

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeSession:
    """Records the exact get(url, params=...) call shape for SSRF assertions."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.captured_url: str | None = None
        self.captured_kwargs: dict | None = None

    def get(self, url: str, **kwargs):
        self.captured_url = url
        self.captured_kwargs = kwargs
        return self._response

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


def _fake_connector():
    return object()


class TestSourceDefinitionLoading:
    """Data-driven loading (#12625 acceptance: "add a source via config only")."""

    def test_load_source_definitions_missing_file_returns_empty(self, tmp_path):
        assert load_source_definitions(str(tmp_path / "nope.yaml")) == []

    def test_load_source_definitions_parses_valid_entry(self, tmp_path):
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
        defs = load_source_definitions(str(config))
        assert len(defs) == 1
        assert defs[0].name == "docs_source"
        assert defs[0].category == "code"

    @pytest.mark.parametrize(
        "raw",
        [
            {"name": "", "category": "code", "base_url": "https://x.example/a", "query_param": "q"},
            {"name": "x", "category": "", "base_url": "https://x.example/a", "query_param": "q"},
            {"name": "x", "category": "code", "base_url": "", "query_param": "q"},
            {"name": "x", "category": "code", "base_url": "https://x.example/a", "query_param": ""},
            {"name": "x", "category": "code", "base_url": "ftp://x.example/a", "query_param": "q"},
            {"name": "x", "category": "code", "base_url": "not-a-url", "query_param": "q"},
        ],
    )
    def test_validate_definition_rejects_malformed_or_unsafe_entries(self, raw):
        assert _validate_definition(raw) is None


class TestConfigDeclaredProviderRequestSafety:
    """Requests never string-interpolate the runtime query into the URL (#12625)."""

    async def test_search_passes_query_only_through_params_never_the_url(self):
        """A query crafted to look like a host/scheme change must stay a params value."""
        hostile_query = "http://evil.example.com/@docs.example.com"
        response = _FakeResponse(200, json.dumps({"results": []}).encode("utf-8"))
        session = _FakeSession(response)

        with (
            patch("autobot_shared.security.ssrf_guard.pinned_connector", AsyncMock(return_value=_fake_connector())),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            provider = ConfigDeclaredSearchProvider(_definition())
            await provider.search(hostile_query, count=5)

        # The outbound request target is ALWAYS the declared base_url — the
        # hostile value can only ever land inside params, never the URL itself.
        assert session.captured_url == "https://docs.example.com/api/search"
        assert session.captured_kwargs["params"]["q"] == hostile_query
        assert session.captured_kwargs["allow_redirects"] is False

    async def test_search_rejects_redirect_response_without_following_it(self):
        """A 3xx response (e.g. redirecting to an internal address) must be rejected outright."""
        response = _FakeResponse(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})
        session = _FakeSession(response)

        with (
            patch("autobot_shared.security.ssrf_guard.pinned_connector", AsyncMock(return_value=_fake_connector())),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            provider = ConfigDeclaredSearchProvider(_definition())
            with pytest.raises(RuntimeError, match="redirect"):
                await provider.search("q", count=5)

    async def test_search_parses_declarative_result_path_and_fields(self):
        payload = {
            "results": [
                {"title": "Doc A", "url": "https://docs.example.com/a", "summary": "About A"},
                {"title": "Doc B", "url": "https://docs.example.com/b", "summary": "About B"},
            ]
        }
        response = _FakeResponse(200, json.dumps(payload).encode("utf-8"))
        session = _FakeSession(response)

        with (
            patch("autobot_shared.security.ssrf_guard.pinned_connector", AsyncMock(return_value=_fake_connector())),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            provider = ConfigDeclaredSearchProvider(_definition())
            results = await provider.search("q", count=5)

        assert [r.url for r in results] == ["https://docs.example.com/a", "https://docs.example.com/b"]
        assert results[0].title == "Doc A"
        assert results[0].snippet == "About A"
        assert results[0].source == "test_source"


class TestConfigDeclaredProviderSSRFHostileCases:
    """Hostile base_url cases — real ssrf_guard/url_safety DNS resolution, not mocked away."""

    async def test_is_available_false_for_internal_ip_base_url(self):
        provider = ConfigDeclaredSearchProvider(_definition(base_url="http://10.0.0.5/search"))
        assert await provider.is_available() is False

    async def test_is_available_false_for_localhost_base_url(self):
        provider = ConfigDeclaredSearchProvider(_definition(base_url="http://localhost:8080/search"))
        assert await provider.is_available() is False

    async def test_is_available_false_for_link_local_metadata_base_url(self):
        provider = ConfigDeclaredSearchProvider(_definition(base_url="http://169.254.169.254/search"))
        assert await provider.is_available() is False

    async def test_search_raises_when_base_url_resolves_to_private_address(self):
        """DNS-rebind case: a benign-looking hostname resolves to a private IP at request time."""
        fake_infos = [(2, 1, 6, "", ("10.0.0.9", 0))]
        provider = ConfigDeclaredSearchProvider(_definition(base_url="https://rebind.example.com/search"))

        with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
            with pytest.raises(RuntimeError, match="SSRF guard"):
                await provider.search("q", count=5)

    async def test_search_raises_when_base_url_resolves_to_loopback(self):
        fake_infos = [(2, 1, 6, "", ("127.0.0.1", 0))]
        provider = ConfigDeclaredSearchProvider(_definition(base_url="https://sneaky.example.com/search"))

        with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
            with pytest.raises(RuntimeError, match="SSRF guard"):
                await provider.search("q", count=5)

    async def test_search_raises_when_base_url_resolves_to_metadata_address(self):
        fake_infos = [(2, 1, 6, "", ("169.254.169.254", 0))]
        provider = ConfigDeclaredSearchProvider(_definition(base_url="https://sneaky.example.com/search"))

        with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
            with pytest.raises(RuntimeError, match="SSRF guard"):
                await provider.search("q", count=5)

    async def test_search_succeeds_when_base_url_resolves_to_public_address(self):
        fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]
        response = _FakeResponse(200, json.dumps({"results": []}).encode("utf-8"))
        session = _FakeSession(response)
        provider = ConfigDeclaredSearchProvider(_definition(base_url="https://real.example.com/search"))

        with (
            patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            results = await provider.search("q", count=5)

        assert results == []
