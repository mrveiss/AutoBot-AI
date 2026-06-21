# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for per-user voice bundle assignment endpoints (GH#8605, GH#8969, GH#9113).

Covers:
- Helper functions: _is_admin, _get_user_id, _check_self_or_admin, _count_tools_for_bundle
- GET /api/voice/bundles: list available bundles with tool counts
- GET /api/voice/users/{userId}/bundle: get user's bundle assignment (self/admin only)
- PUT /api/voice/users/{userId}/bundle: assign/clear bundle (admin only — GH#8969)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.voice_bundle_helpers import _require_admin
from api.voice_bundle_user import (
    _check_self_or_admin,
    _get_user_id,
    _is_admin,
    router,
)
from auth_middleware import get_current_user
from utils.catalog_http_exceptions import raise_auth_error

# Test users
_USER_ALICE = {"user_id": "alice", "username": "alice", "role": "user"}
_USER_BOB = {"user_id": "bob", "username": "bob", "role": "user"}
_ADMIN = {"user_id": "admin-user", "username": "admin", "role": "admin"}


def _make_client(user: dict) -> TestClient:
    """Create a TestClient with dependency_overrides for get_current_user.

    Admin-gated routes depend on ``_require_admin`` (a Request-based middleware
    check, GH#9450) rather than ``get_current_user``, so override it too —
    role-gated against the injected user so admin routes 200 for admins and
    403 for non-admins (GH#8977).
    """
    app = FastAPI()
    app.include_router(router, prefix="/api/voice")

    async def _override():
        return user

    def _override_require_admin() -> dict:
        if user.get("role") != "admin":
            raise_auth_error("AUTH_0003", "Admin permission required")
        return user

    app.dependency_overrides[get_current_user] = _override
    app.dependency_overrides[_require_admin] = _override_require_admin
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper function unit tests (GH#9113)
# ---------------------------------------------------------------------------


class TestIsAdmin:
    def test_admin_role_returns_true(self):
        assert _is_admin({"role": "admin"}) is True

    def test_user_role_returns_false(self):
        assert _is_admin({"role": "user"}) is False

    def test_missing_role_returns_false(self):
        assert _is_admin({}) is False

    def test_other_role_returns_false(self):
        assert _is_admin({"role": "moderator"}) is False


class TestGetUserId:
    def test_user_id_field(self):
        assert _get_user_id({"user_id": "alice"}) == "alice"

    def test_sub_field_fallback(self):
        assert _get_user_id({"sub": "bob"}) == "bob"

    def test_username_field_fallback(self):
        assert _get_user_id({"username": "carol"}) == "carol"

    def test_user_id_takes_precedence_over_sub(self):
        assert _get_user_id({"user_id": "alice", "sub": "alice-sub"}) == "alice"

    def test_empty_dict_returns_unknown(self):
        assert _get_user_id({}) == "unknown"


class TestCheckSelfOrAdmin:
    """_check_self_or_admin is a security gate — must be tested thoroughly."""

    def _make_request(self):
        return MagicMock()

    def test_user_accessing_own_id_allowed(self):
        user = {"user_id": "alice", "role": "user"}
        assert _check_self_or_admin(self._make_request(), user, "alice") is True

    def test_user_accessing_other_id_denied(self):
        user = {"user_id": "alice", "role": "user"}
        assert _check_self_or_admin(self._make_request(), user, "bob") is False

    def test_admin_accessing_own_id_allowed(self):
        user = {"user_id": "admin-user", "role": "admin"}
        assert _check_self_or_admin(self._make_request(), user, "admin-user") is True

    def test_admin_accessing_other_id_allowed(self):
        user = {"user_id": "admin-user", "role": "admin"}
        assert _check_self_or_admin(self._make_request(), user, "alice") is True

    def test_sub_field_used_when_no_user_id(self):
        user = {"sub": "alice", "role": "user"}
        assert _check_self_or_admin(self._make_request(), user, "alice") is True
        assert _check_self_or_admin(self._make_request(), user, "bob") is False


class TestCountToolsForBundle:
    @pytest.mark.asyncio
    async def test_count_tools_returns_integer(self):
        from api.voice_bundle_helpers import _count_tools_for_bundle, _tool_count_cache

        _tool_count_cache.clear()

        mock_matrix = {"tool_a": {}, "tool_b": {}, "tool_c": {}}

        def mock_filter(tools, bundle, is_admin):
            return tools[:2]

        with (
            patch("api.redis_mcp.rbac.TOOL_ACCESS_MATRIX", mock_matrix),
            patch("api.redis_mcp.rbac.filter_tools_for_bundle", mock_filter),
        ):
            count = await _count_tools_for_bundle("voice_safe", is_admin=False)

        assert count == 2

    @pytest.mark.asyncio
    async def test_count_tools_result_cached(self):
        from api.voice_bundle_helpers import _count_tools_for_bundle, _tool_count_cache

        _tool_count_cache.clear()
        call_count = 0
        mock_matrix = {"tool_x": {}}

        def counting_filter(tools, bundle, is_admin):
            nonlocal call_count
            call_count += 1
            return tools

        with (
            patch("api.redis_mcp.rbac.TOOL_ACCESS_MATRIX", mock_matrix),
            patch("api.redis_mcp.rbac.filter_tools_for_bundle", counting_filter),
        ):
            await _count_tools_for_bundle("voice_extended", is_admin=True)
            await _count_tools_for_bundle("voice_extended", is_admin=True)

        assert call_count == 1  # second call used cache


class TestListVoiceBundles:
    """Tests for GET /api/voice/bundles."""

    def test_list_bundles_user(self):
        """User can list available bundles."""
        client = _make_client(_USER_ALICE)
        response = client.get("/api/voice/bundles")

        assert response.status_code == 200
        bundles = response.json()
        assert isinstance(bundles, list)
        assert len(bundles) > 0

        for bundle in bundles:
            assert "name" in bundle
            assert "label" in bundle
            assert "tool_count" in bundle
            assert isinstance(bundle["tool_count"], int)

    def test_list_bundles_admin(self):
        """Admin can list bundles (should see all)."""
        client = _make_client(_ADMIN)
        response = client.get("/api/voice/bundles")

        assert response.status_code == 200
        bundles = response.json()
        assert len(bundles) > 0


class TestGetUserBundle:
    """Tests for GET /api/voice/users/{userId}/bundle."""

    def test_get_own_bundle(self):
        """User can get their own bundle assignment."""
        client = _make_client(_USER_ALICE)

        with patch("user_management.database.get_async_session") as mock_session_ctx:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_result = MagicMock()
            mock_result.fetchone.return_value = ("voice_extended",)
            mock_session.execute.return_value = mock_result
            mock_session_ctx.return_value.__aenter__.return_value = mock_session

            response = client.get("/api/voice/users/alice/bundle")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "alice"
        assert data["bundle_name"] == "voice_extended"

    def test_admin_can_get_other_bundle(self):
        """Admin can get any user's bundle assignment."""
        client = _make_client(_ADMIN)

        with patch("user_management.database.get_async_session") as mock_session_ctx:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_result = MagicMock()
            mock_result.fetchone.return_value = ("voice_admin",)
            mock_session.execute.return_value = mock_result
            mock_session_ctx.return_value.__aenter__.return_value = mock_session

            response = client.get("/api/voice/users/bob/bundle")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "bob"
        assert data["bundle_name"] == "voice_admin"

    def test_user_cannot_access_other_bundle(self):
        """Non-admin user cannot access another user's bundle."""
        client = _make_client(_USER_ALICE)
        response = client.get("/api/voice/users/bob/bundle")

        assert response.status_code == 403

    def test_get_bundle_not_assigned(self):
        """Getting bundle when none assigned returns null."""
        client = _make_client(_USER_ALICE)

        with patch("user_management.database.get_async_session") as mock_session_ctx:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_result = MagicMock()
            mock_result.fetchone.return_value = None
            mock_session.execute.return_value = mock_result
            mock_session_ctx.return_value.__aenter__.return_value = mock_session

            response = client.get("/api/voice/users/alice/bundle")

        assert response.status_code == 200
        data = response.json()
        assert data["bundle_name"] is None


class TestSetUserBundle:
    """Tests for PUT /api/voice/users/{userId}/bundle.

    PUT is admin-only (GH#8969 — privilege escalation fix).
    """

    def test_non_admin_cannot_self_assign_bundle(self):
        """Non-admin user cannot assign a bundle to themselves (GH#8969)."""
        client = _make_client(_USER_ALICE)
        response = client.put(
            "/api/voice/users/alice/bundle",
            json={"bundle_name": "voice_extended"},
        )

        assert response.status_code == 403

    def test_non_admin_cannot_self_clear_bundle(self):
        """Non-admin user cannot clear their own bundle assignment (admin-only operation)."""
        client = _make_client(_USER_ALICE)
        response = client.put(
            "/api/voice/users/alice/bundle",
            json={"bundle_name": None},
        )

        assert response.status_code == 403

    def test_user_cannot_assign_to_other_user(self):
        """Non-admin user cannot assign bundle to another user."""
        client = _make_client(_USER_ALICE)
        response = client.put(
            "/api/voice/users/bob/bundle",
            json={"bundle_name": "voice_extended"},
        )

        assert response.status_code == 403

    def test_admin_assigns_bundle_to_user(self):
        """Admin can assign a bundle to any user."""
        client = _make_client(_ADMIN)

        with (
            patch("user_management.database.get_async_session") as mock_session_ctx,
            patch("api.voice_bundle_user.emit") as mock_emit,
        ):
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_ctx.return_value.__aenter__.return_value = mock_session
            mock_result = MagicMock()
            mock_result.fetchone.return_value = ("voice_safe",)
            mock_session.execute.return_value = mock_result

            response = client.put(
                "/api/voice/users/bob/bundle",
                json={"bundle_name": "voice_safe"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "bob"
        assert data["bundle_name"] == "voice_safe"
        mock_session.commit.assert_called_once()
        mock_emit.assert_called_once()

    def test_admin_clears_bundle_for_user(self):
        """Admin can clear a user's bundle assignment."""
        client = _make_client(_ADMIN)

        with (
            patch("user_management.database.get_async_session") as mock_session_ctx,
            patch("api.voice_bundle_user.emit") as mock_emit,
        ):
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_ctx.return_value.__aenter__.return_value = mock_session
            mock_result = MagicMock()
            mock_result.fetchone.return_value = None
            mock_session.execute.return_value = mock_result

            response = client.put(
                "/api/voice/users/alice/bundle",
                json={"bundle_name": None},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "alice"
        assert data["bundle_name"] is None
        mock_emit.assert_called_once()

    def test_invalid_bundle_name(self):
        """Admin assigning invalid bundle name fails with 422."""
        client = _make_client(_ADMIN)
        response = client.put(
            "/api/voice/users/alice/bundle",
            json={"bundle_name": "invalid_bundle"},
        )

        assert response.status_code == 422

    def test_user_cannot_assign_admin_bundle(self):
        """Non-admin user cannot assign voice_admin bundle."""
        client = _make_client(_USER_ALICE)
        response = client.put(
            "/api/voice/users/alice/bundle",
            json={"bundle_name": "voice_admin"},
        )

        assert response.status_code == 403

    def test_admin_can_assign_admin_bundle(self):
        """Admin can assign voice_admin bundle."""
        client = _make_client(_ADMIN)

        with (
            patch("user_management.database.get_async_session") as mock_session_ctx,
            patch("api.voice_bundle_user.emit") as mock_emit,
        ):
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_ctx.return_value.__aenter__.return_value = mock_session
            mock_result = MagicMock()
            mock_result.fetchone.return_value = ("voice_admin",)
            mock_session.execute.return_value = mock_result

            response = client.put(
                "/api/voice/users/bob/bundle",
                json={"bundle_name": "voice_admin"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["bundle_name"] == "voice_admin"
        mock_emit.assert_called_once()
