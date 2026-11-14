# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for video-generation providers — GH#9016. All HTTP is mocked.

#12979 converted the providers off per-call ``aiohttp.ClientSession()`` onto
the shared pooled client, so the double is now an ``HTTPClientManager`` stub
rather than an ``aiohttp`` module stub. The queued-response shape
(``post=`` / ``get=``) is unchanged, so every test body below reads as before.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from autobot_shared import generation_http_timeouts as gt

# Load the providers module by file path (hyphenated plugin dir is not importable).
_PROVIDERS_PATH = Path(__file__).resolve().parent / "providers.py"
_spec = importlib.util.spec_from_file_location("vg_providers_under_test", _PROVIDERS_PATH)
providers = importlib.util.module_from_spec(_spec)
sys.modules["vg_providers_under_test"] = providers
_spec.loader.exec_module(providers)


class _FakeResponse:
    """Mimics an aiohttp response usable as an async context manager."""

    def __init__(self, status: int, payload: dict):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def text(self):
        return str(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeHTTPClient:
    """Mimics ``HTTPClientManager``; ``tracked_request`` yields the queued response.

    ``tracked_request`` is an ``@asynccontextmanager`` on the real manager, and
    ``_FakeResponse`` is already an async context manager, so returning it
    directly reproduces ``async with client.tracked_request(...) as resp``.
    """

    def __init__(self, post=None, get=None):
        self._by_method = {"POST": post, "GET": get}

    def tracked_request(self, method, url, **kwargs):
        response = self._by_method.get(method.upper())
        assert response is not None, f"no fake response queued for {method} {url}"
        return response


def _patch_http_client(post=None, get=None):
    """Patch the module-level ``get_http_client`` the providers import.

    ``patch.object`` on the module object, not ``patch("...")`` by dotted path:
    ``providers`` is loaded by file path under a synthetic module name because
    the plugin directory is hyphenated and therefore not importable.
    """
    return patch.object(providers, "get_http_client", lambda: _FakeHTTPClient(post=post, get=get))


# ---------------------------------------------------------------------------
# Availability / credential gating
# ---------------------------------------------------------------------------


def test_provider_disabled_without_key():
    with patch.dict("os.environ", {"RUNWAY_API_KEY": ""}, clear=False):
        p = providers.RunwayProvider()
        assert p.available is False


def test_provider_enabled_with_key():
    p = providers.RunwayProvider(api_key="secret")
    assert p.available is True


def test_unknown_provider_raises():
    with pytest.raises(providers.ProviderError):
        providers.get_provider("nope")


def test_provider_names_stable():
    assert providers.provider_names() == ["runway", "sora", "kling"]


# ---------------------------------------------------------------------------
# Runway submit + poll + normalize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runway_submit_returns_job_id():
    post = _FakeResponse(200, {"id": "task-123"})
    p = providers.RunwayProvider(api_key="k")
    with _patch_http_client(post=post):
        job_id = await p.submit("a cat", duration=5)
    assert job_id == "task-123"


@pytest.mark.asyncio
async def test_runway_submit_quota_error():
    post = _FakeResponse(429, {"error": "rate limited"})
    p = providers.RunwayProvider(api_key="k")
    with _patch_http_client(post=post):
        with pytest.raises(providers.ProviderError) as exc:
            await p.submit("a cat")
    assert "quota" in str(exc.value).lower() or "429" in str(exc.value)


@pytest.mark.asyncio
async def test_runway_submit_missing_id():
    post = _FakeResponse(200, {})
    p = providers.RunwayProvider(api_key="k")
    with _patch_http_client(post=post):
        with pytest.raises(providers.ProviderError):
            await p.submit("a cat")


@pytest.mark.asyncio
async def test_runway_poll_succeeded():
    get = _FakeResponse(200, {"status": "SUCCEEDED", "output": ["https://v/clip.mp4"]})
    p = providers.RunwayProvider(api_key="k")
    with _patch_http_client(get=get):
        status = await p.poll("task-123")
    assert status.status == "succeeded"
    assert status.video_url == "https://v/clip.mp4"
    assert status.progress == 1.0


@pytest.mark.asyncio
async def test_runway_poll_running_progress():
    get = _FakeResponse(200, {"status": "RUNNING", "progress": 0.42})
    p = providers.RunwayProvider(api_key="k")
    with _patch_http_client(get=get):
        status = await p.poll("task-123")
    assert status.status == "running"
    assert status.progress == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_runway_poll_failed():
    get = _FakeResponse(200, {"status": "FAILED", "failure": "moderation"})
    p = providers.RunwayProvider(api_key="k")
    with _patch_http_client(get=get):
        status = await p.poll("task-123")
    assert status.status == "failed"
    assert "moderation" in (status.error or "")


@pytest.mark.asyncio
async def test_runway_poll_http_error_raises():
    get = _FakeResponse(500, {"error": "boom"})
    p = providers.RunwayProvider(api_key="k")
    with _patch_http_client(get=get):
        with pytest.raises(providers.ProviderError):
            await p.poll("task-123")


# ---------------------------------------------------------------------------
# Credential-gated providers still implement the contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sora_submit_and_poll():
    post = _FakeResponse(200, {"id": "sora-1"})
    p = providers.SoraProvider(api_key="k")
    with _patch_http_client(post=post):
        assert await p.submit("clip") == "sora-1"
    get = _FakeResponse(200, {"status": "completed", "url": "https://s/o.mp4"})
    with _patch_http_client(get=get):
        st = await p.poll("sora-1")
    assert st.status == "succeeded" and st.video_url == "https://s/o.mp4"


@pytest.mark.asyncio
async def test_kling_submit_and_poll():
    post = _FakeResponse(200, {"data": {"task_id": "kling-1"}})
    p = providers.KlingProvider(api_key="k")
    with _patch_http_client(post=post):
        assert await p.submit("clip") == "kling-1"
    get = _FakeResponse(
        200, {"data": {"task_status": "succeed", "task_result": {"videos": [{"url": "https://k/o.mp4"}]}}}
    )
    with _patch_http_client(get=get):
        st = await p.poll("kling-1")
    assert st.status == "succeeded" and st.video_url == "https://k/o.mp4"


# ---------------------------------------------------------------------------
# Every pooled request carries an explicit timeout (#12979)
# ---------------------------------------------------------------------------


class _RecordingHTTPClient:
    """Records the kwargs of each ``tracked_request`` call."""

    def __init__(self, payload: dict):
        self.calls: list = []
        self._payload = payload

    def tracked_request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return _FakeResponse(200, self._payload)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_cls,submit_body,poll_body",
    [
        (providers.RunwayProvider, {"id": "j"}, {"status": "PENDING"}),
        (providers.SoraProvider, {"id": "j"}, {"status": "queued"}),
        (providers.KlingProvider, {"data": {"task_id": "j"}}, {"data": {"task_status": "submitted"}}),
    ],
)
async def test_every_request_passes_a_timeout(provider_cls, submit_body, poll_body):
    import aiohttp

    p = provider_cls(api_key="k")
    for body, call in ((submit_body, lambda: p.submit("a cat")), (poll_body, lambda: p.poll("j"))):
        client = _RecordingHTTPClient(body)
        with patch.object(providers, "get_http_client", lambda c=client: c):
            await call()
        ((_, _, kwargs),) = client.calls
        assert isinstance(kwargs.get("timeout"), aiohttp.ClientTimeout)
        # Exact values, so neither the pooled 10s sock_read default nor a drifted
        # constant can pass.
        assert kwargs["timeout"].total == gt.POLL_TIMEOUT_S
        assert kwargs["timeout"].sock_read == gt.POLL_TIMEOUT_S
        assert kwargs["timeout"].connect == gt.CONNECT_TIMEOUT_S
