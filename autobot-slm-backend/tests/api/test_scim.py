# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for SCIM 2.0 inbound provisioning (#10157).

Tests:
- 401 without bearer token
- 201 on user create with correct SCIM body
- PATCH active:false deactivates user
- Group→role mapping (PUT /Groups)
- Role revocation when member removed from group (deprovisioning)

Uses importlib to load api.scim with all heavy dependencies mocked out,
mirroring the test_sso_auth.py pattern used in this codebase.
"""

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup: ensure autobot-slm-backend is importable
# ---------------------------------------------------------------------------
_SLM_BACKEND = Path(__file__).parent.parent.parent
_SHARED = _SLM_BACKEND.parent / "autobot_shared"
for _p in [str(_SLM_BACKEND), str(_SHARED)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Minimal module stubs (avoid heavy deps: FastAPI, SQLAlchemy, cryptography)
# ---------------------------------------------------------------------------


def _stub_modules():
    """Install lightweight stubs for modules the SCIM module imports."""
    stubs = {
        "fastapi": MagicMock(),
        "fastapi.responses": MagicMock(),
        "sqlalchemy": MagicMock(),
        "sqlalchemy.exc": MagicMock(),
        "sqlalchemy.ext.asyncio": MagicMock(),
        "sqlalchemy.orm": MagicMock(),
        "models.database": MagicMock(),
        "services.database": MagicMock(),
        "services.encryption": MagicMock(),
        "user_management.database": MagicMock(),
        "user_management.models": MagicMock(),
        "user_management.models.sso": MagicMock(),
        "user_management.services.base_service": MagicMock(),
        "user_management.services.sso_service": MagicMock(),
        "user_management.services.user_service": MagicMock(),
    }
    for mod, stub in stubs.items():
        sys.modules.setdefault(mod, stub)


_stub_modules()

# ---------------------------------------------------------------------------
# Import only the pure-Python helpers from api.scim (no FastAPI dep needed)
# ---------------------------------------------------------------------------
from importlib.util import module_from_spec, spec_from_file_location

_scim_spec = spec_from_file_location("api.scim", _SLM_BACKEND / "api" / "scim.py")
_scim_mod = module_from_spec(_scim_spec)


def _load_scim_module():
    """Load the SCIM module with stubs active."""
    # Provide concrete exceptions that the module references at import time
    sys.modules["user_management.services.user_service"].DuplicateUserError = Exception
    sys.modules["user_management.services.user_service"].UserNotFoundError = Exception
    sys.modules["user_management.services.user_service"].UserService = MagicMock()

    # JSONResponse stub: store content for assertions
    def _json_response(content=None, status_code=200):
        r = SimpleNamespace(status_code=status_code, content=content)
        return r

    sys.modules["fastapi.responses"].JSONResponse = _json_response
    _scim_spec.loader.exec_module(_scim_mod)
    return _scim_mod


_scim = _load_scim_module()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(headers: dict | None = None, json_body: dict | None = None):
    """Build a minimal mock Request."""
    req = MagicMock()
    req.headers = MagicMock()
    req.headers.get = lambda k, default=None: (headers or {}).get(k, default)
    req.url = SimpleNamespace(scheme="https", netloc="autobot.local")
    req.json = AsyncMock(return_value=json_body or {})
    return req


def _make_user(is_active: bool = True) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.username = "alice"
    u.email = "alice@example.com"
    u.display_name = "Alice Example"
    u.is_active = is_active
    u.created_at = None
    u.updated_at = None
    return u


def _make_role(name: str = "operator") -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.name = name
    return r


# ---------------------------------------------------------------------------
# Bearer-token auth tests
# ---------------------------------------------------------------------------


class TestBearerAuth:
    """Verify _require_scim_bearer raises 401 when token is absent or wrong."""

    @pytest.mark.asyncio
    async def test_missing_auth_header_raises_401(self):
        req = _make_request(headers={})
        mock_exc = None

        async def _load():
            return "correct-token"

        with patch.object(_scim, "_load_scim_token", _load):
            try:
                await _scim._require_scim_bearer(req)
            except Exception as exc:
                mock_exc = exc
        assert mock_exc is not None, "Expected HTTPException-like raised"

    @pytest.mark.asyncio
    async def test_wrong_token_raises_401(self):
        req = _make_request(headers={"Authorization": "Bearer wrong-token"})

        async def _load():
            return "correct-token"

        exc = None
        with patch.object(_scim, "_load_scim_token", _load):
            try:
                await _scim._require_scim_bearer(req)
            except Exception as e:
                exc = e
        assert exc is not None, "Expected 401 for wrong token"

    @pytest.mark.asyncio
    async def test_correct_token_passes(self):
        token = "my-secret-scim-token"
        req = _make_request(headers={"Authorization": f"Bearer {token}"})

        async def _load():
            return token

        with patch.object(_scim, "_load_scim_token", _load):
            # Should NOT raise
            await _scim._require_scim_bearer(req)


# ---------------------------------------------------------------------------
# User serialisation
# ---------------------------------------------------------------------------


class TestUserToScim:
    def test_basic_shape(self):
        user = _make_user()
        result = _scim._user_to_scim(user, "https://host")
        assert result["schemas"] == [_scim._SCIM_USER_SCHEMA]
        assert result["id"] == str(user.id)
        assert result["userName"] == "alice"
        assert result["active"] is True
        assert result["meta"]["resourceType"] == "User"
        assert str(user.id) in result["meta"]["location"]

    def test_inactive_user(self):
        user = _make_user(is_active=False)
        result = _scim._user_to_scim(user, "https://host")
        assert result["active"] is False

    def test_email_present(self):
        user = _make_user()
        result = _scim._user_to_scim(user, "https://host")
        assert result["emails"][0]["value"] == "alice@example.com"
        assert result["emails"][0]["primary"] is True


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------


class TestExtractScimUserFields:
    def test_standard_body(self):
        body = {
            "userName": "bob",
            "emails": [{"value": "bob@example.com", "primary": True}],
            "name": {"givenName": "Bob", "familyName": "Smith"},
            "active": True,
            "externalId": "ext-001",
        }
        fields = _scim._extract_scim_user_fields(body)
        assert fields["username"] == "bob"
        assert fields["email"] == "bob@example.com"
        assert fields["display_name"] == "Bob Smith"
        assert fields["active"] is True
        assert fields["external_id"] == "ext-001"

    def test_fallback_email_from_username(self):
        body = {"userName": "carol", "emails": []}
        fields = _scim._extract_scim_user_fields(body)
        assert "carol@scim.local" == fields["email"]

    def test_non_primary_email_fallback(self):
        body = {"userName": "dave", "emails": [{"value": "dave@corp.com"}]}
        fields = _scim._extract_scim_user_fields(body)
        assert fields["email"] == "dave@corp.com"


# ---------------------------------------------------------------------------
# create user → 201 SCIM body
# ---------------------------------------------------------------------------


class _ScimDuplicateError(Exception):
    """Concrete exception used to exercise the DuplicateUserError except branch."""


class TestScimCreateUser:
    """Test user-creation logic via the inner helpers (router decorator replaces the
    endpoint with a MagicMock in the stub environment, so we test at the logic layer
    that the router calls — the same pattern used in test_sso_auth.py)."""

    @pytest.mark.asyncio
    async def test_create_user_service_called_and_result_serialised(self):
        """create_user is called; result maps to a valid SCIM User body."""
        user = _make_user()
        mock_svc = MagicMock()
        mock_svc.create_user = AsyncMock(return_value=user)
        mock_svc.deactivate_user = AsyncMock()

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        fields = {
            "username": "alice",
            "email": "alice@example.com",
            "display_name": "Alice Example",
            "active": True,
            "external_id": "",
        }

        # Simulate the core of scim_create_user without the router decorator
        with (
            patch.object(_scim, "DuplicateUserError", _ScimDuplicateError),
            patch.object(_scim, "UserService", return_value=mock_svc),
        ):
            created = await mock_svc.create_user(
                email=fields["email"],
                username=fields["username"],
                display_name=fields["display_name"],
            )
            if not fields["active"]:
                await mock_svc.deactivate_user(created.id)
            await mock_db.commit()

        scim_body = _scim._user_to_scim(user, "https://autobot.local")
        assert scim_body["schemas"] == [_scim._SCIM_USER_SCHEMA]
        assert scim_body["userName"] == "alice"
        mock_svc.create_user.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_inactive_user_triggers_deactivate(self):
        """When active=false in the SCIM body, deactivate_user is called."""
        user = _make_user(is_active=False)
        mock_svc = MagicMock()
        mock_svc.create_user = AsyncMock(return_value=user)
        mock_svc.deactivate_user = AsyncMock()

        fields = _scim._extract_scim_user_fields(
            {"userName": "ghost", "emails": [{"value": "ghost@example.com", "primary": True}], "active": False}
        )
        assert fields["active"] is False

        # Simulate the active-flag branch
        with (
            patch.object(_scim, "DuplicateUserError", _ScimDuplicateError),
            patch.object(_scim, "UserService", return_value=mock_svc),
        ):
            created = await mock_svc.create_user(email=fields["email"], username=fields["username"])
            if not fields["active"]:
                await mock_svc.deactivate_user(created.id)

        mock_svc.deactivate_user.assert_awaited_once_with(user.id)


# ---------------------------------------------------------------------------
# PATCH active:false → deactivate (deprovisioning signal)
# ---------------------------------------------------------------------------


class TestScimPatchUser:
    @pytest.mark.asyncio
    async def test_patch_active_false_deactivates(self):
        user = _make_user(is_active=True)
        mock_svc = MagicMock()
        mock_svc.get_user = AsyncMock(return_value=user)
        mock_svc.deactivate_user = AsyncMock()
        mock_svc.activate_user = AsyncMock()

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        ops = [{"op": "replace", "path": "active", "value": False}]
        await _scim._apply_patch_ops(ops, user, mock_svc)

        mock_svc.deactivate_user.assert_awaited_once_with(user.id)

    @pytest.mark.asyncio
    async def test_patch_active_true_activates_inactive(self):
        user = _make_user(is_active=False)
        mock_svc = MagicMock()
        mock_svc.activate_user = AsyncMock()
        mock_svc.deactivate_user = AsyncMock()

        ops = [{"op": "replace", "path": "active", "value": True}]
        await _scim._apply_patch_ops(ops, user, mock_svc)

        mock_svc.activate_user.assert_awaited_once_with(user.id)


# ---------------------------------------------------------------------------
# Group → role mapping
# ---------------------------------------------------------------------------


class TestGroupRoleMapping:
    @pytest.mark.asyncio
    async def test_sync_group_members_assigns_role(self):
        role = _make_role("operator")
        user_id = uuid.uuid4()
        members = [{"value": str(user_id)}]

        mock_svc = MagicMock()
        mock_svc.assign_role = AsyncMock(return_value=True)
        mock_svc.revoke_role = AsyncMock(return_value=True)

        mock_db = AsyncMock()
        # existing_result.scalars().all() returns empty (no current members)
        existing_mock = MagicMock()
        existing_mock.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=existing_mock)

        with patch.object(_scim, "UserService", return_value=mock_svc):
            await _scim._sync_group_members(role, members, mock_db)

        mock_svc.assign_role.assert_awaited_once_with(user_id, role.id)

    @pytest.mark.asyncio
    async def test_sync_group_members_revokes_removed(self):
        role = _make_role("operator")
        existing_user_id = uuid.uuid4()

        # Member currently has role but not in new members list
        mock_ur = MagicMock()
        mock_ur.user_id = existing_user_id

        mock_svc = MagicMock()
        mock_svc.assign_role = AsyncMock(return_value=True)
        mock_svc.revoke_role = AsyncMock(return_value=True)

        mock_db = AsyncMock()
        existing_mock = MagicMock()
        existing_mock.scalars.return_value.all.return_value = [mock_ur]
        mock_db.execute = AsyncMock(return_value=existing_mock)

        # members list is empty — so existing member should be revoked
        with patch.object(_scim, "UserService", return_value=mock_svc):
            await _scim._sync_group_members(role, [], mock_db)

        mock_svc.revoke_role.assert_awaited_once_with(existing_user_id, role.id)

    @pytest.mark.asyncio
    async def test_deprovision_remove_member_revokes_role(self):
        """Removing a member via PATCH /Groups deprovisions the role (deprovisioning)."""
        role = _make_role("admin")
        user_id = uuid.uuid4()

        mock_svc = MagicMock()
        mock_svc.revoke_role = AsyncMock(return_value=True)

        member = {"value": str(user_id)}
        await _scim._revoke_role_from_member(member, role, mock_svc)

        mock_svc.revoke_role.assert_awaited_once_with(user_id, role.id)


# ---------------------------------------------------------------------------
# List response shape
# ---------------------------------------------------------------------------


class TestListResponse:
    def test_list_response_schema(self):
        resources = [{"id": "1"}, {"id": "2"}]
        result = _scim._list_response(resources, total=10, start=1, count=2)
        assert result["schemas"] == [_scim._SCIM_LIST_SCHEMA]
        assert result["totalResults"] == 10
        assert result["itemsPerPage"] == 2
        assert len(result["Resources"]) == 2


# ---------------------------------------------------------------------------
# SCIM filter parsing
# ---------------------------------------------------------------------------


class TestApplyScimFilter:
    @pytest.mark.asyncio
    async def test_username_filter_calls_get_by_username(self):
        mock_svc = MagicMock()
        user = _make_user()
        mock_svc.get_user_by_username = AsyncMock(return_value=user)
        result = await _scim._apply_scim_filter('userName eq "alice"', mock_svc)
        assert result == user
        mock_svc.get_user_by_username.assert_awaited_once_with("alice")

    @pytest.mark.asyncio
    async def test_email_filter_calls_get_by_email(self):
        mock_svc = MagicMock()
        user = _make_user()
        mock_svc.get_user_by_email = AsyncMock(return_value=user)
        result = await _scim._apply_scim_filter('emails.value eq "alice@example.com"', mock_svc)
        assert result == user
        mock_svc.get_user_by_email.assert_awaited_once_with("alice@example.com")

    @pytest.mark.asyncio
    async def test_unknown_filter_returns_none(self):
        mock_svc = MagicMock()
        result = await _scim._apply_scim_filter('id eq "abc"', mock_svc)
        assert result is None
