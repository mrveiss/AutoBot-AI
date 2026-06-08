# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
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

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.security.ssrf_guard import (
    SSRFError,
    fetch_safe_url,
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
