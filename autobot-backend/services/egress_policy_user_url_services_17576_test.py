# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""DB- and vendor-supplied URLs in ``services/`` are public-only: an internal origin is refused (#17576, AC4 slice 3).

``whatsapp_service.download_whatsapp_media`` requests a base URL read from a Redis setting and then a
``url`` the vendor's JSON response names. ``EGRESS_POLICY`` would trust an AutoBot-internal origin, letting
whoever controls either value aim the server (and its bearer token) at its own services; both calls
use ``guard_egress=False`` (public-only). A real manager with a mocked session shows whether a request left.
"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared import egress_allowlist as al
from autobot_shared.http_client_manager import HTTPClientManager
from autobot_shared.ssot_config import config
from services import whatsapp_service

PUBLIC_URL = "https://media.example.test/file"
PUBLIC_IP = "93.184.216.34"
DEFAULT_BASE = "https://graph.facebook.com/v18.0"
INTERNAL_URLS = [
    pytest.param(lambda: config.backend_url + "/api/x", id="ssot_backend_origin"),
    pytest.param(lambda: config.ollama_url + "/api/x", id="ssot_ollama_origin"),
    pytest.param(lambda: "http://127.0.0.1:8001/api/x", id="loopback"),
    pytest.param(lambda: "http://10.1.2.3:8001/api/x", id="private"),
    pytest.param(lambda: "http://169.254.169.254/latest/meta-data/", id="metadata"),
]


@pytest.fixture(autouse=True)
def _clean_allowlist():
    al.reset_internal_origin_state()
    yield
    al.reset_internal_origin_state()


@pytest.fixture
def net(monkeypatch):
    """Real manager, mocked session; the Redis settings and DNS are stubbed."""
    state = {"settings": {}, "meta_url": PUBLIC_URL}
    resp = MagicMock(status=200, headers={"Content-Type": "image/png"})
    resp.json = AsyncMock(side_effect=lambda: {"url": state["meta_url"], "mime_type": "image/png"})
    resp.read = AsyncMock(return_value=b"bytes")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.request = AsyncMock(return_value=resp)
    mgr = HTTPClientManager()
    # On the CLASS, not the instance (#19527): HTTPClientManager() is the process
    # singleton, and undoing an instance setattr leaves the old bound method in its
    # __dict__, where it shadows every later class-level patch in the same worker.
    monkeypatch.setattr(HTTPClientManager, "get_session", AsyncMock(return_value=session))
    for attr in ("_active_requests", "_request_count", "_error_count"):
        monkeypatch.setattr(mgr, attr, getattr(mgr, attr))
    monkeypatch.setattr("autobot_shared.http_client.get_http_client", lambda: mgr)
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, 0))]
    )

    async def _get(key):
        return {whatsapp_service.WHATSAPP_ACCESS_TOKEN_KEY: "token", **state["settings"]}.get(key)

    monkeypatch.setattr(whatsapp_service, "_get", _get)
    state["session"] = session
    return state


def _sent_urls(net):
    return [c.args[1] for c in net["session"].request.await_args_list]


@pytest.mark.asyncio
@pytest.mark.parametrize("make_url", INTERNAL_URLS)
async def test_internal_or_private_base_url_setting_is_refused_before_any_request(make_url, net):
    net["settings"][whatsapp_service.WHATSAPP_BASE_URL_KEY] = make_url()
    assert await whatsapp_service.download_whatsapp_media("m1") == (None, None)
    assert _sent_urls(net) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("make_url", INTERNAL_URLS)
async def test_internal_or_private_download_url_from_the_response_is_refused(make_url, net):
    net["meta_url"] = make_url()
    assert await whatsapp_service.download_whatsapp_media("m1") == (None, None)
    assert _sent_urls(net) == [f"{DEFAULT_BASE}/m1"]  # the metadata call only; the download never left


@pytest.mark.asyncio
async def test_public_base_url_and_public_download_url_pass_the_guard(net):
    raw, mime = await whatsapp_service.download_whatsapp_media("m1")
    assert (raw, mime) == (b"bytes", "image/png")
    assert _sent_urls(net) == [f"{DEFAULT_BASE}/m1", PUBLIC_URL]


@pytest.mark.asyncio
async def test_internal_origin_is_trusted_by_policy_but_not_here(net):
    """The key property: the origin ``EGRESS_POLICY`` waves through is refused for a vendor-supplied URL."""
    from autobot_shared.http_egress_guard import assert_egress_policy

    await assert_egress_policy(config.backend_url + "/api/x")
    net["meta_url"] = config.backend_url + "/api/x"
    assert await whatsapp_service.download_whatsapp_media("m1") == (None, None)
