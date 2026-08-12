# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""`is_url_allowed` resolves hosts instead of prefix-matching URLs (#13236 step 5).

The regex allowlist it replaced was bypassable. Its patterns were anchored at
the start but **not** the end, so any attacker-controlled domain prefixed with
an allowlisted string passed — a lookalike host such as
``github.com.<attacker>`` or ``localhost.<attacker>`` matched.

Those cases come first here, because they are why this is a fix rather than a
tidy-up.

The admin surface still reaches genuinely internal hosts — that is what it is
for — but by matching the *parsed hostname* against an explicit exception set,
never by matching text against the URL. Fleet addresses come from SSOT config
rather than a hardcoded range.
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.browser_mcp import (
    INTERNAL_HOST_EXCEPTIONS,
    _is_excepted_internal_host,
    fleet_host_exceptions,
    is_url_allowed,
)

_RESOLVER = "api.browser_mcp.is_public_url_async"


def _not_public():
    """The resolving guard says: not a public address."""
    return patch(_RESOLVER, AsyncMock(return_value=False))


def _public():
    return patch(_RESOLVER, AsyncMock(return_value=True))


# ------------------------------------------------------------ the bypass


@pytest.mark.parametrize(
    "host",
    [
        "github.com.attacker.test",
        "localhost.attacker.test",
        "127.0.0.1.attacker.test",
        "evil.github.com.attacker.test",
    ],
)
@pytest.mark.asyncio
async def test_lookalike_domains_are_refused(host):
    """Every one of these passed the old prefix-matching allowlist."""
    with _not_public():
        assert await is_url_allowed(f"https://{host}/") is False


def test_lookalike_hostnames_are_not_internal_exceptions():
    """The host match is exact — a prefix must not qualify."""
    for host in ("localhost.attacker.test", "127.0.0.1.attacker.test", "notlocalhost"):
        assert _is_excepted_internal_host(host) is False


# ------------------------------------------------------------ what is allowed


@pytest.mark.asyncio
async def test_a_public_url_is_allowed_without_being_listed():
    """Public hosts no longer need an allowlist entry at all."""
    with _public():
        assert await is_url_allowed("https://example.org/some/page") is True


@pytest.mark.asyncio
async def test_loopback_stays_reachable_for_the_admin_surface():
    """Driving the browser at a local service is what this surface is for."""
    with _not_public():
        for url in ("http://localhost:3000/", "http://127.0.0.1:8000/health"):
            assert await is_url_allowed(url) is True


@pytest.mark.asyncio
async def test_fleet_hosts_come_from_ssot_not_a_hardcoded_range():
    """Whatever ConfigRegistry reports as a fleet host is exempt — and only that.

    The regex this replaced baked a /24 into the source, which exempted a whole
    subnet rather than the known hosts, and put a fleet address in code.
    """
    with patch("api.browser_mcp.fleet_host_exceptions", lambda: frozenset({"10.99.0.7"})):
        assert _is_excepted_internal_host("10.99.0.7") is True
        assert _is_excepted_internal_host("10.99.0.8") is False


def test_fleet_host_exceptions_degrades_to_empty_without_config():
    """Config unavailable must exempt nothing, not raise or guess."""

    class _Boom:
        def __getattr__(self, name):
            raise RuntimeError("config unavailable")

    with patch("api.browser_mcp.NetworkConstants", _Boom()):
        assert fleet_host_exceptions() == frozenset()


@pytest.mark.asyncio
async def test_other_private_addresses_are_still_refused():
    """Only listed hosts are excepted, not private space at large."""
    with _not_public():
        with patch("api.browser_mcp.fleet_host_exceptions", frozenset):
            assert await is_url_allowed("http://169.254.169.254/latest/meta-data/") is False
            assert await is_url_allowed("http://10.0.0.5/") is False


# ------------------------------------------------------------ scheme + shape


@pytest.mark.asyncio
async def test_non_http_schemes_are_refused_before_resolving():
    with patch(_RESOLVER, AsyncMock(return_value=True)) as resolver:
        assert await is_url_allowed("ftp://example.org/x") is False
        assert await is_url_allowed("javascript:alert(1)") is False

    resolver.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_malformed_url_is_refused_not_raised():
    with _not_public():
        assert await is_url_allowed("") is False
        assert await is_url_allowed("not a url") is False


def test_the_exception_set_is_explicit_and_small():
    """It is a security control — it should be readable at a glance."""
    assert INTERNAL_HOST_EXCEPTIONS == frozenset({"localhost", "127.0.0.1", "::1"})
