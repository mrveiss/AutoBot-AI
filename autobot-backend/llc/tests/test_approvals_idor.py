# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Auth + IDOR hardening tests for approvals.py routes (GH#12163).

Prior to this fix every handler in llc/api/approvals.py depended only on
``get_session`` — no authentication and no tenant-authorization dependency —
allowing an unauthenticated caller to request/list/decide board approvals for
ANY company by supplying an arbitrary ``company_id``/``approval_id`` (missing
authentication + IDOR).

Mirrors test_goals_idor.py / test_secrets_idor.py (GH#12136, GH#12147):
  - no auth at all                     -> 401
  - authenticated, cross-tenant access -> 404 (existence disclosure avoided)
  - authenticated, same-tenant access  -> the expected success status
  - platform admin                    -> cross-tenant allowed
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("88888888-8888-8888-8888-888888888888")
_OTHER_ORG = "99999999-9999-9999-9999-999999999999"


def _make_approval(company_id: str) -> MagicMock:
    approval = MagicMock()
    approval.id = uuid.uuid4()
    approval.company_id = uuid.UUID(company_id)
    approval.type = "hire"
    approval.status = "pending"
    approval.requested_by_agent_id = uuid.uuid4()
    approval.payload = {}
    approval.decided_by_agent_id = None
    approval.decided_at = None
    approval.created_at = datetime.now(timezone.utc)
    approval.updated_at = datetime.now(timezone.utc)
    return approval


def _make_client(
    caller_org_id: str,
    approval_company_id: str | None = None,
    approval_exists: bool = True,
    is_platform_admin: bool = False,
) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.approvals import router as approvals_router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(approvals_router, prefix="/api/llc")

    acid = approval_company_id if approval_company_id is not None else caller_org_id
    approval = _make_approval(acid) if approval_exists else None

    mock_session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = approval
    mock_session.execute = AsyncMock(return_value=execute_result)
    mock_session.begin = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org_id), user_id=_FIXED_USER_ID, is_platform_admin=is_platform_admin
    )

    patch("llc.api.approvals.ApprovalService.request_approval", new=AsyncMock(return_value=approval)).start()
    patch("llc.api.approvals.ApprovalService.publish_requested", new=AsyncMock()).start()
    patch(
        "llc.api.approvals.ApprovalService.get_pending",
        new=AsyncMock(return_value=[approval] if approval else []),
    ).start()
    patch("llc.api.approvals.ApprovalService.decide", new=AsyncMock(return_value=approval)).start()
    patch("llc.api.approvals.ApprovalService.publish_decided", new=AsyncMock()).start()
    patch("llc.api.approvals.ApprovalService.log_decision_to_kb", new=AsyncMock()).start()

    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


class TestApprovalsNoAuth:
    """No credentials at all -> 401 (real get_current_user, not overridden)."""

    def _make_unauthenticated_client(self) -> TestClient:
        from llc.api.approvals import router as approvals_router
        from llc.deps import get_session

        app = FastAPI()
        app.include_router(approvals_router, prefix="/api/llc")

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_session] = _fake_session
        return TestClient(app)

    def test_request_approval_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.post(
                "/api/llc/approvals",
                json={
                    "company_id": str(uuid.uuid4()),
                    "type": "hire",
                    "requested_by_agent_id": str(uuid.uuid4()),
                },
            )
        assert resp.status_code == 401

    def test_list_pending_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.get("/api/llc/approvals", params={"company_id": str(uuid.uuid4())})
        assert resp.status_code == 401

    def test_decide_approval_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.post(
                f"/api/llc/approvals/{uuid.uuid4()}/decide",
                json={"decision": "approved"},
            )
        assert resp.status_code == 401


class TestApprovalsIdor:
    # --- request ---

    def test_request_approval_own_company_returns_201(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            "/api/llc/approvals",
            json={"company_id": org, "type": "hire", "requested_by_agent_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 201

    def test_request_approval_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            "/api/llc/approvals",
            json={"company_id": _OTHER_ORG, "type": "hire", "requested_by_agent_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_request_approval_platform_admin_cross_tenant_allowed(self):
        org = str(uuid.uuid4())
        client = _make_client(org, is_platform_admin=True)
        resp = client.post(
            "/api/llc/approvals",
            json={"company_id": _OTHER_ORG, "type": "hire", "requested_by_agent_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 201

    # --- list ---

    def test_list_pending_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get("/api/llc/approvals", params={"company_id": org})
        assert resp.status_code == 200

    def test_list_pending_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get("/api/llc/approvals", params={"company_id": _OTHER_ORG})
        assert resp.status_code == 404

    def test_list_pending_platform_admin_cross_tenant_allowed(self):
        org = str(uuid.uuid4())
        client = _make_client(org, is_platform_admin=True)
        resp = client.get("/api/llc/approvals", params={"company_id": _OTHER_ORG})
        assert resp.status_code == 200

    # --- decide ---

    def test_decide_approval_own_tenant_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org, approval_company_id=org)
        resp = client.post(f"/api/llc/approvals/{uuid.uuid4()}/decide", json={"decision": "approved"})
        assert resp.status_code == 200

    def test_decide_approval_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org, approval_company_id=_OTHER_ORG)
        resp = client.post(f"/api/llc/approvals/{uuid.uuid4()}/decide", json={"decision": "approved"})
        assert resp.status_code == 404

    def test_decide_approval_not_found_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org, approval_exists=False)
        resp = client.post(f"/api/llc/approvals/{uuid.uuid4()}/decide", json={"decision": "approved"})
        assert resp.status_code == 404

    def test_decide_approval_platform_admin_cross_tenant_allowed(self):
        org = str(uuid.uuid4())
        client = _make_client(org, approval_company_id=_OTHER_ORG, is_platform_admin=True)
        resp = client.post(f"/api/llc/approvals/{uuid.uuid4()}/decide", json={"decision": "approved"})
        assert resp.status_code == 200
