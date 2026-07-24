# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSRF guards on provider-auth outbound token/device endpoints (#12278).

Proves the guards protecting the CodeQL ``py/full-ssrf`` sinks in
``api/provider_auth.py`` (exchange_code + device POSTs):
- ``_validate_outbound_url`` rejects non-https, IP-literal (loopback / RFC1918 /
  link-local metadata) and non-allowlisted hosts, and accepts allowlisted https.
- ``_pinned_connector`` rejects an allowlisted host that RESOLVES to a private
  address (DNS-rebind), and pins the public IP otherwise.
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api import provider_auth as mod


def _allow(monkeypatch):
    monkeypatch.setattr(mod, "get_oauth_allowed_hosts", lambda: {"token.example.com"})


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://169.254.169.254/token",  # AWS/Azure/GCP metadata (link-local)
        "https://127.0.0.1/token",  # loopback
        "https://10.0.0.1/token",  # RFC1918
        "http://token.example.com/token",  # not https
        "https://evil.example.com/token",  # not allowlisted
    ],
)
def test_validate_outbound_url_blocks_unsafe(monkeypatch, bad_url):
    _allow(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        mod._validate_outbound_url(bad_url)
    assert exc.value.status_code == 400


def test_validate_outbound_url_allows_allowlisted_https(monkeypatch):
    _allow(monkeypatch)
    mod._validate_outbound_url("https://token.example.com/token")  # must not raise


@pytest.mark.asyncio
async def test_pinned_connector_blocks_dns_rebind_to_private(monkeypatch):
    """Allowlisted host resolving to a private IP must be blocked (rebind)."""
    fake_infos = [(2, 1, 6, "", ("10.0.0.1", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(HTTPException) as exc:
            await mod._pinned_connector("https://token.example.com/token")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_pinned_connector_blocks_metadata_ip(monkeypatch):
    fake_infos = [(2, 1, 6, "", ("169.254.169.254", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        with pytest.raises(HTTPException):
            await mod._pinned_connector("https://token.example.com/token")


@pytest.mark.asyncio
async def test_pinned_connector_pins_public_ip(monkeypatch):
    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        connector = await mod._pinned_connector("https://token.example.com/token")
    try:
        results = await connector._resolver.resolve("token.example.com", 443)
        assert results[0]["host"] == "93.184.216.34"
    finally:
        await connector.close()
