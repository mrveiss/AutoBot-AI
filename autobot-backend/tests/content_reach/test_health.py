# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
import pytest

from content_reach.base import ContentBackend
from content_reach.chain import ContentSourceChain
from content_reach.health import probe_content_reach
from content_reach.registry import get_content_source_registry
from source_attribution import SourceType


class _B(ContentBackend):
    def __init__(self, name, live):
        self.name = name
        self.source_type = SourceType.WEB_SEARCH
        self._live = live

    async def probe(self):
        return self._live

    async def fetch(self, request):
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _clean_registry():
    reg = get_content_source_registry()
    reg.clear()
    yield
    reg.clear()


@pytest.mark.asyncio
async def test_down_when_no_sources():
    ch = await probe_content_reach(None)
    assert ch.name == "content_reach"
    assert ch.status == "down"


@pytest.mark.asyncio
async def test_ok_when_all_sources_have_live_backend():
    reg = get_content_source_registry()
    reg.register_chain(ContentSourceChain("web_search", SourceType.WEB_SEARCH, [_B("a", True)]))
    ch = await probe_content_reach(None)
    assert ch.status == "ok"
    assert ch.data["live"] == {"web_search": ["a"]}
    assert ch.data["sources"] == {"web_search": ["a"]}


@pytest.mark.asyncio
async def test_degraded_when_some_source_dead():
    reg = get_content_source_registry()
    reg.register_chain(ContentSourceChain("web_search", SourceType.WEB_SEARCH, [_B("a", True)]))
    reg.register_chain(ContentSourceChain("youtube", SourceType.YOUTUBE, [_B("b", False)]))
    ch = await probe_content_reach(None)
    assert ch.status == "degraded"


@pytest.mark.asyncio
async def test_down_when_all_sources_dead():
    reg = get_content_source_registry()
    reg.register_chain(ContentSourceChain("web_search", SourceType.WEB_SEARCH, [_B("a", False)]))
    reg.register_chain(ContentSourceChain("youtube", SourceType.YOUTUBE, [_B("b", False)]))
    ch = await probe_content_reach(None)
    assert ch.status == "down"
