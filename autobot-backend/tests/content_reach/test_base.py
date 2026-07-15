# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
import pytest

from content_reach.base import BackendError, ContentBackend, ContentRequest, ContentResult
from source_attribution import SourceReliability, SourceType


def test_content_result_failure_factory():
    r = ContentResult.failure(SourceType.WEB_SEARCH, "boom")
    assert r.success is False
    assert r.source_type is SourceType.WEB_SEARCH
    assert r.backend_used == "none"
    assert r.metadata["error"] == "boom"


def test_content_request_defaults():
    req = ContentRequest(query="hello")
    assert req.query == "hello"
    assert req.limit == 5
    assert req.options == {}


def test_content_backend_is_abstract():
    with pytest.raises(TypeError):
        ContentBackend()  # abstract methods unimplemented


@pytest.mark.asyncio
async def test_concrete_backend_roundtrip():
    class Dummy(ContentBackend):
        name = "dummy"
        source_type = SourceType.WEB_SEARCH

        async def probe(self) -> bool:
            return True

        async def fetch(self, request: ContentRequest) -> ContentResult:
            return ContentResult(
                success=True,
                source_type=self.source_type,
                backend_used=self.name,
                text=f"result for {request.query}",
                reliability=SourceReliability.MEDIUM,
            )

    d = Dummy()
    assert await d.probe() is True
    res = await d.fetch(ContentRequest(query="q"))
    assert res.success and res.text == "result for q"
    assert isinstance(BackendError(), Exception)
