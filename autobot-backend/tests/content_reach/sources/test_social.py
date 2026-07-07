# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for content_reach.sources.social (build_social_chain)."""

from __future__ import annotations

import pytest

from content_reach.base import ContentRequest
from source_attribution import SourceType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubManager:
    """Minimal stub for the research browser manager."""

    def __init__(self, result: dict) -> None:
        self._result = result

    async def research_url(self, conversation_id: str, url: str, extract_content: bool = True) -> dict:
        return self._result


# ---------------------------------------------------------------------------
# build_social_chain()
# ---------------------------------------------------------------------------


def test_build_social_chain():
    """build_social_chain() returns a chain named 'social' with one 'browser' backend."""
    from content_reach.sources.social import build_social_chain

    chain = build_social_chain()
    assert chain.backend_names() == ["browser"]
    assert chain.source_type is SourceType.SOCIAL
    assert chain.source == "social"


# ---------------------------------------------------------------------------
# fetch() — result carries SourceType.SOCIAL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_social_fetch_carries_social_source_type(monkeypatch):
    """BrowserBackend(SOCIAL).fetch() maps the stub result and carries source_type=SOCIAL."""
    stub_manager = _StubManager(
        {
            "success": True,
            "content": {
                "text_content": "tweet text",
                "structured_data": {},
            },
            "title": "t",
        }
    )

    import content_reach._url_guard as guard_mod
    import content_reach.backends.browser as browser_mod

    async def _always_public(_url: str) -> bool:
        return True

    monkeypatch.setattr(guard_mod, "_is_public_url_async", _always_public)
    monkeypatch.setattr(guard_mod, "_RESPECT_ROBOTS", False)
    monkeypatch.setattr(browser_mod, "_get_manager", lambda: stub_manager)

    from content_reach.sources.social import build_social_chain

    chain = build_social_chain()
    backend = chain.backends[0]

    request = ContentRequest(url="https://twitter.com/x/status/1")
    result = await backend.fetch(request)

    assert result.success is True
    assert result.source_type is SourceType.SOCIAL
