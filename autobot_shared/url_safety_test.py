# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Contract tests for ``autobot_shared.url_safety`` (#7477).

Validates the extracted SSRF guard. The full-coverage tests for the
``LinkPipeline._is_public_url`` method (28 tests) still live in
``autobot-backend/media/link/pipeline_test.py`` and validate the same
function via the backward-compat method wrapper. These tests pin the
import-isolation contract that motivated the extraction.
"""

from __future__ import annotations

import ipaddress
from unittest.mock import patch

import pytest

from autobot_shared.url_safety import is_public_url, is_public_url_async

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
# Import-isolation contract (the whole point of #7477)
# ---------------------------------------------------------------------------


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
