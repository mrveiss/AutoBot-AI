# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for GH#10750 A5 — tenant org-context resolution.

Covers the four scenarios mandated by the issue:
  1. Header-provided org for a platform admin (allow without membership check).
  2. Header-provided org for a member (allow after membership check).
  3. Header-provided org for a NON-member (reject with HTTP 403).
  4. JWT-claim fallback when no request org is present.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient

from api.user_management.dependencies import (
    _extract_request_org_id,
    _parse_uuid_safe,
    get_tenant_context,
    require_org_context,
)
from user_management.services import TenantContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ORG_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_ORG_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_USER_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _user(org_id=None, role="user", is_platform_admin=False, user_id=None):
    return {
        "user_id": str(user_id or _USER_ID),
        "org_id": str(org_id) if org_id else None,
        "role": role,
        "is_platform_admin": is_platform_admin,
    }


# ---------------------------------------------------------------------------
# _parse_uuid_safe
# ---------------------------------------------------------------------------


class TestParseUuidSafe:
    def test_valid_uuid(self):
        assert _parse_uuid_safe(str(_ORG_A)) == _ORG_A

    def test_invalid_string_returns_none(self):
        assert _parse_uuid_safe("not-a-uuid") is None

    def test_none_returns_none(self):
        assert _parse_uuid_safe(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_uuid_safe("") is None


# ---------------------------------------------------------------------------
# _extract_request_org_id  (uses a minimal ASGI scope)
# ---------------------------------------------------------------------------


class TestExtractRequestOrgId:
    def _make_request(self, headers=None, path_params=None, query_string=b""):
        from starlette.requests import Request

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": query_string,
            # ASGI spec requires header names as lowercase bytes
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "path_params": path_params or {},
        }
        return Request(scope)

    def test_header_takes_precedence(self):
        req = self._make_request(
            headers={"X-Organization-Id": str(_ORG_A)},
            path_params={"company_id": str(_ORG_B)},
        )
        assert _extract_request_org_id(req) == _ORG_A

    def test_path_param_company_id(self):
        req = self._make_request(path_params={"company_id": str(_ORG_A)})
        assert _extract_request_org_id(req) == _ORG_A

    def test_path_param_id(self):
        req = self._make_request(path_params={"id": str(_ORG_A)})
        assert _extract_request_org_id(req) == _ORG_A

    def test_query_param(self):
        req = self._make_request(query_string=f"company_id={_ORG_A}".encode())
        assert _extract_request_org_id(req) == _ORG_A

    def test_no_org_returns_none(self):
        req = self._make_request()
        assert _extract_request_org_id(req) is None

    def test_invalid_header_uuid_ignored(self):
        req = self._make_request(headers={"X-Organization-Id": "garbage"})
        assert _extract_request_org_id(req) is None


