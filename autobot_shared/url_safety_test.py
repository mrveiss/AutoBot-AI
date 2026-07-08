# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Contract tests for ``autobot_shared.url_safety`` (#7477).

Validates the extracted SSRF guard. The full-coverage tests for the
``LinkPipeline._is_public_url`` method (28 tests) still live in
``autobot-backend/media/link/pipeline_test.py`` and validate the same
function via the backward-compat method wrapper. These tests pin the
import-isolation contract that motivated the extraction.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from autobot_shared.url_safety import (
    host_matches,
    is_public_url,
    is_public_url_async,
    require_allowlisted_https,
    resolve_safe_ip_async,
)

# ---------------------------------------------------------------------------
# Scheme/host rejection
# ---------------------------------------------------------------------------


def test_rejects_non_http_schemes() -> None:
    assert is_public_url("file:///etc/passwd") is False
    assert is_public_url("ftp://example.com") is False
    assert is_public_url("javascript:alert(1)") is False


def test_rejects_empty_or_no_host() -> None:
    assert is_public_url("https://") is False
    assert is_public_url("not-a-url") is False
    assert is_public_url("") is False


# ---------------------------------------------------------------------------
# Private TLD / hostname rejection (no DNS needed)
# ---------------------------------------------------------------------------


def test_rejects_localhost_hostname() -> None:
    assert is_public_url("http://localhost/page") is False
    assert is_public_url("http://localhost:8080/api") is False


def test_rejects_private_tlds() -> None:
    assert is_public_url("http://server.internal/admin") is False
    assert is_public_url("http://router.local/page") is False
    assert is_public_url("http://machine.lan/share") is False
    assert is_public_url("http://nas.home/files") is False
    assert is_public_url("http://intranet.corp/login") is False
    assert is_public_url("http://hidden.onion/") is False


# ---------------------------------------------------------------------------
# Literal-IP rejection (no DNS needed)
# ---------------------------------------------------------------------------


def test_rejects_loopback_ip_literal() -> None:
    assert is_public_url("http://127.0.0.1/admin") is False
    assert is_public_url("http://[::1]/api") is False


def test_rejects_rfc1918_ip_literals() -> None:
    assert is_public_url("http://10.0.0.1/admin") is False
    assert is_public_url("http://172.16.0.1/page") is False
    assert is_public_url("http://192.168.1.1/login") is False


def test_rejects_ipv6_unique_local_ip_literals() -> None:
    """fc00::/7 — IPv6 ULA range."""
    assert is_public_url("http://[fc00::1]/page") is False
    assert is_public_url("http://[fd12:3456:789a::1]/api") is False


# ---------------------------------------------------------------------------
# DNS-resolved rejection
# ---------------------------------------------------------------------------


def test_rejects_hostname_resolving_to_rfc1918() -> None:
    """A bare-domain DNS-rebind label resolving to private space must
    be rejected. Mocks ``socket.getaddrinfo`` to avoid live DNS."""
    fake_infos = [(2, 1, 6, "", ("10.5.5.5", 0))]  # AF_INET, RFC1918
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        assert is_public_url("https://intranet-db.company/admin") is False


