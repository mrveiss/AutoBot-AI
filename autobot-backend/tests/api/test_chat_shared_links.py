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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.chat_shared_links import router
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.time_utils import now_utc

# Test users
_USER_ALICE = {"user_id": "alice", "username": "alice", "role": "user"}
_ADMIN = {"user_id": "admin-user", "username": "admin", "role": "admin"}
_SUPERADMIN = {"user_id": "root", "username": "root", "role": "superadmin"}

# Holds the user the patched auth middleware returns for the current test.
_CURRENT: dict = {"user": None}


@pytest.fixture(autouse=True)
def _patch_auth_middleware():
    """Make require_role() (#12704) see the injected test user.

    The admin cross-user route uses ``require_role("admin", "superadmin")``,
    which reads the user via ``auth_rbac.get_auth_middleware()``.
    """
    mw = MagicMock()
    mw.get_user_from_request.side_effect = lambda request: _CURRENT["user"]
    with patch("auth_rbac.get_auth_middleware", return_value=mw):
        yield
    _CURRENT["user"] = None


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

    The admin cross-user route uses ``require_role("admin", "superadmin")``
    (#12704), fed by the autouse middleware patch; ``get_current_user`` (the
    owner-scoped routes) is overridden so admin routes 200 for admin/superadmin
    and 403 for others.
    """
    _CURRENT["user"] = user
    app = FastAPI()
    app.include_router(router)

    async def _override_user():
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

    def test_superadmin_lists_all_active_links(self):
        """superadmin reaches the admin cross-user view — previously admin-only (#12704)."""
        client = _make_client(_SUPERADMIN, [_make_link(owner="alice", session_id="sess-a")])

        response = client.get("/chat/shared-links/admin")

        assert response.status_code == 200
        assert response.json()["data"]["count"] == 1

    def test_non_admin_cannot_list_all_links(self):
        """Non-admin user receives 403."""
        client = _make_client(_USER_ALICE, [_make_link(owner="alice", session_id="sess-a")])

        response = client.get("/chat/shared-links/admin")

        assert response.status_code == 403


class TestSharedLinkResponseSerialization:
    """Regression: every success response must be `.model_dump()`'d to a dict.

    Each endpoint declares ``response_model=Dict[str, Any]`` but returned the
    ``DataResponse`` Pydantic model un-dumped, which FastAPI rejects with
    ResponseValidationError → 500 on success. This guards the owner-scoped list
    endpoint (representative of the create/revoke/access/session siblings).
    """

    def test_owner_list_serializes_to_200(self):
        client = _make_client(_USER_ALICE, [_make_link(owner="alice", session_id="sess-a")])

        with (
            patch("api.chat_shared_links.SessionOwnershipValidator") as MockValidator,
            patch(
                "autobot_shared.redis_client.get_redis_client",
                new=AsyncMock(return_value=MagicMock()),
            ),
        ):
            MockValidator.return_value.get_session_owner = AsyncMock(return_value="alice")
            response = client.get("/chat/sessions/sess-a/share-links")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["count"] == 1
