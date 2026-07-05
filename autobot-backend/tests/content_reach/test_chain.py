# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from content_reach.base import ContentBackend
from content_reach.chain import ContentSourceChain
from source_attribution import SourceType


def _stub(backend_name: str) -> ContentBackend:
    class _B(ContentBackend):
        name = backend_name
        source_type = SourceType.WEB_SEARCH

        async def probe(self):
            return True

        async def fetch(self, request):
            raise NotImplementedError

    return _B()


def _chain():
    return ContentSourceChain(
        source="web_search",
        source_type=SourceType.WEB_SEARCH,
        backends=[_stub("ddgs"), _stub("jina"), _stub("browser")],
    )


def test_backend_names_preserve_order():
    assert _chain().backend_names() == ["ddgs", "jina", "browser"]


def test_reorder_noop_without_env(monkeypatch):
    monkeypatch.delenv("AUTOBOT_CONTENT_CHAIN_WEB_SEARCH", raising=False)
    assert _chain().reordered().backend_names() == ["ddgs", "jina", "browser"]


def test_reorder_promotes_named_backends(monkeypatch):
    monkeypatch.setenv("AUTOBOT_CONTENT_CHAIN_WEB_SEARCH", "browser,ddgs")
    assert _chain().reordered().backend_names() == ["browser", "ddgs", "jina"]


def test_reorder_ignores_unknown_names(monkeypatch):
    monkeypatch.setenv("AUTOBOT_CONTENT_CHAIN_WEB_SEARCH", "nope,jina")
    assert _chain().reordered().backend_names() == ["jina", "ddgs", "browser"]


def test_reorder_noop_returns_new_instance(monkeypatch):
    monkeypatch.delenv("AUTOBOT_CONTENT_CHAIN_WEB_SEARCH", raising=False)
    original = _chain()
    result = original.reordered()
    assert result is not original
    assert result.backend_names() == original.backend_names()
