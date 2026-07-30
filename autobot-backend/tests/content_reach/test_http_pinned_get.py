# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hostile-path tests for content_reach._http's pinned-connect fix (#13017).

The DNS-mocking technique (patching ``autobot_shared.url_safety.socket.getaddrinfo``)
mirrors ``api/tests/test_provider_auth_ssrf.py`` / ``config_declared_provider_test.py``
— asyncio's default ``loop.getaddrinfo`` runs the very same ``socket.getaddrinfo``
in an executor, so this exercises the REAL ``ssrf_guard.resolve_safe_ip`` guard
rather than mocking it away.

Structure:
  1. _pin_host — pure URL-rewrite unit tests (IPv4/IPv6/port)
  2. _pinned_get / http_get(client=None) — hostile cases: internal IP, localhost,
     link-local metadata, DNS-rebind; and the successful-pin path (Host + SNI
     preserved, connect target is the resolved IP literal)
  3. http_get(client=...) — injected-client path is unaffected by pinning
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from autobot_shared.security.ssrf_guard import SSRFError
from content_reach._http import _pin_host, http_get

# ---------------------------------------------------------------------------
# 1. _pin_host — pure unit tests
# ---------------------------------------------------------------------------


def test_pin_host_replaces_ipv4_host_preserves_path_query():
    pinned = _pin_host("https://example.com/a/b?x=1", "93.184.216.34")
    assert pinned == "https://93.184.216.34/a/b?x=1"


def test_pin_host_preserves_port():
    pinned = _pin_host("https://example.com:8443/page", "93.184.216.34")
    assert pinned == "https://93.184.216.34:8443/page"


def test_pin_host_brackets_ipv6_literal():
    pinned = _pin_host("http://example.com/page", "2606:2800:220:1:248:1893:25c8:1946")
    assert pinned == "http://[2606:2800:220:1:248:1893:25c8:1946]/page"


# ---------------------------------------------------------------------------
# 2. http_get(client=None) — the production, pinned-connect path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_get_blocks_internal_ip_no_network_call():
    """An outright-internal-IP URL is blocked before any httpx call is made."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        with pytest.raises(SSRFError):
            await http_get("http://10.0.0.5/secret", client=None)
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_http_get_blocks_localhost_no_network_call():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        with pytest.raises(SSRFError):
            await http_get("http://localhost:8080/x", client=None)
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_http_get_blocks_link_local_metadata_no_network_call():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        with pytest.raises(SSRFError):
            await http_get("http://169.254.169.254/latest/meta-data/", client=None)
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_http_get_blocks_dns_rebind_to_private_address():
    """A benign-looking hostname that resolves to a private IP at connect time is refused.

    This is the exact defect-2 shape: a URL that would pass a validate-then-forget
    check must still be caught because resolution happens fresh at connect time.
    """
    fake_infos = [(2, 1, 6, "", ("10.0.0.9", 0))]
    with (
        patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos),
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        with pytest.raises(SSRFError):
            await http_get("https://rebind.example.com/page", client=None)
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_http_get_blocks_dns_rebind_to_loopback():
    fake_infos = [(2, 1, 6, "", ("127.0.0.1", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(SSRFError):
            await http_get("https://sneaky.example.com/page", client=None)


@pytest.mark.asyncio
async def test_http_get_blocks_dns_rebind_to_metadata():
    fake_infos = [(2, 1, 6, "", ("169.254.169.254", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(SSRFError):
            await http_get("https://sneaky2.example.com/page", client=None)


@pytest.mark.asyncio
async def test_http_get_pins_connect_target_and_preserves_host_sni():
    """A genuinely public host connects to the resolved IP with Host + SNI preserved."""
    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["host_header"] = request.headers.get("host")
        captured["sni_hostname"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, text="ok")

    class _MockTransportClient(httpx.AsyncClient):
        """Forces every real ``httpx.AsyncClient(...)`` construction in the
        code under test onto a MockTransport bound to *handler*, so we can
        assert on the exact outbound request without touching the network.
        """

        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    with (
        patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos),
        patch("content_reach._http.httpx.AsyncClient", _MockTransportClient),
    ):
        response = await http_get("https://real.example.com/robots.txt", client=None)

    assert response.status_code == 200
    assert captured["url"] == "https://93.184.216.34/robots.txt"
    assert captured["host_header"] == "real.example.com"
    assert captured["sni_hostname"] == "real.example.com"


# ---------------------------------------------------------------------------
# 3. http_get(client=...) — injected-client (test) path is unaffected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_get_injected_client_bypasses_pinning():
    """When a client is injected, http_get uses it directly — no DNS resolution at all."""
    mock_response = httpx.Response(200, text="ok")
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_response

    with patch("autobot_shared.security.ssrf_guard.resolve_safe_ip", new_callable=AsyncMock) as mock_resolve:
        response = await http_get("http://10.0.0.5/whatever", client=mock_client)

    assert response is mock_response
    mock_resolve.assert_not_called()
