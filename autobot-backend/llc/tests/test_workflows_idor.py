# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Route-level access control for workflows.py routes (#14210).

Mirrors ``test_contacts_idor.py``'s shape:
  - no auth at all                  -> 401
  - authenticated, wrong company_id -> 404 (assert_company_access, #12238)
  - authenticated, own company_id   -> the expected success status
  - platform admin, any company_id  -> allowed

Proves the route wiring itself (dependency chain + assert_company_access)
end-to-end, complementing the service-level company-scoping tests in
``test_workflows_scoping.py`` which pin the underlying ``WHERE company_id``
predicate.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
_OTHER_COMPANY = "99999999-9999-9999-9999-999999999999"


def _make_workflow_dict(company_id: str, workflow_id: str) -> dict:
    return {
        "workflow_id": workflow_id,
        "company_id": company_id,
        "name": "Deploy",
        "status": "planned",
        "source": "created",
        "definition": {},
        "created_at": "2026-08-13T00:00:00+00:00",
        "updated_at": "2026-08-13T00:00:00+00:00",
    }


def _make_client(caller_company_id: str, is_platform_admin: bool = False) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.workflows import router as workflows_router  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(workflows_router, prefix="/api/llc")

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_async_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_company_id), user_id=_FIXED_USER_ID, is_platform_admin=is_platform_admin
    )

    workflow_id = "wf-1"
    created = MagicMock(**_make_workflow_dict(caller_company_id, workflow_id))
    for key, value in _make_workflow_dict(caller_company_id, workflow_id).items():
        setattr(created, key, value)

    patch("llc.api.workflows.WorkflowService.list_by_company", new=AsyncMock(return_value=[])).start()
    patch("llc.api.workflows.WorkflowService.create", new=AsyncMock(return_value=created)).start()
    patch("llc.api.workflows.WorkflowService.get", new=AsyncMock(return_value=created)).start()
    patch("llc.api.workflows.WorkflowService.update_status", new=AsyncMock(return_value=created)).start()
    patch("llc.api.workflows.WorkflowService.delete", new=AsyncMock(return_value=True)).start()

    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


class TestWorkflowsNoAuth:
    def _make_unauthenticated_client(self) -> TestClient:
        from llc.api.workflows import router as workflows_router
        from user_management.database import get_async_session

        app = FastAPI()
        app.include_router(workflows_router, prefix="/api/llc")

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_async_session] = _fake_session
        return TestClient(app)

    def test_list_workflows_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.get(f"/api/llc/workflows/{_OTHER_COMPANY}")
        assert resp.status_code == 401

    def test_create_workflow_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.post(f"/api/llc/workflows/{_OTHER_COMPANY}", json={"workflow_id": "wf-1"})
        assert resp.status_code == 401


class TestWorkflowsScopeGuard:
    def test_list_own_company_returns_200(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.get(f"/api/llc/workflows/{company_id}")
        assert resp.status_code == 200

    def test_list_other_company_returns_404(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.get(f"/api/llc/workflows/{_OTHER_COMPANY}")
        assert resp.status_code == 404

    def test_list_platform_admin_other_company_allowed(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id, is_platform_admin=True)
        resp = client.get(f"/api/llc/workflows/{_OTHER_COMPANY}")
        assert resp.status_code == 200

    def test_create_own_company_returns_201(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        with patch("llc.api.workflows.WorkflowService.get", new=AsyncMock(return_value=None)):
            resp = client.post(f"/api/llc/workflows/{company_id}", json={"workflow_id": "wf-1"})
        assert resp.status_code == 201

    def test_create_other_company_returns_404(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.post(f"/api/llc/workflows/{_OTHER_COMPANY}", json={"workflow_id": "wf-1"})
        assert resp.status_code == 404

    def test_delete_other_company_returns_404(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.delete(f"/api/llc/workflows/{_OTHER_COMPANY}/wf-1")
        assert resp.status_code == 404

    def test_delete_own_company_returns_204(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.delete(f"/api/llc/workflows/{company_id}/wf-1")
        assert resp.status_code == 204

    def test_get_by_id_own_company_returns_200(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.get(f"/api/llc/workflows/{company_id}/wf-1")
        assert resp.status_code == 200

    def test_get_by_id_other_company_returns_404(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.get(f"/api/llc/workflows/{_OTHER_COMPANY}/wf-1")
        assert resp.status_code == 404

    def test_patch_own_company_returns_200(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.patch(f"/api/llc/workflows/{company_id}/wf-1", json={"status": "executing"})
        assert resp.status_code == 200

    def test_patch_other_company_returns_404(self):
        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.patch(f"/api/llc/workflows/{_OTHER_COMPANY}/wf-1", json={"status": "executing"})
        assert resp.status_code == 404


class TestWorkflowsActorDerivation:
    """Mirrors #13969 review M1: the audit-trail actor must come from the
    authenticated session, never from client-supplied input."""

    def test_create_derives_actor_from_authenticated_user(self):
        from llc.api.workflows import WorkflowService  # noqa: PLC0415

        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        with patch("llc.api.workflows.WorkflowService.get", new=AsyncMock(return_value=None)):
            resp = client.post(f"/api/llc/workflows/{company_id}", json={"workflow_id": "wf-1"})
        assert resp.status_code == 201
        _, kwargs = WorkflowService.create.call_args
        assert kwargs["actor"] == _FIXED_USER_ID

    def test_delete_derives_actor_from_authenticated_user(self):
        from llc.api.workflows import WorkflowService  # noqa: PLC0415

        company_id = str(uuid.uuid4())
        client = _make_client(company_id)
        resp = client.delete(f"/api/llc/workflows/{company_id}/wf-1")
        assert resp.status_code == 204
        _, kwargs = WorkflowService.delete.call_args
        assert kwargs["actor"] == _FIXED_USER_ID
