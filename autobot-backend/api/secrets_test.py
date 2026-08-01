# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the legacy Redis chat-secrets API surface (api/secrets.py).

Pins the GET /api/secrets/types response (scope + type option lists) so the
#11759 rename of the chat-secrets scope enum (``SecretScope`` ->
``ChatSecretScope``) provably does not change any served values, and asserts
the renamed enum stays distinct from the canonical authorization
``ScopeLevel`` (#11290).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas_system import ChatSecretScope, SecretType
from autobot_shared.scoping.scope_level import ScopeLevel

# Exact response content served by GET /api/secrets/types — order and
# strings pinned; the #11759 rename must not change any of this.
EXPECTED_SCOPES = [
    {"value": "chat", "label": "Chat"},
    {"value": "general", "label": "General"},
    {"value": "user", "label": "User"},
    {"value": "session", "label": "Session"},
    {"value": "shared", "label": "Shared"},
    {"value": "group", "label": "Group"},
    {"value": "organization", "label": "Organization"},
]

EXPECTED_TYPES = [
    {"value": "ssh_key", "label": "Ssh Key"},
    {"value": "password", "label": "Password"},
    {"value": "api_key", "label": "Api Key"},
    {"value": "token", "label": "Token"},
    {"value": "certificate", "label": "Certificate"},
    {"value": "database_url", "label": "Database Url"},
    {"value": "infrastructure_host", "label": "Infrastructure Host"},
    {"value": "other", "label": "Other"},
]


class TestChatSecretScopeEnum:
    """The chat-secrets scope enum after the #11759 rename."""

    def test_members_and_values_pinned(self):
        assert [(m.name, m.value) for m in ChatSecretScope] == [
            ("CHAT", "chat"),
            ("GENERAL", "general"),
            ("USER", "user"),
            ("SESSION", "session"),
            ("SHARED", "shared"),
            ("GROUP", "group"),
            ("ORGANIZATION", "organization"),
        ]

    def test_distinct_from_canonical_scope_level(self):
        """ChatSecretScope must never be conflated with ScopeLevel (#11759)."""
        assert ChatSecretScope is not ScopeLevel
        assert "chat" not in {level.value for level in ScopeLevel}
        assert "workflow" not in {scope.value for scope in ChatSecretScope}

    def test_secret_type_values_pinned(self):
        assert [t.value for t in SecretType] == [t["value"] for t in EXPECTED_TYPES]


@pytest.mark.asyncio
async def test_get_secret_types_response_pinned():
    """GET /api/secrets/types serves identical content after the rename."""
    from api.secrets import get_secret_types

    response = await get_secret_types(admin_check=True)
    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload == {"types": EXPECTED_TYPES, "scopes": EXPECTED_SCOPES}


class TestCheckRateLimit:
    """check_rate_limit() delegates to the shared RateLimiter's custom
    single-window mode (window=60s, max=30) — migrated off the retired
    local in-memory class (#12646). No coverage previously existed."""

    def _fake_request(self, host: str) -> MagicMock:
        from fastapi import Request

        request = MagicMock(spec=Request)
        request.client = MagicMock(host=host)
        request.headers = {}
        return request

    @pytest.mark.asyncio
    async def test_allows_when_under_limit(self):
        from api.secrets import check_rate_limit

        with patch("autobot_shared.rate_limiter.get_async_redis_client", AsyncMock(return_value=None)):
            await check_rate_limit(self._fake_request("203.0.113.5"))  # must not raise

    @pytest.mark.asyncio
    async def test_raises_429_with_retry_after_when_denied(self):
        from fastapi import HTTPException

        from api.secrets import RATE_LIMIT_WINDOW, check_rate_limit

        redis = AsyncMock()
        redis.eval = AsyncMock(return_value=[0, "5"])

        with patch("autobot_shared.rate_limiter.get_async_redis_client", AsyncMock(return_value=redis)):
            with pytest.raises(HTTPException) as exc_info:
                await check_rate_limit(self._fake_request("203.0.113.6"))

        assert exc_info.value.status_code == 429
        assert exc_info.value.headers["Retry-After"] == str(RATE_LIMIT_WINDOW)


class TestGetSecretDualRead:
    """``_get_secret_dual_read`` (#10088 Task 3): unified store first, legacy file fallback.

    Mocks ``load_imported_json_secret`` directly — no Postgres needed here; the envelope
    read itself is covered by the Postgres-gated ``tests/migrations/test_json_secrets_importer.py``.
    """

    @pytest.mark.asyncio
    async def test_returns_unified_secret_without_touching_legacy_file(self):
        from api.secrets import _get_secret_dual_read

        unified = {"id": "s1", "scope": "general", "chat_id": None, "value": "v"}
        with (
            patch("api.secrets.load_imported_json_secret", AsyncMock(return_value=unified)),
            patch("api.secrets.secrets_manager") as legacy,
        ):
            result = await _get_secret_dual_read("s1", chat_id=None)
        assert result == unified
        legacy.get_secret.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_legacy_file_when_not_yet_imported(self):
        from api.secrets import _get_secret_dual_read

        legacy_result = {"id": "s2", "scope": "general", "value": "v2"}
        with (
            patch("api.secrets.load_imported_json_secret", AsyncMock(return_value=None)),
            patch("api.secrets.secrets_manager") as legacy,
        ):
            legacy.get_secret = MagicMock(return_value=legacy_result)
            result = await _get_secret_dual_read("s2", chat_id=None)
        assert result == legacy_result
        legacy.get_secret.assert_called_once_with("s2", chat_id=None)

    @pytest.mark.asyncio
    async def test_chat_scope_mismatch_denied_even_via_unified_store(self):
        from api.secrets import _get_secret_dual_read

        unified = {"id": "s3", "scope": "chat", "chat_id": "chat-a", "value": "v3"}
        with patch("api.secrets.load_imported_json_secret", AsyncMock(return_value=unified)):
            with pytest.raises(PermissionError):
                await _get_secret_dual_read("s3", chat_id="chat-b")
