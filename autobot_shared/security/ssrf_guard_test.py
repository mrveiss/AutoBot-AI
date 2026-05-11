# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Tests for ``autobot_shared.security.ssrf_guard`` (GH #6533).

Covers the three public functions:
- ``resolve_safe_ip``     — async DNS-resolving guard
- ``safe_aiohttp_resolver`` — pinned resolver factory
- ``fetch_safe_url``      — SSRF-safe HTTP GET

Test matrix per acceptance criteria:
- Loopback (127.0.0.1, ::1)
- RFC 1918 private (10.x, 172.16-31.x, 192.168.x)
- Link-local / cloud metadata (169.254.169.254)
- IPv6 ULA (fc00::/7, fd::/8)
- Multicast (224.x, ff00::)
- Reserved
- IPv4-mapped IPv6 (::ffff:192.168.x.x)
- DNS rebind (hostname resolves to private IP)
- DNS failure (fail-closed)
- DNS pinning (safe_aiohttp_resolver)
- allow_redirects=False enforcement
"""

from __future__ import annotations

import socket
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.security.ssrf_guard import (
    SSRFError,
    fetch_safe_url,
    resolve_safe_ip,
    safe_aiohttp_resolver,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_getaddrinfo(ip: str) -> list[tuple]:
    """Return a minimal getaddrinfo result that resolves to *ip*."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]


def _fake_getaddrinfo_ipv6(ip: str) -> list[tuple]:
    return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, 0, 0, 0))]


# ---------------------------------------------------------------------------
# resolve_safe_ip — blocked addresses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blocks_loopback_ipv4() -> None:
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo("127.0.0.1"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="non-public"):
            await resolve_safe_ip("localhost")


@pytest.mark.asyncio
async def test_blocks_loopback_ipv6() -> None:
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo_ipv6("::1"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="non-public"):
            await resolve_safe_ip("ip6-localhost")


@pytest.mark.asyncio
async def test_blocks_rfc1918_10_dot() -> None:
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo("10.0.0.1"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="non-public"):
            await resolve_safe_ip("internal.example")


@pytest.mark.asyncio
async def test_blocks_rfc1918_172_16() -> None:
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo("172.16.0.5"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="non-public"):
            await resolve_safe_ip("internal.example")


@pytest.mark.asyncio
async def test_blocks_rfc1918_192_168() -> None:
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo("192.168.1.100"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="non-public"):
            await resolve_safe_ip("printer.local")


@pytest.mark.asyncio
async def test_blocks_link_local_aws_metadata() -> None:
    """169.254.169.254 is the AWS/GCP/Azure metadata endpoint — must be blocked."""
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo("169.254.169.254"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="non-public"):
            await resolve_safe_ip("metadata.internal")


@pytest.mark.asyncio
async def test_blocks_ipv6_ula_fc00() -> None:
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo_ipv6("fc00::1"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="non-public"):
            await resolve_safe_ip("internal.v6")


@pytest.mark.asyncio
async def test_blocks_ipv6_ula_fd_prefix() -> None:
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo_ipv6("fd12:3456:789a::1"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="non-public"):
            await resolve_safe_ip("internal.v6")


@pytest.mark.asyncio
async def test_blocks_multicast_ipv4() -> None:
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo("224.0.0.1"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="non-public"):
            await resolve_safe_ip("mcast.example")


@pytest.mark.asyncio
async def test_blocks_multicast_ipv6() -> None:
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo_ipv6("ff02::1"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="non-public"):
            await resolve_safe_ip("mcast6.example")


@pytest.mark.asyncio
async def test_blocks_ipv4_mapped_ipv6_private() -> None:
    """::ffff:192.168.1.1 is an IPv4-mapped IPv6 address wrapping a private IPv4.
    Must be blocked even if the outer IPv6 form passes a naive check."""
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo_ipv6("::ffff:192.168.1.1"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="non-public"):
            await resolve_safe_ip("bypass.example")


@pytest.mark.asyncio
async def test_blocks_ipv4_mapped_ipv6_loopback() -> None:
    """::ffff:127.0.0.1 must be blocked."""
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo_ipv6("::ffff:127.0.0.1"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="non-public"):
            await resolve_safe_ip("bypass.example")


# ---------------------------------------------------------------------------
# resolve_safe_ip — DNS rebind (hostname resolves to private IP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dns_rebind_hostname_resolves_to_private() -> None:
    """A public-looking hostname that resolves to RFC1918 must be blocked."""
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo("10.5.5.5"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError):
            await resolve_safe_ip("rebind.attacker.example")


