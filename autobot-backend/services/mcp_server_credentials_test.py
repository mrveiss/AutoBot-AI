# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for services.mcp_server_credentials (#11542)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.auth.connector_auth import ApiKeyAuth, BearerAuth
from services.mcp_external_servers import MCPServerConfig
from services.mcp_server_credentials import (
    build_auth_headers,
    resolve_auth_class,
    resolve_extra_headers_for_server,
)


class TestResolveAuthClass:
    def test_resolves_bearer_auth(self):
        assert resolve_auth_class("BearerAuth") is BearerAuth

    def test_resolves_api_key_auth(self):
        assert resolve_auth_class("ApiKeyAuth") is ApiKeyAuth

    def test_unknown_name_returns_none(self):
        assert resolve_auth_class("NotARealAuthType") is None

    def test_non_class_attribute_returns_none(self):
        """A name that resolves to something that isn't a type at all is rejected."""
        assert resolve_auth_class("validate_config_against_schema") is None


class TestBuildAuthHeaders:
    def test_bearer(self):
        assert build_auth_headers("BearerAuth", {"token": "tok123"}) == {"Authorization": "Bearer tok123"}

    def test_api_key_default_header(self):
        assert build_auth_headers("ApiKeyAuth", {"key": "k1"}) == {"X-Api-Key": "k1"}

    def test_api_key_custom_header(self):
        headers = build_auth_headers("ApiKeyAuth", {"key": "k1", "header": "X-Custom"})
        assert headers == {"X-Custom": "k1"}

    def test_basic_auth_encodes_credentials(self):
        import base64

        headers = build_auth_headers("BasicAuth", {"username": "admin", "password": "pw"})
        expected = "Basic " + base64.b64encode(b"admin:pw").decode("ascii")
        assert headers == {"Authorization": expected}

    def test_unsupported_auth_type_raises(self):
        with pytest.raises(ValueError, match="does not support"):
            build_auth_headers("OAuthRefreshAuth", {})


def _cfg(**overrides) -> MCPServerConfig:
    base = dict(server_id="s1", name="n", transport="streamable_http", owner_id="admin-1", url="https://x.example")
    base.update(overrides)
    return MCPServerConfig(**base)


class TestResolveExtraHeadersForServer:
    @pytest.mark.asyncio
    async def test_no_secret_returns_empty(self):
        cfg = _cfg(secret_id=None, auth_type=None)
        assert await resolve_extra_headers_for_server(cfg) == {}

    @pytest.mark.asyncio
    async def test_bearer_auth_decrypts_and_builds_header(self):
        cfg = _cfg(secret_id="sec-1", auth_type="BearerAuth", auth_config={})

        mock_store = AsyncMock()
        mock_store.load = AsyncMock(return_value={"token": "decrypted-tok"})

        with patch("knowledge.connectors.credential_store.get_credential_store", return_value=mock_store):
            headers = await resolve_extra_headers_for_server(cfg)

        assert headers == {"Authorization": "Bearer decrypted-tok"}
        mock_store.load.assert_awaited_once_with("sec-1", {}, BearerAuth, "admin-1")

    @pytest.mark.asyncio
    async def test_api_key_auth_merges_sanitized_auth_config(self):
        cfg = _cfg(secret_id="sec-1", auth_type="ApiKeyAuth", auth_config={"header": "X-Custom"})

        mock_store = AsyncMock()
        mock_store.load = AsyncMock(return_value={"header": "X-Custom", "key": "the-key"})

        with patch("knowledge.connectors.credential_store.get_credential_store", return_value=mock_store):
            headers = await resolve_extra_headers_for_server(cfg)

        assert headers == {"X-Custom": "the-key"}

    @pytest.mark.asyncio
    async def test_oauth_refresh_auth_uses_get_access_token(self):
        cfg = _cfg(secret_id="sec-1", auth_type="OAuthRefreshAuth")

        mock_store = AsyncMock()
        mock_store.get_access_token = AsyncMock(return_value="fresh-access-token")

        with patch("knowledge.connectors.credential_store.get_credential_store", return_value=mock_store):
            headers = await resolve_extra_headers_for_server(cfg)

        assert headers == {"Authorization": "Bearer fresh-access-token"}
        mock_store.get_access_token.assert_awaited_once_with("sec-1", "admin-1")

    @pytest.mark.asyncio
    async def test_unresolvable_auth_type_raises(self):
        cfg = _cfg(secret_id="sec-1", auth_type="TotallyMadeUpAuth")

        mock_store = AsyncMock()
        with patch("knowledge.connectors.credential_store.get_credential_store", return_value=mock_store):
            with pytest.raises(ValueError, match="unsupported auth_type"):
                await resolve_extra_headers_for_server(cfg)
