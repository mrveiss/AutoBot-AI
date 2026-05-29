# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for per-user voice bundle assignment endpoints (GH#8605).

Covers:
- GET /api/voice/bundles: list available bundles with tool counts
- GET /api/voice/users/{userId}/bundle: get user's bundle assignment (self/admin only)
- PUT /api/voice/users/{userId}/bundle: assign/clear bundle (self/admin only)
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


# Test users
_USER_ALICE = {"user_id": "alice", "username": "alice", "role": "user"}
_USER_BOB = {"user_id": "bob", "username": "bob", "role": "user"}
_ADMIN = {"user_id": "admin-user", "username": "admin", "role": "admin"}


@pytest.fixture()
def app():
    """Create FastAPI app with voice_bundle_user router and mocked dependencies."""
    app = FastAPI()
    app.include_router(router, prefix="/api/voice")
    return app


@pytest.fixture()
def client(app):
    """Create TestClient for the app."""
    return TestClient(app)


def _mock_get_current_user(user: dict):
    """Create a mock for get_current_user dependency."""
    async def _current_user():
        return user
    return _current_user


class TestListVoiceBundles:
    """Tests for GET /api/voice/bundles."""

    def test_list_bundles_user(self, client):
        """User can list available bundles."""
        with patch(
            "api.voice_bundle_user.get_current_user",
            _mock_get_current_user(_USER_ALICE),
        ):
            response = client.get("/api/voice/bundles")

        assert response.status_code == 200
        bundles = response.json()
        assert isinstance(bundles, list)
        assert len(bundles) > 0

        # Verify structure of each bundle
        for bundle in bundles:
            assert "name" in bundle
            assert "label" in bundle
            assert "tool_count" in bundle
            assert isinstance(bundle["tool_count"], int)

    def test_list_bundles_admin(self, client):
        """Admin can list bundles (should see all)."""
        with patch(
            "api.voice_bundle_user.get_current_user",
            _mock_get_current_user(_ADMIN),
        ):
            response = client.get("/api/voice/bundles")

        assert response.status_code == 200
        bundles = response.json()
        assert len(bundles) > 0


class TestGetUserBundle:
    """Tests for GET /api/voice/users/{userId}/bundle."""

    def test_get_own_bundle(self, client):
        """User can get their own bundle assignment."""
        with patch(
            "api.voice_bundle_user.get_current_user",
            _mock_get_current_user(_USER_ALICE),
        ), patch(
            "api.voice_bundle_user.get_async_session"
        ) as mock_session_ctx:
            # Mock database response
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

    def test_admin_can_get_other_bundle(self, client):
        """Admin can get any user's bundle assignment."""
        with patch(
            "api.voice_bundle_user.get_current_user",
            _mock_get_current_user(_ADMIN),
        ), patch(
            "api.voice_bundle_user.get_async_session"
        ) as mock_session_ctx:
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

    def test_user_cannot_access_other_bundle(self, client):
        """Non-admin user cannot access another user's bundle."""
        with patch(
            "api.voice_bundle_user.get_current_user",
            _mock_get_current_user(_USER_ALICE),
        ):
            response = client.get("/api/voice/users/bob/bundle")

        assert response.status_code == 403

    def test_get_bundle_not_assigned(self, client):
        """Getting bundle when none assigned returns null."""
        with patch(
            "api.voice_bundle_user.get_current_user",
            _mock_get_current_user(_USER_ALICE),
        ), patch(
            "api.voice_bundle_user.get_async_session"
        ) as mock_session_ctx:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_result = MagicMock()
            mock_result.fetchone.return_value = None  # No assignment
            mock_session.execute.return_value = mock_result
            mock_session_ctx.return_value.__aenter__.return_value = mock_session

            response = client.get("/api/voice/users/alice/bundle")

        assert response.status_code == 200
        data = response.json()
        assert data["bundle_name"] is None


class TestSetUserBundle:
    """Tests for PUT /api/voice/users/{userId}/bundle."""

    def test_assign_bundle_to_self(self, client):
        """User can assign a bundle to themselves."""
        with patch(
            "api.voice_bundle_user.get_current_user",
            _mock_get_current_user(_USER_ALICE),
        ), patch(
            "api.voice_bundle_user.get_async_session"
        ) as mock_session_ctx, patch(
            "api.voice_bundle_user.emit"
        ) as mock_emit:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_ctx.return_value.__aenter__.return_value = mock_session

            response = client.put(
                "/api/voice/users/alice/bundle",
                json={"bundle_name": "voice_extended"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "alice"
        assert data["bundle_name"] == "voice_extended"
        mock_session.commit.assert_called_once()
        mock_emit.assert_called_once()

    def test_admin_assigns_bundle_to_other_user(self, client):
        """Admin can assign a bundle to any user."""
        with patch(
            "api.voice_bundle_user.get_current_user",
            _mock_get_current_user(_ADMIN),
        ), patch(
            "api.voice_bundle_user.get_async_session"
        ) as mock_session_ctx, patch(
            "api.voice_bundle_user.emit"
        ) as mock_emit:
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

    def test_user_cannot_assign_to_other_user(self, client):
        """Non-admin user cannot assign bundle to another user."""
        with patch(
            "api.voice_bundle_user.get_current_user",
            _mock_get_current_user(_USER_ALICE),
        ):
            response = client.put(
                "/api/voice/users/bob/bundle",
                json={"bundle_name": "voice_extended"},
            )

        assert response.status_code == 403

    def test_clear_bundle_assignment(self, client):
        """User can clear their bundle assignment (set to None)."""
        with patch(
            "api.voice_bundle_user.get_current_user",
            _mock_get_current_user(_USER_ALICE),
        ), patch(
            "api.voice_bundle_user.get_async_session"
        ) as mock_session_ctx, patch(
            "api.voice_bundle_user.emit"
        ) as mock_emit:
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

    def test_invalid_bundle_name(self, client):
        """Assigning invalid bundle name fails."""
        with patch(
            "api.voice_bundle_user.get_current_user",
            _mock_get_current_user(_USER_ALICE),
        ):
            response = client.put(
                "/api/voice/users/alice/bundle",
                json={"bundle_name": "invalid_bundle"},
            )

        assert response.status_code == 422

    def test_user_cannot_assign_admin_bundle(self, client):
        """Non-admin user cannot assign voice_admin bundle."""
        with patch(
            "api.voice_bundle_user.get_current_user",
            _mock_get_current_user(_USER_ALICE),
        ):
            response = client.put(
                "/api/voice/users/alice/bundle",
                json={"bundle_name": "voice_admin"},
            )

        assert response.status_code == 403

    def test_admin_can_assign_admin_bundle(self, client):
        """Admin can assign voice_admin bundle."""
        with patch(
            "api.voice_bundle_user.get_current_user",
            _mock_get_current_user(_ADMIN),
        ), patch(
            "api.voice_bundle_user.get_async_session"
        ) as mock_session_ctx, patch(
            "api.voice_bundle_user.emit"
        ) as mock_emit:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_session_ctx.return_value.__aenter__.return_value = mock_session

            response = client.put(
                "/api/voice/users/bob/bundle",
                json={"bundle_name": "voice_admin"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["bundle_name"] == "voice_admin"
