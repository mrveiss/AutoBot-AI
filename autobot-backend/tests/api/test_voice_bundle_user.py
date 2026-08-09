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

from api.voice_bundle_user import (
    _check_self_or_admin,
    _get_user_id,
    _is_admin,
    router,
)
from auth_middleware import get_current_user

# Test users
_USER_ALICE = {"user_id": "alice", "username": "alice", "role": "user"}
_USER_BOB = {"user_id": "bob", "username": "bob", "role": "user"}
_ADMIN = {"user_id": "admin-user", "username": "admin", "role": "admin"}
_SUPERADMIN = {"user_id": "root", "username": "root", "role": "superadmin"}

# Holds the user the patched auth middleware returns for the current test.
_CURRENT: dict = {"user": None}


@pytest.fixture(autouse=True)
def _patch_auth_middleware():
    """Make the canonical require_role() gate see the injected test user.

    Admin-gated routes use ``require_role("admin", "superadmin")`` (#12704),
    which reads the user via ``auth_rbac.get_auth_middleware()``.
    """
    mw = MagicMock()
    mw.get_user_from_request.side_effect = lambda request: _CURRENT["user"]
    with patch("auth_rbac.get_auth_middleware", return_value=mw):
        yield
    _CURRENT["user"] = None


def _make_client(user: dict) -> TestClient:
    """Create a TestClient with the injected user wired into auth.

    ``get_current_user`` (the acting-user dict) is overridden, and the
    ``require_role()`` gate reads the same user via the autouse middleware
    patch, so admin routes 200 for admin/superadmin and 403 for others.
    """
    _CURRENT["user"] = user
    app = FastAPI()
    app.include_router(router, prefix="/api/voice")

    async def _override():
        return user

    app.dependency_overrides[get_current_user] = _override
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

        with patch("user_management.database.db_session_context") as mock_session_ctx:
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

        with patch("user_management.database.db_session_context") as mock_session_ctx:
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

        with patch("user_management.database.db_session_context") as mock_session_ctx:
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
            patch("user_management.database.db_session_context") as mock_session_ctx,
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
            patch("user_management.database.db_session_context") as mock_session_ctx,
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

    def test_superadmin_assigns_bundle_to_user(self):
        """superadmin can assign a bundle — previously admin-only (#12704 unlock)."""
        client = _make_client(_SUPERADMIN)

        with (
            patch("user_management.database.db_session_context") as mock_session_ctx,
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
        assert data["bundle_name"] == "voice_safe"
        mock_emit.assert_called_once()

    def test_admin_can_assign_admin_bundle(self):
        """Admin can assign voice_admin bundle."""
        client = _make_client(_ADMIN)

        with (
            patch("user_management.database.db_session_context") as mock_session_ctx,
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


class TestSuperadminIsNotLockedOut:
    """#12717: superadmin must count as admin on the READ paths too.

    The write path (PUT /voice/users/{id}/bundle) has always been guarded by
    require_role("admin", "superadmin"), so a superadmin could ASSIGN a bundle
    but then got 403 reading it back — the read path went through _is_admin,
    which only accepted "admin". Same class as #12704.
    """

    def test_is_admin_accepts_superadmin(self):
        from api.voice_bundle_user import _is_admin

        assert _is_admin({"role": "superadmin"}) is True
        assert _is_admin({"role": "admin"}) is True

    def test_is_admin_still_rejects_ordinary_roles(self):
        from api.voice_bundle_user import _is_admin

        for role in ("user", "readonly", "operator", "analyst", "editor"):
            assert _is_admin({"role": role}) is False, role
        assert _is_admin({}) is False
        assert _is_admin({"role": None}) is False

    def test_is_admin_is_case_insensitive_like_require_role(self):
        """auth_rbac.require_role lowercases both sides; this must match, or a
        'SuperAdmin' token would pass the write guard and fail the read."""
        from api.voice_bundle_user import _is_admin

        assert _is_admin({"role": "SuperAdmin"}) is True
        assert _is_admin({"role": "ADMIN"}) is True

    def test_superadmin_can_read_another_users_bundle(self):
        """_check_self_or_admin is what the GET actually calls."""
        from unittest.mock import MagicMock

        from api.voice_bundle_user import _check_self_or_admin

        superadmin = {"role": "superadmin", "user_id": "admin-1"}
        assert _check_self_or_admin(MagicMock(), superadmin, "some-other-user") is True

    def test_ordinary_user_still_cannot_read_another_users_bundle(self):
        from unittest.mock import MagicMock

        from api.voice_bundle_user import _check_self_or_admin

        plain = {"role": "user", "user_id": "user-1"}
        assert _check_self_or_admin(MagicMock(), plain, "user-2") is False
        assert _check_self_or_admin(MagicMock(), plain, "user-1") is True


class TestSessionAcquisitionIsAContextManager:
    """#13364: the voice-bundle endpoints must open sessions with a real
    async context manager.

    Every other test in this file patches the session helper with a mock that
    implements ``__aenter__``, so they pass whatever the production code calls —
    which is exactly how this shipped. ``get_async_session`` is an undecorated
    async *generator* (a FastAPI ``Depends`` dependency); ``async with`` on it
    raises ``AttributeError: __aenter__``, and the endpoints' ``except
    Exception`` turned that into an unconditional ``500 Database error``. All
    four sites were dead on arrival in production and green in CI.

    These tests use the real objects, so they fail if the endpoints go back to
    the generator.
    """

    def test_db_session_context_supports_async_with(self):
        from user_management.database import db_session_context

        cm = db_session_context()
        assert hasattr(cm, "__aenter__"), "db_session_context must be usable with 'async with'"
        assert hasattr(cm, "__aexit__")

    def test_get_async_session_does_not_support_async_with(self):
        """Documents *why* the endpoints must not use it — it is a Depends generator."""
        from user_management.database import get_async_session

        gen = get_async_session()
        assert not hasattr(gen, "__aenter__"), (
            "get_async_session gained __aenter__; if it is now a context manager this test "
            "and the #13364 comments in the voice-bundle endpoints should be revisited"
        )

    def test_voice_bundle_endpoints_do_not_async_with_the_generator(self):
        """Source-level guard: neither module may 'async with' the Depends generator."""
        from pathlib import Path

        import api.voice_bundle_admin as admin_mod
        import api.voice_bundle_user as user_mod

        for module in (admin_mod, user_mod):
            source = Path(module.__file__).read_text(encoding="utf-8")
            assert "async with get_async_session()" not in source, (
                f"{Path(module.__file__).name} opens a session with the Depends generator; "
                "use db_session_context() (#13364)"
            )
            assert "async with db_session_context()" in source
