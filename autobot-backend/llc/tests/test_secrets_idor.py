# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Auth + IDOR hardening tests for secrets.py routes (GH#12147).

Prior to this fix every handler in llc/api/secrets.py depended only on
``_check_company_access``, which merely asserted that a client-supplied
``X-Agent-Company-Id`` header equaled the ``{company_id}`` path parameter —
no identity verification at all. Any caller could read/write/revoke ANY
company's secrets by setting the header to the target company_id.

Mirrors test_goals_idor.py (GH#12136):
  - no auth at all                     -> 401
  - the old spoofable header alone     -> 401 (no longer a trust anchor)
  - authenticated, cross-tenant access -> 404 (existence disclosure avoided)
  - authenticated, same-tenant access  -> the expected success status
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
_OTHER_ORG = "99999999-9999-9999-9999-999999999999"


def _make_row(secret_name: str = "db_password", version: int = 1) -> MagicMock:
    row = MagicMock()
    row.name = secret_name
    row.version = version
    return row


def _make_client(
    caller_org_id: str,
    is_platform_admin: bool = False,
) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.secrets import router as secrets_router  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(secrets_router, prefix="/api/llc")

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one.return_value = _make_row()
    mock_session.execute = AsyncMock(return_value=execute_result)

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_async_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org_id), user_id=_FIXED_USER_ID, is_platform_admin=is_platform_admin
    )

    set_result = MagicMock()
    set_result.name = "api_key"
    set_result.version = 1
    set_result.company_id = caller_org_id

    patch("llc.api.secrets.SecretService.list", new=AsyncMock(return_value=[])).start()
    patch("llc.api.secrets.SecretService.set", new=AsyncMock(return_value=set_result)).start()
    patch("llc.api.secrets.SecretService.get", new=AsyncMock(return_value="plaintext-value")).start()
    patch("llc.api.secrets.SecretService.revoke", new=AsyncMock(return_value=None)).start()

    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


class TestSecretsNoAuth:
    """No credentials at all -> 401 (real get_current_user, not overridden)."""

    def _make_unauthenticated_client(self) -> TestClient:
        from llc.api.secrets import router as secrets_router
        from user_management.database import get_async_session

        app = FastAPI()
        app.include_router(secrets_router, prefix="/api/llc")

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_async_session] = _fake_session
        return TestClient(app)

    def test_list_secrets_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.get(f"/api/llc/secrets/{_OTHER_ORG}")
        assert resp.status_code == 401

    def test_list_secrets_spoofed_header_alone_returns_401(self):
        """The old X-Agent-Company-Id header, with no real auth, no longer works (GH#12147)."""
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.get(f"/api/llc/secrets/{_OTHER_ORG}", headers={"X-Agent-Company-Id": _OTHER_ORG})
        assert resp.status_code == 401

    def test_get_secret_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.get(f"/api/llc/secrets/{_OTHER_ORG}/db_password")
        assert resp.status_code == 401

    def test_set_secret_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.post(
                f"/api/llc/secrets/{_OTHER_ORG}",
                json={"name": "k", "value": "v", "actor": "agent-1"},
            )
        assert resp.status_code == 401

    def test_revoke_secret_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.delete(f"/api/llc/secrets/{_OTHER_ORG}/db_password", params={"actor": "agent-1"})
        assert resp.status_code == 401


class TestSecretsIdor:
    # --- list ---

    def test_list_secrets_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get(f"/api/llc/secrets/{org}")
        assert resp.status_code == 200

    def test_list_secrets_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get(f"/api/llc/secrets/{_OTHER_ORG}")
        assert resp.status_code == 404

    def test_list_secrets_spoofed_header_cross_tenant_still_404(self):
        """Even with the old header set to the target company, real tenant wins (GH#12147)."""
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get(f"/api/llc/secrets/{_OTHER_ORG}", headers={"X-Agent-Company-Id": _OTHER_ORG})
        assert resp.status_code == 404

    def test_list_secrets_platform_admin_cross_tenant_allowed(self):
        org = str(uuid.uuid4())
        client = _make_client(org, is_platform_admin=True)
        resp = client.get(f"/api/llc/secrets/{_OTHER_ORG}")
        assert resp.status_code == 200

    # --- set ---

    def test_set_secret_own_company_returns_201(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            f"/api/llc/secrets/{org}",
            json={"name": "api_key", "value": "s3cr3t", "actor": "agent-1"},
        )
        assert resp.status_code == 201

    def test_set_secret_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            f"/api/llc/secrets/{_OTHER_ORG}",
            json={"name": "api_key", "value": "s3cr3t", "actor": "agent-1"},
        )
        assert resp.status_code == 404

    # --- get value ---

    def test_get_secret_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get(f"/api/llc/secrets/{org}/db_password")
        assert resp.status_code == 200
        assert resp.json()["value"] == "plaintext-value"

    def test_get_secret_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get(f"/api/llc/secrets/{_OTHER_ORG}/db_password")
        assert resp.status_code == 404

    # --- revoke ---

    def test_revoke_secret_own_company_returns_204(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.delete(f"/api/llc/secrets/{org}/db_password", params={"actor": "agent-1"})
        assert resp.status_code == 204

    def test_revoke_secret_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.delete(f"/api/llc/secrets/{_OTHER_ORG}/db_password", params={"actor": "agent-1"})
        assert resp.status_code == 404
