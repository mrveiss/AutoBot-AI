# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for autobot_shared.security.ssrf_guard (#6533).

Covers all threat categories the shared module must block:
- Loopback (127.0.0.1, ::1)
- RFC1918 (10/8, 172.16/12, 192.168/16)
- Link-local and AWS metadata (169.254.0.0/16 — includes 169.254.169.254)
- IPv6 ULA (fc00::/7)
- Multicast and reserved
- IPv4-mapped IPv6 (::ffff:10.0.0.1)
- DNS rebind via pinned resolver (resolver map verification)
- Bad schemes
- DNS failure → fail-closed
"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.security.ssrf_guard import (
    SSRFError,
    fetch_safe_url,
    pinned_connector,
    pinned_request_with_redirects,
    resolve_safe_ip,
    safe_aiohttp_resolver,
)

# ---------------------------------------------------------------------------
# resolve_safe_ip — delegates to resolve_safe_ip_async and normalises errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_safe_ip_returns_public_ip() -> None:
    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        result = await resolve_safe_ip("example.com")
    assert result == "93.184.216.34"


@pytest.mark.asyncio
async def test_resolve_safe_ip_loopback_raises() -> None:
    fake_infos = [(2, 1, 6, "", ("127.0.0.1", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(SSRFError, match="non-public"):
            await resolve_safe_ip("loopback.example")


@pytest.mark.asyncio
async def test_resolve_safe_ip_rfc1918_raises() -> None:
    for private_ip in ("10.0.0.1", "172.16.0.1", "192.168.1.1"):
        fake_infos = [(2, 1, 6, "", (private_ip, 0))]
        with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
            with pytest.raises(SSRFError):
                await resolve_safe_ip("internal.example")


@pytest.mark.asyncio
async def test_resolve_safe_ip_link_local_raises() -> None:
    """169.254.0.0/16 — blocks AWS/Azure/GCP metadata (169.254.169.254)."""
    for link_local_ip in ("169.254.169.254", "169.254.0.1"):
        fake_infos = [(2, 1, 6, "", (link_local_ip, 0))]
        with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
            with pytest.raises(SSRFError):
                await resolve_safe_ip("metadata.example")


@pytest.mark.asyncio
async def test_resolve_safe_ip_ipv6_ula_raises() -> None:
    """fc00::/7 — IPv6 Unique Local Addresses."""
    for ula_ip in ("fc00::1", "fd12:3456:789a::1"):
        fake_infos = [(10, 1, 6, "", (ula_ip, 0))]
        with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
            with pytest.raises(SSRFError):
                await resolve_safe_ip("ipv6-ula.example")


@pytest.mark.asyncio
async def test_resolve_safe_ip_ipv6_loopback_raises() -> None:
    fake_infos = [(10, 1, 6, "", ("::1", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(SSRFError):
            await resolve_safe_ip("ipv6-loopback.example")


@pytest.mark.asyncio
async def test_resolve_safe_ip_multicast_raises() -> None:
    fake_infos = [(2, 1, 6, "", ("224.0.0.1", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(SSRFError):
            await resolve_safe_ip("multicast.example")


@pytest.mark.asyncio
async def test_resolve_safe_ip_ipv4_mapped_ipv6_raises() -> None:
    """::ffff:10.0.0.1 is IPv4-mapped IPv6; Python ipaddress treats it as private."""
    fake_infos = [(10, 1, 6, "", ("::ffff:10.0.0.1", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(SSRFError):
            await resolve_safe_ip("mapped.example")


@pytest.mark.asyncio
async def test_resolve_safe_ip_dns_failure_raises() -> None:
    import socket as _socket

    with patch(
        "autobot_shared.url_safety.socket.getaddrinfo",
        side_effect=_socket.gaierror("name not known"),
    ):
        with pytest.raises(SSRFError, match="Could not resolve"):
            await resolve_safe_ip("nonexistent.invalid")


# ---------------------------------------------------------------------------
# safe_aiohttp_resolver — pinned resolver pins IP and port
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safe_aiohttp_resolver_returns_pinned_ip() -> None:
    resolver = safe_aiohttp_resolver("example.com", "93.184.216.34", 443)
    results = await resolver.resolve("example.com", 443)
    assert len(results) == 1
    assert results[0]["host"] == "93.184.216.34"
    assert results[0]["hostname"] == "example.com"


@pytest.mark.asyncio
async def test_safe_aiohttp_resolver_ignores_dns_on_resolve() -> None:
    """The pinned resolver must NEVER call real DNS — defeats rebind protection."""
    resolver = safe_aiohttp_resolver("attack.example", "93.184.216.34", 80)
    with patch("socket.getaddrinfo") as mock_dns:
        results = await resolver.resolve("attack.example", 80)
    mock_dns.assert_not_called()
    assert results[0]["host"] == "93.184.216.34"


@pytest.mark.asyncio
async def test_safe_aiohttp_resolver_close_is_noop() -> None:
    resolver = safe_aiohttp_resolver("example.com", "1.2.3.4", 80)
    await resolver.close()  # must not raise


# ---------------------------------------------------------------------------
# pinned_connector — resolve-once + IP pin for a caller-owned ClientSession (#11497)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pinned_connector_pins_resolved_public_ip() -> None:
    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        connector = await pinned_connector("https://token.example.com/token")
    try:
        results = await connector._resolver.resolve("token.example.com", 443)
        assert results[0]["host"] == "93.184.216.34"
        assert results[0]["hostname"] == "token.example.com"
        assert results[0]["port"] == 443
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_pinned_connector_rejects_private_ip() -> None:
    fake_infos = [(2, 1, 6, "", ("10.0.0.1", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(SSRFError):
            await pinned_connector("https://internal.example/token")


@pytest.mark.asyncio
async def test_pinned_connector_rejects_no_host() -> None:
    with pytest.raises(SSRFError, match="no hostname"):
        await pinned_connector("https://")


# ---------------------------------------------------------------------------
# fetch_safe_url — end-to-end SSRF protection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_safe_url_rejects_file_scheme() -> None:
    with pytest.raises(SSRFError, match="scheme"):
        await fetch_safe_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_fetch_safe_url_rejects_no_host() -> None:
    with pytest.raises(SSRFError, match="no hostname"):
        await fetch_safe_url("https://")


@pytest.mark.asyncio
async def test_fetch_safe_url_rejects_private_ip() -> None:
    fake_infos = [(2, 1, 6, "", ("10.0.0.1", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(SSRFError):
            await fetch_safe_url("https://internal.example/path")


@pytest.mark.asyncio
async def test_fetch_safe_url_rejects_aws_metadata() -> None:
    """169.254.169.254 is link-local — must be blocked."""
    fake_infos = [(2, 1, 6, "", ("169.254.169.254", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(SSRFError):
            await fetch_safe_url("http://metadata.example/latest")


@pytest.mark.asyncio
async def test_fetch_safe_url_uses_pinned_resolver_not_redirect() -> None:
    """Verify allow_redirects=False is enforced: a redirect response must
    NOT be followed — the caller gets the raw 3xx response back."""
    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]

    mock_response = MagicMock()
    mock_response.status = 301
    mock_response.headers = {"Content-Type": "text/html", "Location": "http://10.0.0.1/"}
    mock_response.content.read = AsyncMock(return_value=b"Moved")
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session_get = MagicMock(return_value=mock_response)
    mock_session = MagicMock()
    mock_session.get = mock_session_get
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with patch("aiohttp.ClientSession", return_value=mock_session):
            status, body, _ = await fetch_safe_url("https://example.com/page")

    # Status 301 must be returned as-is; caller decides to reject it
    assert status == 301
    # Verify allow_redirects=False was passed
    call_kwargs = mock_session_get.call_args
    assert call_kwargs.kwargs.get("allow_redirects") is False


@pytest.mark.asyncio
async def test_fetch_safe_url_truncates_at_max_bytes() -> None:
    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "text/html"}
    oversized_body = b"x" * 101
    mock_response.content.read = AsyncMock(return_value=oversized_body)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with patch("aiohttp.ClientSession", return_value=mock_session):
            _, body, _ = await fetch_safe_url("https://example.com/large", max_bytes=100)

    assert len(body) == 100


@pytest.mark.asyncio
async def test_fetch_safe_url_returns_status_body_content_type() -> None:
    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.content.read = AsyncMock(return_value=b'{"ok":true}')
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with patch("aiohttp.ClientSession", return_value=mock_session):
            status, body, ct = await fetch_safe_url("https://example.com/api")

    assert status == 200
    assert body == b'{"ok":true}'
    assert ct == "application/json"


# ---------------------------------------------------------------------------
# pinned_request_with_redirects — per-hop pinned redirect following (#13019)
# ---------------------------------------------------------------------------


def _make_fake_session_class(responses):
    """Return a fake ``aiohttp.ClientSession`` class + a shared *calls* log.

    Each instantiation pulls the next canned response from *responses* on
    ``.request()``; ``.close()`` is a no-op. Mirrors the real API surface
    ``pinned_request_with_redirects`` actually uses (``request`` + ``close``),
    not ``get`` + ``async with session`` like ``fetch_safe_url``'s tests.
    """
    calls = []

    class _FakeSession:
        def __init__(self, *args, **kwargs):
            self._init_kwargs = kwargs
            calls.append({"connector": kwargs.get("connector")})

        async def request(self, method, url, **kwargs):
            calls[-1].update({"method": method, "url": url, "kwargs": kwargs})
            return responses.pop(0)

        async def close(self):
            calls[-1]["closed"] = True

    return _FakeSession, calls


def _make_fake_response(status, headers=None):
    resp = MagicMock()
    resp.status = status
    resp.headers = headers or {}
    resp.release = AsyncMock(return_value=None)
    return resp


@pytest.mark.asyncio
async def test_pinned_request_with_redirects_blocks_private_ip_no_network_call() -> None:
    """A private-IP-literal URL is blocked before any session is created."""
    with patch("aiohttp.ClientSession") as mock_session_cls:
        with pytest.raises(SSRFError):
            async with pinned_request_with_redirects("GET", "http://10.0.0.5/secret"):
                pass
    mock_session_cls.assert_not_called()


@pytest.mark.asyncio
async def test_pinned_request_with_redirects_blocks_localhost_no_network_call() -> None:
    with patch("aiohttp.ClientSession") as mock_session_cls:
        with pytest.raises(SSRFError):
            async with pinned_request_with_redirects("GET", "http://localhost:8080/x"):
                pass
    mock_session_cls.assert_not_called()


@pytest.mark.asyncio
async def test_pinned_request_with_redirects_blocks_link_local_metadata_no_network_call() -> None:
    with patch("aiohttp.ClientSession") as mock_session_cls:
        with pytest.raises(SSRFError):
            async with pinned_request_with_redirects("GET", "http://169.254.169.254/latest/meta-data/"):
                pass
    mock_session_cls.assert_not_called()


@pytest.mark.asyncio
async def test_pinned_request_with_redirects_blocks_dns_rebind_to_private_address() -> None:
    """Public-looking hostname that resolves to a private IP at connect time is refused.

    Exercises the REAL ``resolve_safe_ip`` guard via mocked DNS (never mocking
    the guard itself) — the classic validate-then-forget rebind shape.
    """
    fake_infos = [(2, 1, 6, "", ("10.0.0.9", 0))]
    with (
        patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos),
        patch("aiohttp.ClientSession") as mock_session_cls,
    ):
        with pytest.raises(SSRFError):
            async with pinned_request_with_redirects("GET", "https://rebind.example.com/page"):
                pass
    mock_session_cls.assert_not_called()


@pytest.mark.asyncio
async def test_pinned_request_with_redirects_no_redirect_returns_response() -> None:
    """A plain 200 is yielded as-is; session is closed on context exit."""
    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]
    fake_cls, calls = _make_fake_session_class([_make_fake_response(200, {"Content-Type": "text/html"})])

    with (
        patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos),
        patch("aiohttp.ClientSession", fake_cls),
    ):
        async with pinned_request_with_redirects("GET", "https://real.example.com/page") as resp:
            assert resp.status == 200

    assert len(calls) == 1
    assert calls[0]["url"] == "https://real.example.com/page"
    assert calls[0]["kwargs"]["allow_redirects"] is False
    assert calls[0].get("closed") is True

    # The connector actually used for the connect is pinned to the resolved
    # IP literal while Host/TLS SNI (the resolver's "hostname" field) still
    # preserve the original hostname — i.e. validation and connect target
    # are the same address, but the vhost/cert identity is unchanged.
    resolver_result = await calls[0]["connector"]._resolver.resolve("real.example.com", 443)
    assert resolver_result[0]["host"] == "93.184.216.34"
    assert resolver_result[0]["hostname"] == "real.example.com"


@pytest.mark.asyncio
async def test_pinned_request_with_redirects_follows_redirect_with_per_hop_pin() -> None:
    """A same-origin 302 is followed; the second hop is independently resolved + pinned."""
    per_hop_infos = [
        [(2, 1, 6, "", ("93.184.216.34", 0))],  # hop 1: real.example.com
        [(2, 1, 6, "", ("8.8.4.4", 0))],  # hop 2: real2.example.com
    ]
    fake_cls, calls = _make_fake_session_class(
        [
            _make_fake_response(302, {"Location": "https://real2.example.com/final"}),
            _make_fake_response(200, {"Content-Type": "text/html"}),
        ]
    )

    with (
        patch("autobot_shared.url_safety.socket.getaddrinfo", side_effect=per_hop_infos),
        patch("aiohttp.ClientSession", fake_cls),
    ):
        async with pinned_request_with_redirects("GET", "https://real.example.com/start") as resp:
            assert resp.status == 200

    assert len(calls) == 2
    assert calls[0]["url"] == "https://real.example.com/start"
    assert calls[1]["url"] == "https://real2.example.com/final"
    # Each hop gets its OWN connector pinned to that hop's resolved IP.
    assert calls[0]["connector"] is not calls[1]["connector"]


@pytest.mark.asyncio
async def test_pinned_request_with_redirects_rejects_redirect_to_private_ip() -> None:
    """A redirect Location pointing at a private IP literal is rejected outright, never followed.

    Only hop 1's hostname needs DNS mocked; hop 2 is an IP literal that the
    REAL (unmocked) resolver parses directly — verifying the private-IP
    rejection is genuine, not an artifact of a blanket DNS mock.
    """
    real_getaddrinfo = socket.getaddrinfo

    def _fake_getaddrinfo(host, *args, **kwargs):
        if host == "open-redirect.example.com":
            return [(2, 1, 6, "", ("93.184.216.34", 0))]
        return real_getaddrinfo(host, *args, **kwargs)

    fake_cls, calls = _make_fake_session_class([_make_fake_response(302, {"Location": "http://10.0.0.5/internal"})])

    with (
        patch("autobot_shared.url_safety.socket.getaddrinfo", side_effect=_fake_getaddrinfo),
        patch("aiohttp.ClientSession", fake_cls),
    ):
        with pytest.raises(SSRFError):
            async with pinned_request_with_redirects("GET", "https://open-redirect.example.com/go"):
                pass

    # Only the first (legitimate) hop actually connected; the second was blocked pre-connect.
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_pinned_request_with_redirects_exceeds_max_redirects_raises() -> None:
    """A redirect chain longer than max_redirects raises SSRFError, not a silent truncation."""
    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]
    responses = [_make_fake_response(302, {"Location": f"https://real.example.com/hop{i}"}) for i in range(5)]
    fake_cls, calls = _make_fake_session_class(responses)

    with (
        patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos),
        patch("aiohttp.ClientSession", fake_cls),
    ):
        with pytest.raises(SSRFError, match="exceeded max_redirects"):
            async with pinned_request_with_redirects("GET", "https://real.example.com/start", max_redirects=2):
                pass

    # max_redirects=2 allows hops 0,1,2 (3 attempts) before giving up.
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_pinned_request_with_redirects_passes_ssl_kwarg_through() -> None:
    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]
    fake_cls, calls = _make_fake_session_class([_make_fake_response(200)])

    with (
        patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos),
        patch("aiohttp.ClientSession", fake_cls),
    ):
        async with pinned_request_with_redirects("GET", "https://real.example.com/x", ssl=False):
            pass

    assert calls[0]["kwargs"]["ssl"] is False
