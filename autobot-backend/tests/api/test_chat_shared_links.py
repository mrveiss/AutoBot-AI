# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for shared chat link endpoints (GH#8996).

Covers the admin cross-user view (AC4):
- GET /chat/shared-links/admin: admin lists all active, non-expired links
  across all users; non-admin receives 403.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.chat_shared_links import router
from api.user_management.dependencies import get_db_session
from api.voice_bundle_helpers import _require_admin
from auth_middleware import get_current_user
from autobot_shared.time_utils import now_utc
from utils.catalog_http_exceptions import raise_auth_error

# Test users
_USER_ALICE = {"user_id": "alice", "username": "alice", "role": "user"}
_ADMIN = {"user_id": "admin-user", "username": "admin", "role": "admin"}


def _make_link(*, owner: str, session_id: str, has_password: bool = False, expired: bool = False):
    """Build a MagicMock that quacks like a ChatSharedLink ORM row."""
    link = MagicMock()
    link.id = f"id-{owner}-{session_id}"
    link.token = f"tok-{owner}-{session_id}"
    link.session_id = session_id
    link.created_by = owner
    link.has_password = has_password
    link.is_active = True
    link.is_expired = expired
    link.created_at = now_utc()
    link.expires_at = (now_utc() - timedelta(hours=1)) if expired else None
    return link


def _make_client(user: dict, links: list) -> TestClient:
    """Create a TestClient overriding auth + DB session.

    Admin routes depend on ``_require_admin`` (a Request-based middleware check),
    so override it too — role-gated against the injected user so the admin route
    200s for admins and 403s for non-admins.
    """
    app = FastAPI()
    app.include_router(router)

    async def _override_user():
        return user

    def _override_require_admin() -> dict:
        if user.get("role") != "admin":
            raise_auth_error("AUTH_0003", "Admin permission required")
        return user

    async def _override_db():
        session = AsyncMock(spec=AsyncSession)
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = links
        result.scalars.return_value = scalars
        session.execute.return_value = result
        return session

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[_require_admin] = _override_require_admin
    app.dependency_overrides[get_db_session] = _override_db
    return TestClient(app)


class TestAdminListAllSharedLinks:
    """GET /chat/shared-links/admin (GH#8996, AC4)."""

    def test_admin_lists_all_active_links(self):
        """Admin sees active, non-expired links across all users; expired excluded."""
        links = [
            _make_link(owner="alice", session_id="sess-a"),
            _make_link(owner="bob", session_id="sess-b", has_password=True),
            _make_link(owner="carol", session_id="sess-c", expired=True),
        ]
        client = _make_client(_ADMIN, links)

        response = client.get("/chat/shared-links/admin")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        # The expired link is filtered out; two active links remain across owners.
        assert data["count"] == 2
        owners = {item["owner"] for item in data["links"]}
        assert owners == {"alice", "bob"}
        protected = {item["owner"]: item["has_password"] for item in data["links"]}
        assert protected["bob"] is True
        assert protected["alice"] is False

    def test_non_admin_cannot_list_all_links(self):
        """Non-admin user receives 403."""
        client = _make_client(_USER_ALICE, [_make_link(owner="alice", session_id="sess-a")])

        response = client.get("/chat/shared-links/admin")

        assert response.status_code == 403
