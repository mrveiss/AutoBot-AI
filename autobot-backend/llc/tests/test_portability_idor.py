# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Auth + tenant hardening tests for portability.py import routes (GH#12148).

Prior to this fix llc/api/portability.py (POST /preview, POST /execute)
depended only on ``get_async_session`` — no authentication and no
tenant-authorization — allowing an unauthenticated caller to import data into
ANY company via ``target_company_id`` (missing-authentication + cross-tenant
write). Import is an admin/user action, so the routes are user-facing
(get_current_user + require_org_context).

  - no auth at all                                  -> 401
  - authenticated, cross-tenant target_company_id   -> 404
  - authenticated, same-tenant / no target          -> success
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
_OTHER_ORG = "99999999-9999-9999-9999-999999999999"

_PREVIEW_RESULT = {"collisions": [], "will_create": {}, "warnings": []}
_EXECUTE_RESULT = {"company_id": "c", "created_entities": {}, "skipped": {}, "warnings": []}


def _make_client(caller_org_id: str, is_platform_admin: bool = False) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.portability import router as portability_router  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(portability_router, prefix="/api/llc")

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_async_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org_id), user_id=_FIXED_USER_ID, is_platform_admin=is_platform_admin
    )

    patch("llc.api.portability.PortabilityService.preview_import", new=AsyncMock(return_value=_PREVIEW_RESULT)).start()
    patch("llc.api.portability.PortabilityService.execute_import", new=AsyncMock(return_value=_EXECUTE_RESULT)).start()

    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


class TestPortabilityNoAuth:
    def _make_unauthenticated_client(self) -> TestClient:
        from llc.api.portability import router as portability_router
        from user_management.database import get_async_session

        app = FastAPI()
        app.include_router(portability_router, prefix="/api/llc")

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_async_session] = _fake_session
        return TestClient(app)

    def test_preview_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.post("/api/llc/import/preview", json={"template": {}})
        assert resp.status_code == 401

    def test_execute_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.post("/api/llc/import/execute", json={"template": {}})
        assert resp.status_code == 401


class TestPortabilityTenant:
    def test_preview_no_target_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post("/api/llc/import/preview", json={"template": {}})
        assert resp.status_code == 200

    def test_preview_own_target_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post("/api/llc/import/preview", json={"template": {}, "target_company_id": org})
        assert resp.status_code == 200

    def test_preview_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post("/api/llc/import/preview", json={"template": {}, "target_company_id": _OTHER_ORG})
        assert resp.status_code == 404

    def test_execute_own_target_returns_201(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post("/api/llc/import/execute", json={"template": {}, "target_company_id": org})
        assert resp.status_code == 201

    def test_execute_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post("/api/llc/import/execute", json={"template": {}, "target_company_id": _OTHER_ORG})
        assert resp.status_code == 404

    def test_execute_platform_admin_cross_tenant_allowed(self):
        org = str(uuid.uuid4())
        client = _make_client(org, is_platform_admin=True)
        resp = client.post("/api/llc/import/execute", json={"template": {}, "target_company_id": _OTHER_ORG})
        assert resp.status_code == 201
