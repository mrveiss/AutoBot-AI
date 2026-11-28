# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""With the opt-in on, every request to the third-party reader/search host carries the egress policy (#21850).

The host is server-chosen (SSOT); the page URL or query only rides in the request path, so the
egress target is the reader/search host and the policy that names it is ``EGRESS_POLICY``.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.http_egress_guard import EGRESS_POLICY
from autobot_shared.ssot_config import config


@pytest.fixture(autouse=True)
def _gate_on(monkeypatch):
    monkeypatch.setattr("services.web_research_config.third_party_fast_paths_enabled", lambda: True)


@pytest.mark.asyncio
async def test_fetch_jina_impl_passes_egress_policy_and_no_redirects():
    from web_fetch.fetcher import _fetch_jina_impl

    seen = {}
    resp = MagicMock(status=200)
    resp.text = AsyncMock(return_value="body")

    @asynccontextmanager
    async def tracked_request(method, url, **kwargs):
        seen.update(url=url, **kwargs)
        yield resp

    client = MagicMock(tracked_request=tracked_request)
    with patch("web_fetch.fetcher.get_http_client", return_value=client):
        assert await _fetch_jina_impl("https://example.com/p", 5.0) == "body"

    assert seen["guard_egress"] is EGRESS_POLICY
    assert not seen.get("allow_redirects")
    assert seen["url"].startswith(config.feature.third_party_reader_base_url)


@pytest.mark.asyncio
async def test_link_pipeline_applies_egress_policy_to_the_reader_url():
    from media.link import pipeline as pl

    resp = MagicMock(status=500)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock(get=MagicMock(return_value=resp))
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    guard = AsyncMock()
    with (
        patch.object(pl, "assert_egress_policy", guard),
        patch.object(pl, "_get_jina_session", MagicMock(return_value=session)),
    ):
        await pl.LinkPipeline()._try_jina("https://example.com/p")

    guard.assert_awaited_once()
    assert guard.await_args.args[0].startswith(config.feature.third_party_reader_base_url)
    assert session.get.call_args.kwargs["allow_redirects"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "backend", "request_kwargs", "base"),
    [
        ("web_page", "JinaReaderBackend", {"url": "https://example.com/p"}, "third_party_reader_base_url"),
        ("web_search", "JinaSearchBackend", {"query": "q"}, "third_party_search_base_url"),
    ],
)
async def test_content_reach_backends_apply_egress_policy(monkeypatch, module, backend, request_kwargs, base):
    import importlib

    from content_reach.base import ContentRequest

    mod = importlib.import_module(f"content_reach.sources.{module}")
    guard = AsyncMock()
    response = MagicMock(status_code=200, text="result text")
    monkeypatch.setattr("content_reach._http.assert_egress_policy", guard)
    monkeypatch.setattr(mod, "http_get", AsyncMock(return_value=response))
    monkeypatch.setattr(mod, "ensure_public_url", AsyncMock(), raising=False)
    monkeypatch.setattr(mod, "ensure_robots_allowed", AsyncMock(), raising=False)

    await getattr(mod, backend)().fetch(ContentRequest(**request_kwargs))

    guard.assert_awaited_once()
    assert guard.await_args.args[0].startswith(getattr(config.feature, base))
