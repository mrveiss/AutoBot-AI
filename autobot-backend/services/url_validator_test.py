# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for URLValidator.resolve_safe_ip()
Issue #6533: Consolidate SSRF-guard implementations into shared helper
"""

import asyncio
import socket
from unittest.mock import AsyncMock, patch

import pytest

from services.url_validator import URLValidator


@pytest.mark.asyncio
class TestResolveSafeIP:
    """Tests for URLValidator.resolve_safe_ip() async DNS-rebind defense."""

    async def test_resolves_public_ipv4(self) -> None:
        """Resolving a public IPv4 should succeed."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            result = await URLValidator.resolve_safe_ip("google.com")
            assert result == "8.8.8.8"

    async def test_resolves_public_ipv6(self) -> None:
        """Resolving a public IPv6 should succeed."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:4860:4860::8888", 0, 0, 0))
            ]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            result = await URLValidator.resolve_safe_ip("google.com")
            assert result == "2001:4860:4860::8888"

    async def test_picks_first_safe_ip_from_multiple(self) -> None:
        """When multiple public IPs are returned, pick the first."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.4.4", 0)),
            ]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            result = await URLValidator.resolve_safe_ip("google.com")
            assert result == "8.8.8.8"

    async def test_rejects_loopback_ipv4(self) -> None:
        """Resolving to 127.0.0.0/8 should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("localhost")

    async def test_rejects_loopback_ipv6(self) -> None:
        """Resolving to ::1 should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 0, 0, 0))]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("localhost")

    async def test_rejects_rfc1918_10(self) -> None:
        """Resolving to 10.0.0.0/8 should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("internal.local")

    async def test_rejects_rfc1918_172(self) -> None:
        """Resolving to 172.16.0.0/12 should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.16.0.5", 0))]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("internal.local")

    async def test_rejects_rfc1918_192(self) -> None:
        """Resolving to 192.168.0.0/16 should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 0))]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("router.local")

    async def test_rejects_link_local_ipv4_aws_metadata(self) -> None:
        """Resolving to 169.254.169.254 (AWS metadata) should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("aws-metadata")

    async def test_rejects_link_local_ipv6(self) -> None:
        """Resolving to fe80::/10 should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1", 0, 0, 0))]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("link-local")

    async def test_rejects_ipv6_ula_fc(self) -> None:
        """Resolving to fc00::/7 (IPv6 ULA) should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fc00::1", 0, 0, 0))]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("internal-ipv6")

    async def test_rejects_ipv6_ula_fd(self) -> None:
        """Resolving to fd00::/8 (IPv6 ULA) should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fd12:3456:789a::1", 0, 0, 0))
            ]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("internal-ipv6")

    async def test_rejects_multicast_ipv4(self) -> None:
        """Resolving to 224.0.0.0/4 should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("224.0.0.1", 0))]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("multicast")

    async def test_rejects_multicast_ipv6(self) -> None:
        """Resolving to ff00::/8 should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("ff02::1", 0, 0, 0))]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("multicast-ipv6")

    async def test_rejects_reserved_ipv4(self) -> None:
        """Resolving to 240.0.0.0/4 should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("240.0.0.1", 0))]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("reserved")

    async def test_rejects_unspecified_ipv4(self) -> None:
        """Resolving to 0.0.0.0 should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("0.0.0.0", 0))  # nosec B104 - intentional bind to all interfaces for service/test
            ]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("unspecified")

    async def test_rejects_unspecified_ipv6(self) -> None:
        """Resolving to :: should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::", 0, 0, 0))]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("unspecified-ipv6")

    async def test_rejects_ipv4_mapped_ipv6_private(self) -> None:
        """Resolving to ::ffff:192.168.1.1 should be rejected."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:192.168.1.1", 0, 0, 0))
            ]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("ipv4-mapped-private")

    async def test_handles_mixed_responses_rejects_all_if_any_blocked(self) -> None:
        """If any response is blocked, reject the whole resolution."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
            ]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("mixed")

    async def test_handles_dns_timeout(self) -> None:
        """DNS timeout should raise ValueError."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.side_effect = asyncio.TimeoutError("timeout")
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="DNS resolution timeout"):
                await URLValidator.resolve_safe_ip("slow.example.com")

    async def test_handles_dns_resolution_error(self) -> None:
        """DNS resolution error should raise ValueError."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.side_effect = socket.gaierror("Name or service not known")
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="Cannot resolve hostname"):
                await URLValidator.resolve_safe_ip("nonexistent.invalid")

    async def test_handles_os_error(self) -> None:
        """OS-level errors during DNS resolution should raise ValueError."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.side_effect = OSError("Network is unreachable")
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="Cannot resolve hostname"):
                await URLValidator.resolve_safe_ip("example.com")

    async def test_handles_no_usable_ips(self) -> None:
        """If all IPs are blocked, raise ValueError on first blocked IP."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0)),
            ]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="non-public address"):
                await URLValidator.resolve_safe_ip("all-blocked.local")

    async def test_handles_empty_response(self) -> None:
        """Empty DNS response should raise ValueError."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = []
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            with pytest.raises(ValueError, match="no usable IP"):
                await URLValidator.resolve_safe_ip("empty.local")

    async def test_honors_timeout_parameter(self) -> None:
        """Should pass custom timeout to getaddrinfo."""
        with patch("asyncio.wait_for") as mock_wait_for:
            mock_wait_for.side_effect = asyncio.TimeoutError()

            with pytest.raises(ValueError, match="DNS resolution timeout"):
                await URLValidator.resolve_safe_ip("example.com", timeout=5.0)

    async def test_skips_invalid_ip_strings(self) -> None:
        """Should skip invalid IP strings and continue."""
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_getaddrinfo = AsyncMock()
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("not-an-ip", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
            ]
            mock_loop.return_value.getaddrinfo = mock_getaddrinfo

            result = await URLValidator.resolve_safe_ip("example.com")
            assert result == "8.8.8.8"