# ---------------------------------------------------------------------------
# get_tenant_context — async dependency tests (call directly, mock DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetTenantContext:
    def _make_request(self, headers=None, path_params=None, query_string=b""):
        from starlette.requests import Request

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": query_string,
            # ASGI spec requires header names as lowercase bytes
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "path_params": path_params or {},
        }
        return Request(scope)

    def _mock_session(self, is_member: bool):
        session = AsyncMock()
        result = MagicMock()
        result.first.return_value = MagicMock() if is_member else None
        session.execute = AsyncMock(return_value=result)
        return session

    # 1. Platform admin with header — no membership check, org accepted
    async def test_platform_admin_header_org_accepted(self):
        req = self._make_request(headers={"X-Organization-Id": str(_ORG_A)})
        user = _user(role="admin")
        session = self._mock_session(is_member=False)  # membership irrelevant for admin

        with patch("api.user_management.dependencies._check_org_membership") as mock_check:
            ctx = await get_tenant_context(req, current_user=user, session=session)

        mock_check.assert_not_called()
        assert ctx.org_id == _ORG_A
        assert ctx.is_platform_admin is True

    # 1b. is_platform_admin flag in JWT (not just role)
    async def test_is_platform_admin_flag_header_org_accepted(self):
        req = self._make_request(headers={"X-Organization-Id": str(_ORG_A)})
        user = _user(is_platform_admin=True)
        session = self._mock_session(is_member=False)

        with patch("api.user_management.dependencies._check_org_membership") as mock_check:
            ctx = await get_tenant_context(req, current_user=user, session=session)

        mock_check.assert_not_called()
        assert ctx.org_id == _ORG_A

    # 2. Header-provided org for a member — allowed
    async def test_member_header_org_accepted(self):
        req = self._make_request(headers={"X-Organization-Id": str(_ORG_A)})
        user = _user()
        session = self._mock_session(is_member=True)

        ctx = await get_tenant_context(req, current_user=user, session=session)

        assert ctx.org_id == _ORG_A
        assert ctx.user_id == _USER_ID

    # 3. Header-provided org for a NON-member — rejected with 403
    async def test_non_member_header_org_rejected_403(self):
        from fastapi import HTTPException

        req = self._make_request(headers={"X-Organization-Id": str(_ORG_A)})
        user = _user()
        session = self._mock_session(is_member=False)

        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_context(req, current_user=user, session=session)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    # 4. JWT claim fallback when no request org present
    async def test_jwt_fallback_no_request_org(self):
        req = self._make_request()  # no header, no path param, no query
        user = _user(org_id=_ORG_B)
        session = self._mock_session(is_member=False)  # never called

        with patch("api.user_management.dependencies._check_org_membership") as mock_check:
            ctx = await get_tenant_context(req, current_user=user, session=session)

        mock_check.assert_not_called()
        assert ctx.org_id == _ORG_B

    # 4b. No org anywhere — returns None org_id (require_org_context then raises 400)
    async def test_no_org_anywhere_returns_none(self):
        req = self._make_request()
        user = _user()  # no org_id in JWT
        session = self._mock_session(is_member=False)

        ctx = await get_tenant_context(req, current_user=user, session=session)

        assert ctx.org_id is None

    # path param company_id takes precedence over JWT claim
    async def test_path_param_member_accepted(self):
        req = self._make_request(path_params={"company_id": str(_ORG_A)})
        user = _user(org_id=_ORG_B)  # JWT has different org
        session = self._mock_session(is_member=True)

        ctx = await get_tenant_context(req, current_user=user, session=session)

        assert ctx.org_id == _ORG_A  # request org wins

    # invalid header UUID falls through to JWT fallback
    async def test_invalid_header_uuid_falls_back_to_jwt(self):
        req = self._make_request(headers={"X-Organization-Id": "not-a-uuid"})
        user = _user(org_id=_ORG_B)
        session = self._mock_session(is_member=False)

        ctx = await get_tenant_context(req, current_user=user, session=session)

        assert ctx.org_id == _ORG_B  # fell back to JWT


# ---------------------------------------------------------------------------
# require_org_context — HTTP integration test via TestClient
# ---------------------------------------------------------------------------


def _make_app(current_user_dict):
    """Build a minimal FastAPI app wired through the real require_org_context dep.

    The DB session is overridden with a no-op stub.  Actual membership DB calls
    are controlled via ``patch("api.user_management.dependencies._check_org_membership")``
    in each individual test, so the TestClient never touches a real database.
    """
    from api.user_management.dependencies import get_current_user, get_db_session

    app = FastAPI()

    app.dependency_overrides[get_current_user] = lambda: current_user_dict

    async def _fake_session():
        # Yield a stub session; _check_org_membership is mocked at call time
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _fake_session

    @app.get("/test")
    async def _endpoint(ctx: TenantContext = Depends(require_org_context)):
        return {"org_id": str(ctx.org_id)}

    return app


class TestRequireOrgContextIntegration:
    def test_member_with_header_returns_200(self):
        app = _make_app(_user())
        client = TestClient(app, raise_server_exceptions=True)
        with patch(
            "api.user_management.dependencies._check_org_membership",
            new=AsyncMock(return_value=True),
        ):
            resp = client.get("/test", headers={"X-Organization-Id": str(_ORG_A)})
        assert resp.status_code == 200
        assert resp.json()["org_id"] == str(_ORG_A)

    def test_non_member_with_header_returns_403(self):
        app = _make_app(_user())
        client = TestClient(app, raise_server_exceptions=False)
        with patch(
            "api.user_management.dependencies._check_org_membership",
            new=AsyncMock(return_value=False),
        ):
            resp = client.get("/test", headers={"X-Organization-Id": str(_ORG_A)})
        assert resp.status_code == 403

    def test_no_org_anywhere_returns_400(self):
        app = _make_app(_user())
        client = TestClient(app, raise_server_exceptions=True)
        # No header, no path param, no JWT org → require_org_context raises 400
        with patch(
            "api.user_management.dependencies._check_org_membership",
            new=AsyncMock(return_value=False),
        ):
            resp = client.get("/test")
        assert resp.status_code == 400
        assert "Organization context required" in resp.json()["detail"]

    def test_jwt_org_accepted_without_header(self):
        app = _make_app(_user(org_id=_ORG_B))
        client = TestClient(app, raise_server_exceptions=True)
        # JWT claim path — no request org → no membership check → use JWT org
        with patch(
            "api.user_management.dependencies._check_org_membership",
            new=AsyncMock(return_value=False),
        ):
            resp = client.get("/test")
        assert resp.status_code == 200
        assert resp.json()["org_id"] == str(_ORG_B)
