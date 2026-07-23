# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Auth + IDOR hardening tests for goals.py routes (GH#12136).

Prior to this fix every handler in llc/api/goals.py depended only on
``get_async_session`` — no authentication and no tenant-authorization
dependency — allowing an unauthenticated caller to create/read/update/delete
goals in ANY company by supplying an arbitrary ``company_id``/``goal_id``
(missing-authentication + IDOR).

Mirrors test_boards_idor.py / test_sprints_idor.py / test_work_items_idor.py:
  - no auth at all                     -> 401
  - authenticated, cross-tenant access -> 404 (existence disclosure avoided)
  - authenticated, same-tenant access  -> the expected success status
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
_OTHER_ORG = "99999999-9999-9999-9999-999999999999"


def _make_goal(company_id: str) -> MagicMock:
    goal = MagicMock()
    goal.id = uuid.uuid4()
    goal.company_id = company_id
    goal.parent_goal_id = None
    goal.title = "Test Goal"
    goal.description = None
    goal.level = "vision"
    goal.status = "draft"
    goal.owner_agent_id = None
    goal.due_date = None
    goal.created_at = datetime.now(timezone.utc)
    goal.updated_at = datetime.now(timezone.utc)
    return goal


def _make_client(
    caller_org_id: str,
    goal_company_id: Optional[str] = None,
    goal_exists: bool = True,
    is_platform_admin: bool = False,
) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.goals import router as goals_router  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(goals_router, prefix="/api/llc")

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_async_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org_id), user_id=_FIXED_USER_ID, is_platform_admin=is_platform_admin
    )

    gcid = goal_company_id if goal_company_id is not None else caller_org_id
    goal = _make_goal(gcid) if goal_exists else None

    patch("llc.api.goals.GoalService.get", new=AsyncMock(return_value=goal)).start()
    patch("llc.api.goals.GoalService.list_by_company", new=AsyncMock(return_value=[goal] if goal else [])).start()
    patch("llc.api.goals.GoalService.create", new=AsyncMock(return_value=goal)).start()
    patch("llc.api.goals.GoalService.update", new=AsyncMock(return_value=goal)).start()
    patch("llc.api.goals.GoalService.delete", new=AsyncMock(return_value=True)).start()
    patch("llc.api.goals.GoalService.get_ancestors", new=AsyncMock(return_value=[])).start()

    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=items_result)

    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


class TestGoalsNoAuth:
    """No credentials at all -> 401 (real get_current_user, not overridden)."""

    def _make_unauthenticated_client(self) -> TestClient:
        from llc.api.goals import router as goals_router
        from user_management.database import get_async_session

        app = FastAPI()
        app.include_router(goals_router, prefix="/api/llc")

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_async_session] = _fake_session
        return TestClient(app)

    def test_list_goals_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.get("/api/llc/goals", params={"company_id": str(uuid.uuid4())})
        assert resp.status_code == 401

    def test_get_goal_no_token_returns_401(self):
        with patch("api.user_management.dependencies.get_auth_middleware") as mock_mw:
            mock_mw.return_value.get_user_from_request.return_value = None
            client = self._make_unauthenticated_client()
            resp = client.get(f"/api/llc/goals/{uuid.uuid4()}")
        assert resp.status_code == 401


class TestGoalsIdor:
    # --- list ---

    def test_list_goals_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get("/api/llc/goals", params={"company_id": org})
        assert resp.status_code == 200

    def test_list_goals_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get("/api/llc/goals", params={"company_id": _OTHER_ORG})
        assert resp.status_code == 404

    def test_list_goals_platform_admin_cross_tenant_allowed(self):
        org = str(uuid.uuid4())
        client = _make_client(org, is_platform_admin=True)
        resp = client.get("/api/llc/goals", params={"company_id": _OTHER_ORG})
        assert resp.status_code == 200

    # --- create ---

    def test_create_goal_own_company_returns_201(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            "/api/llc/goals",
            json={"company_id": org, "title": "Vision", "level": "vision"},
        )
        assert resp.status_code == 201

    def test_create_goal_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            "/api/llc/goals",
            json={"company_id": _OTHER_ORG, "title": "Hijack", "level": "vision"},
        )
        assert resp.status_code == 404

    # --- get by id ---

    def test_get_goal_own_tenant_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org, goal_company_id=org)
        resp = client.get(f"/api/llc/goals/{uuid.uuid4()}")
        assert resp.status_code == 200

    def test_get_goal_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org, goal_company_id=_OTHER_ORG)
        resp = client.get(f"/api/llc/goals/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_get_goal_not_found_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org, goal_exists=False)
        resp = client.get(f"/api/llc/goals/{uuid.uuid4()}")
        assert resp.status_code == 404

    # --- update ---

    def test_update_goal_own_tenant_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org, goal_company_id=org)
        resp = client.patch(f"/api/llc/goals/{uuid.uuid4()}", json={"title": "New"})
        assert resp.status_code == 200

    def test_update_goal_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org, goal_company_id=_OTHER_ORG)
        resp = client.patch(f"/api/llc/goals/{uuid.uuid4()}", json={"title": "Hijack"})
        assert resp.status_code == 404

    # --- delete ---

    def test_delete_goal_own_tenant_returns_204(self):
        org = str(uuid.uuid4())
        client = _make_client(org, goal_company_id=org)
        resp = client.delete(f"/api/llc/goals/{uuid.uuid4()}")
        assert resp.status_code == 204

    def test_delete_goal_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org, goal_company_id=_OTHER_ORG)
        resp = client.delete(f"/api/llc/goals/{uuid.uuid4()}")
        assert resp.status_code == 404

    # --- ancestors ---

    def test_ancestors_own_tenant_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org, goal_company_id=org)
        resp = client.get(f"/api/llc/goals/{uuid.uuid4()}/ancestors")
        assert resp.status_code == 200

    def test_ancestors_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org, goal_company_id=_OTHER_ORG)
        resp = client.get(f"/api/llc/goals/{uuid.uuid4()}/ancestors")
        assert resp.status_code == 404

    # --- tasks ---

    def test_tasks_own_tenant_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_client(org, goal_company_id=org)
        resp = client.get(f"/api/llc/goals/{uuid.uuid4()}/tasks")
        assert resp.status_code == 200

    def test_tasks_cross_tenant_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_client(org, goal_company_id=_OTHER_ORG)
        resp = client.get(f"/api/llc/goals/{uuid.uuid4()}/tasks")
        assert resp.status_code == 404