# ---------------------------------------------------------------------------
# resolve_safe_ip — DNS failure (fail-closed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dns_failure_raises_ssrf_error() -> None:
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(side_effect=socket.gaierror("simulated DNS failure"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="Could not resolve"):
            await resolve_safe_ip("nonexistent.invalid")


@pytest.mark.asyncio
async def test_empty_dns_response_raises_ssrf_error() -> None:
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=[])
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError, match="no usable public IP"):
            await resolve_safe_ip("no-records.example")


# ---------------------------------------------------------------------------
# resolve_safe_ip — public address passes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_ip_passes() -> None:
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo("93.184.216.34"))
        mock_asyncio.get_running_loop.return_value = loop
        result = await resolve_safe_ip("example.com")
    assert result == "93.184.216.34"


# ---------------------------------------------------------------------------
# safe_aiohttp_resolver — pinning contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pinned_resolver_returns_correct_ip() -> None:
    resolver = safe_aiohttp_resolver("example.com", "93.184.216.34", 443)
    result = await resolver.resolve("example.com", 443)
    assert result[0]["host"] == "93.184.216.34"
    assert result[0]["hostname"] == "example.com"


@pytest.mark.asyncio
async def test_pinned_resolver_returns_empty_for_other_host() -> None:
    resolver = safe_aiohttp_resolver("example.com", "93.184.216.34", 443)
    result = await resolver.resolve("other.com", 443)
    assert result == []


@pytest.mark.asyncio
async def test_pinned_resolver_close_is_noop() -> None:
    resolver = safe_aiohttp_resolver("example.com", "93.184.216.34", 443)
    await resolver.close()  # must not raise


# ---------------------------------------------------------------------------
# fetch_safe_url — scheme guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_safe_url_rejects_non_http_scheme() -> None:
    with pytest.raises(SSRFError, match="scheme"):
        await fetch_safe_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_fetch_safe_url_rejects_no_hostname() -> None:
    with pytest.raises(SSRFError, match="hostname"):
        await fetch_safe_url("https://")


# ---------------------------------------------------------------------------
# fetch_safe_url — SSRF-safe fetch (mocked network)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_safe_url_blocks_private_ip() -> None:
    """fetch_safe_url must raise SSRFError when host resolves to private IP."""
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo("10.0.0.1"))
        mock_asyncio.get_running_loop.return_value = loop
        with pytest.raises(SSRFError):
            await fetch_safe_url("http://internal.example/data")


@pytest.mark.asyncio
async def test_fetch_safe_url_returns_status_and_body() -> None:
    """Successful fetch returns (status, bytes) with allow_redirects=False."""
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo("93.184.216.34"))
        mock_asyncio.get_running_loop.return_value = loop

        # Mock the aiohttp session/response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=b"<html>hello</html>")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session_get = MagicMock()
        mock_session_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_get.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_session_get)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        import aiohttp

        with patch.object(aiohttp, "ClientSession", return_value=mock_session):
            with patch.object(aiohttp, "TCPConnector", return_value=MagicMock()):
                status_code, body = await fetch_safe_url("http://example.com/page")

    assert status_code == 200
    assert body == b"<html>hello</html>"
    # Verify allow_redirects=False was passed
    mock_session.get.assert_called_once()
    call_kwargs = mock_session.get.call_args.kwargs
    assert call_kwargs.get("allow_redirects") is False


@pytest.mark.asyncio
async def test_fetch_safe_url_respects_max_bytes() -> None:
    """When max_bytes is set, reads with a +1 cap (caller detects overflow)."""
    with patch("autobot_shared.security.ssrf_guard.asyncio") as mock_asyncio:
        loop = MagicMock()
        loop.getaddrinfo = AsyncMock(return_value=_fake_getaddrinfo("93.184.216.34"))
        mock_asyncio.get_running_loop.return_value = loop

        mock_content = MagicMock()
        mock_content.read = AsyncMock(return_value=b"x" * 10)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content = mock_content
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session_get = MagicMock()
        mock_session_get.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_get.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_session_get)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        import aiohttp

        with patch.object(aiohttp, "ClientSession", return_value=mock_session):
            with patch.object(aiohttp, "TCPConnector", return_value=MagicMock()):
                await fetch_safe_url("http://example.com/big", max_bytes=5)

    # content.read was called with max_bytes + 1 = 6
    mock_content.read.assert_called_once_with(6)
