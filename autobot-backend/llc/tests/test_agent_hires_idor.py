# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Auth + IDOR hardening tests for agent_hires.py routes (GH#12163).

Prior to this fix ``hire_agent`` (POST /companies/{company_id}/agent-hires)
depended only on ``get_async_session`` — no authentication and no
tenant-authorization dependency — allowing an unauthenticated caller to hire
an agent into ANY company. ``create_agent_hire`` / ``list_agent_hires`` used a
vestigial ``Depends(lambda: None)`` in place of real auth, which always
resolved to ``None`` and silently skipped all tenant checks.

Mirrors test_goals_idor.py / test_secrets_idor.py (GH#12136, GH#12147):
  - no auth at all                     -> 401
  - authenticated, cross-tenant access -> 404 (existence disclosure avoided)
  - authenticated, same-tenant access  -> the expected success status
  - platform admin                    -> cross-tenant allowed
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_OTHER_ORG = "99999999-9999-9999-9999-999999999999"


def _make_client(caller_org_id: str, is_platform_admin: bool = False) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.agent_hires import router as agent_hires_router  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(agent_hires_router, prefix="/api/llc")

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    execute_result = MagicMock()
    execute_result.fetchone.return_value = None
    execute_result.fetchall.return_value = []
    mock_session.execute = AsyncMock(return_value=execute_result)

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_async_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org_id), user_id=_FIXED_USER_ID, is_platform_admin=is_platform_admin
    )

    patch("llc.api.agent_hires.registered_adapter_types", return_value=["claude_code"]).start()
    patch("llc.api.agent_hires.BudgetService.provision_budget", new=AsyncMock()).start()

    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


class TestAgentHiresNoAuth:
    """No credentials at all -> 401 (real get_current_user, not overridden)."""

    def _make_unauthenticated_client(self) -> TestClient:
        from llc.api.agent_hires import router as agent_hires_router
        from user_management.database import get_async_session

        app = FastAPI()
        app.include_router(agent_hires_router, prefix="/api/llc")

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_async_session] = _fake_session
        return TestClient(app)

    def test_create_agent_hire_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.post("/api/llc/agent-hires", json={})
        assert resp.status_code == 401

    def test_list_agent_hires_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.get("/api/llc/agent-hires")
        assert resp.status_code == 401

    def test_hire_agent_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.post(
                f"/api/llc/companies/{uuid.uuid4()}/agent-hires",
                json={"agent_name": "Bot"},
            )
        assert resp.status_code == 401


class TestAgentHiresIdor:
    # --- create_agent_hire (POST /agent-hires) ---

    def test_create_agent_hire_own_company_returns_201(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post("/api/llc/agent-hires", json={"company_id": org})
        assert resp.status_code == 201

    def test_create_agent_hire_no_company_id_defaults_to_caller_org(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post("/api/llc/agent-hires", json={})
        assert resp.status_code == 201
        assert resp.json()["company_id"] == org

    def test_create_agent_hire_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post("/api/llc/agent-hires", json={"company_id": _OTHER_ORG})
        assert resp.status_code == 404

    def test_create_agent_hire_platform_admin_cross_tenant_allowed(self):
        org = str(uuid.uuid4())
        client = _make_client(org, is_platform_admin=True)
        resp = client.post("/api/llc/agent-hires", json={"company_id": _OTHER_ORG})
        assert resp.status_code == 201

    # --- list_agent_hires (GET /agent-hires) ---

    def test_list_agent_hires_authenticated_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get("/api/llc/agent-hires")
        assert resp.status_code == 200
        assert resp.json() == []

    # --- hire_agent (POST /companies/{company_id}/agent-hires) ---

    def test_hire_agent_own_company_returns_201(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(f"/api/llc/companies/{org}/agent-hires", json={"agent_name": "Bot"})
        assert resp.status_code == 201

    def test_hire_agent_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(f"/api/llc/companies/{_OTHER_ORG}/agent-hires", json={"agent_name": "Bot"})
        assert resp.status_code == 404

    def test_hire_agent_platform_admin_cross_tenant_allowed(self):
        org = str(uuid.uuid4())
        client = _make_client(org, is_platform_admin=True)
        resp = client.post(f"/api/llc/companies/{_OTHER_ORG}/agent-hires", json={"agent_name": "Bot"})
        assert resp.status_code == 201
