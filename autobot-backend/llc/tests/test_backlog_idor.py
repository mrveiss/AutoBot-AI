# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Auth + IDOR hardening tests for backlog.py routes (GH#12136).

llc/api/backlog.py previously depended only on ``get_session`` — no
authentication and no tenant-authorization dependency. Mirrors
test_goals_idor.py / test_boards_idor.py: no auth -> 401, cross-tenant -> 404,
same-tenant -> success.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
_OTHER_ORG = "99999999-9999-9999-9999-999999999999"


def _make_client(caller_org_id: str, is_platform_admin: bool = False) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.backlog import get_session, router  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router, prefix="/api/llc")

    async def _fake_session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org_id), user_id=_FIXED_USER_ID, is_platform_admin=is_platform_admin
    )

    mock_svc_factory = patch("llc.api.backlog._service").start()
    mock_svc_factory.return_value.list_backlog = AsyncMock(return_value=([], 0))
    mock_svc_factory.return_value.bulk_assign_sprint = AsyncMock(return_value=2)

    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


class TestBacklogNoAuth:
    def test_get_backlog_no_token_returns_401(self):
        from llc.api.backlog import get_session, router

        app = FastAPI()
        app.include_router(router, prefix="/api/llc")

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_session] = _fake_session

        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = TestClient(app)
            resp = client.get("/api/llc/backlog", params={"company_id": str(uuid.uuid4())})
        assert resp.status_code == 401


class TestBacklogIdor:
    def test_get_backlog_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get("/api/llc/backlog", params={"company_id": org})
        assert resp.status_code == 200

    def test_get_backlog_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get("/api/llc/backlog", params={"company_id": _OTHER_ORG})
        assert resp.status_code == 404

    def test_get_backlog_platform_admin_cross_tenant_allowed(self):
        org = str(uuid.uuid4())
        client = _make_client(org, is_platform_admin=True)
        resp = client.get("/api/llc/backlog", params={"company_id": _OTHER_ORG})
        assert resp.status_code == 200

    def test_bulk_assign_sprint_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            "/api/llc/backlog/bulk-assign-sprint",
            json={"company_id": org, "sprint_id": str(uuid.uuid4()), "work_item_ids": [str(uuid.uuid4())]},
        )
        assert resp.status_code == 200

    def test_bulk_assign_sprint_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            "/api/llc/backlog/bulk-assign-sprint",
            json={"company_id": _OTHER_ORG, "sprint_id": str(uuid.uuid4()), "work_item_ids": [str(uuid.uuid4())]},
        )
        assert resp.status_code == 404