def test_rejects_hostname_resolving_to_loopback() -> None:
    fake_infos = [(2, 1, 6, "", ("127.0.0.1", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        assert is_public_url("https://10-0-0-1.public.example/api") is False


def test_dns_failure_is_fail_closed() -> None:
    """Any DNS error must result in False (fail closed)."""
    import socket as _socket

    with patch(
        "autobot_shared.url_safety.socket.getaddrinfo",
        side_effect=_socket.gaierror("simulated"),
    ):
        assert is_public_url("https://nonexistent.example.invalid/x") is False


# ---------------------------------------------------------------------------
# Async wrapper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_wrapper_delegates_to_sync_in_executor() -> None:
    fake_infos = [(2, 1, 6, "", ("10.5.5.5", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        assert (await is_public_url_async("https://intranet-db.company/admin")) is False


# ---------------------------------------------------------------------------
# resolve_safe_ip_async — returns resolved IP literal for TOCTOU protection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_safe_ip_returns_ip_for_public_hostname() -> None:
    """resolve_safe_ip_async returns the first public IP when resolution succeeds."""
    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]  # example.com
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        result = await resolve_safe_ip_async("example.com")
        assert result == "93.184.216.34"


@pytest.mark.asyncio
async def test_resolve_safe_ip_rejects_rfc1918() -> None:
    """resolve_safe_ip_async raises ValueError for private IPs."""
    fake_infos = [(2, 1, 6, "", ("10.5.5.5", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(ValueError, match="non-public"):
            await resolve_safe_ip_async("internal.example")


@pytest.mark.asyncio
async def test_resolve_safe_ip_rejects_loopback() -> None:
    """resolve_safe_ip_async rejects 127.0.0.1 and ::1."""
    fake_infos = [(2, 1, 6, "", ("127.0.0.1", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(ValueError, match="non-public"):
            await resolve_safe_ip_async("localhost.example")


@pytest.mark.asyncio
async def test_resolve_safe_ip_rejects_ipv6_ula() -> None:
    """resolve_safe_ip_async rejects fc00::/7 (IPv6 ULA)."""
    fake_infos = [(10, 1, 6, "", ("fc00::1", 0))]  # AF_INET6
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(ValueError, match="non-public"):
            await resolve_safe_ip_async("ipv6-private.example")


@pytest.mark.asyncio
async def test_resolve_safe_ip_rejects_dns_failure() -> None:
    """resolve_safe_ip_async raises ValueError on DNS resolution failure."""
    import socket as _socket

    with patch(
        "autobot_shared.url_safety.socket.getaddrinfo",
        side_effect=_socket.gaierror("name or service not known"),
    ):
        with pytest.raises(ValueError, match="Could not resolve"):
            await resolve_safe_ip_async("nonexistent.invalid")


@pytest.mark.asyncio
async def test_resolve_safe_ip_no_usable_ip() -> None:
    """resolve_safe_ip_async raises ValueError if all resolved IPs are private."""
    fake_infos = [
        (2, 1, 6, "", ("192.168.1.1", 0)),  # Private
        (2, 1, 6, "", ("10.0.0.1", 0)),  # Private
    ]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(ValueError, match="non-public"):
            await resolve_safe_ip_async("all-private.example")


# ---------------------------------------------------------------------------
# Import-isolation contract (the whole point of #7477)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# require_allowlisted_https — allowlist + port-pinning SSRF guard (#11091)
# ---------------------------------------------------------------------------

_ALLOW = frozenset({"accounts.google.com", "github.com", "api.anthropic.com"})


def test_allowlisted_https_host_passes() -> None:
    # Standard https on an allowlisted host (port None or explicit 443) is allowed.
    require_allowlisted_https("https://accounts.google.com/o/oauth2/token", _ALLOW)
    require_allowlisted_https("https://github.com:443/login/oauth/access_token", _ALLOW)


@pytest.mark.parametrize(
    "url, reason",
    [
        ("http://accounts.google.com/token", "https"),  # non-https scheme
        ("https://169.254.169.254/latest/meta-data/", "IP-literal"),  # IMDS via IPv4 literal
        ("https://127.0.0.1/token", "IP-literal"),
        ("https://[::1]/token", "IP-literal"),  # IPv6 loopback literal
        ("https://10.0.0.1/token", "IP-literal"),  # private range literal
        ("https://evil-attacker.example.com/token", "allowlist"),  # not allowlisted
        ("https://accounts.google.com:22/token", "port"),  # allowlisted host, non-443 port
        ("https:///token", "host"),  # no host
    ],
)
def test_require_allowlisted_https_rejects(url: str, reason: str) -> None:
    with pytest.raises(ValueError) as exc:
        require_allowlisted_https(url, _ALLOW)
    assert reason.lower() in str(exc.value).lower()


def test_malformed_port_raises_valueerror_not_unhandled() -> None:
    # urlparse defers port parsing; an out-of-range port must surface as ValueError.
    with pytest.raises(ValueError) as exc:
        require_allowlisted_https("https://accounts.google.com:99999/token", _ALLOW)
    assert "port" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# host_matches — domain-boundary trust check (#11226)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host, domain",
    [
        ("github.com", "github.com"),  # exact
        ("sub.github.com", "github.com"),  # subdomain
        ("a.b.github.com", "github.com"),  # deep subdomain
        ("GitHub.com", "github.com"),  # case-insensitive
        ("github.com.", "github.com"),  # trailing FQDN dot
    ],
)
def test_host_matches_true(host: str, domain: str) -> None:
    assert host_matches(host, domain) is True


@pytest.mark.parametrize(
    "host, domain",
    [
        ("evilgithub.com", "github.com"),  # substring-prefix attack
        ("github.com.evil.com", "github.com"),  # trusted label as a subdomain of attacker
        ("notstackoverflow.com", "stackoverflow.com"),
        ("fakewikipedia.org", "wikipedia.org"),
        ("mygithub.com", "github.com"),
        ("", "github.com"),  # empty host
    ],
)
def test_host_matches_false(host: str, domain: str) -> None:
    assert host_matches(host, domain) is False


def test_module_has_zero_autobot_dependencies() -> None:
    """The extracted module must NOT import from ``media.link``,
    ``web_fetch``, or anywhere else inside autobot — that's the cycle-
    breaking contract."""
    import importlib
    import sys

    sys.modules.pop("autobot_shared.url_safety", None)
    mod = importlib.import_module("autobot_shared.url_safety")

    src = open(mod.__file__, encoding="utf-8").read()  # noqa: SIM115
    assert "from media" not in src
    assert "from web_fetch" not in src
    assert "from autobot_backend" not in src
    assert "from autobot_shared" not in src  # no sibling cross-deps either
