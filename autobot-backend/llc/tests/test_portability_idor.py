# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Auth + IDOR hardening tests for portability.py routes (GH#12163).

Prior to this fix both handlers in llc/api/portability.py depended only on
``get_async_session`` — no authentication and no tenant-authorization
dependency — allowing an unauthenticated caller to import a template into
ANY existing company by supplying its ``target_company_id`` (missing
authentication + IDOR).

Mirrors test_goals_idor.py / test_secrets_idor.py (GH#12136, GH#12147):
  - no auth at all                                -> 401
  - authenticated, cross-tenant target_company_id  -> 404
  - authenticated, same-tenant target_company_id   -> the expected success status
  - target_company_id omitted (new-company import) -> allowed for any authenticated caller
  - platform admin                                 -> cross-tenant allowed
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_OTHER_ORG = "99999999-9999-9999-9999-999999999999"

_PREVIEW_RESULT = {"collisions": [], "will_create": {}, "warnings": []}
_EXECUTE_RESULT = {"company_id": str(uuid.uuid4()), "created_entities": {}, "skipped": {}, "warnings": []}

_TEMPLATE = {"schema_version": "1.0", "company": {"name": "Acme"}}


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
    """No credentials at all -> 401 (real get_current_user, not overridden)."""

    def _make_unauthenticated_client(self) -> TestClient:
        from llc.api.portability import router as portability_router
        from user_management.database import get_async_session

        app = FastAPI()
        app.include_router(portability_router, prefix="/api/llc")

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_async_session] = _fake_session
        return TestClient(app)

    def test_preview_import_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.post(
                "/api/llc/import/preview",
                json={"template": _TEMPLATE, "target_company_id": _OTHER_ORG},
            )
        assert resp.status_code == 401

    def test_execute_import_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.post(
                "/api/llc/import/execute",
                json={"template": _TEMPLATE, "target_company_id": _OTHER_ORG},
            )
        assert resp.status_code == 401


class TestPortabilityIdor:
    # --- preview ---

    def test_preview_import_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            "/api/llc/import/preview",
            json={"template": _TEMPLATE, "target_company_id": org},
        )
        assert resp.status_code == 200

    def test_preview_import_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            "/api/llc/import/preview",
            json={"template": _TEMPLATE, "target_company_id": _OTHER_ORG},
        )
        assert resp.status_code == 404

    def test_preview_import_no_target_company_allowed(self):
        """Omitting target_company_id previews a brand-new company — any authenticated caller."""
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post("/api/llc/import/preview", json={"template": _TEMPLATE})
        assert resp.status_code == 200

    def test_preview_import_platform_admin_cross_tenant_allowed(self):
        org = str(uuid.uuid4())
        client = _make_client(org, is_platform_admin=True)
        resp = client.post(
            "/api/llc/import/preview",
            json={"template": _TEMPLATE, "target_company_id": _OTHER_ORG},
        )
        assert resp.status_code == 200

    # --- execute ---

    def test_execute_import_own_company_returns_201(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            "/api/llc/import/execute",
            json={"template": _TEMPLATE, "target_company_id": org},
        )
        assert resp.status_code == 201

    def test_execute_import_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            "/api/llc/import/execute",
            json={"template": _TEMPLATE, "target_company_id": _OTHER_ORG},
        )
        assert resp.status_code == 404

    def test_execute_import_no_target_company_allowed(self):
        """Omitting target_company_id creates a brand-new company — any authenticated caller."""
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post("/api/llc/import/execute", json={"template": _TEMPLATE})
        assert resp.status_code == 201

    def test_execute_import_platform_admin_cross_tenant_allowed(self):
        org = str(uuid.uuid4())
        client = _make_client(org, is_platform_admin=True)
        resp = client.post(
            "/api/llc/import/execute",
            json={"template": _TEMPLATE, "target_company_id": _OTHER_ORG},
        )
        assert resp.status_code == 201
