# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for per-user voice bundle assignment endpoints (GH#8605, GH#8969).

Covers:
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
    BundleAssignRequest,
    BundleInfo,
    UserBundleResponse,
    router,
)
from auth_middleware import get_current_user

# Test users
_USER_ALICE = {"user_id": "alice", "username": "alice", "role": "user"}
_USER_BOB = {"user_id": "bob", "username": "bob", "role": "user"}
_ADMIN = {"user_id": "admin-user", "username": "admin", "role": "admin"}


def _make_client(user: dict) -> TestClient:
    """Create a TestClient with dependency_overrides for get_current_user."""
    app = FastAPI()
    app.include_router(router, prefix="/api/voice")

    async def _override():
        return user

    app.dependency_overrides[get_current_user] = _override
    return TestClient(app)


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
            patch("services.audit.unified_audit.emit") as mock_emit,
        ):
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_ctx.return_value.__aenter__.return_value = mock_session

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
            patch("services.audit.unified_audit.emit") as mock_emit,
        ):
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_ctx.return_value.__aenter__.return_value = mock_session

            response = client.put(
                "/api/voice/users/alice/bundle",
                json={"bundle_name": None},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "alice"
        assert data["bundle_name"] is None
        mock_session.execute.assert_called_once()
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
            patch("services.audit.unified_audit.emit") as mock_emit,
        ):
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_ctx.return_value.__aenter__.return_value = mock_session

            response = client.put(
                "/api/voice/users/bob/bundle",
                json={"bundle_name": "voice_admin"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["bundle_name"] == "voice_admin"
        mock_emit.assert_called_once()
