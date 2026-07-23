# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Auth + IDOR regression tests for llc/api/goals.py routes (GH#12136).

Before GH#12136 every goals route declared only ``Depends(get_async_session)``
with no ``get_current_user`` / ``require_org_context`` — an unauthenticated
caller could CRUD any company's goals (missing-auth + IDOR).

These tests assert:
  (a) an unauthenticated request is rejected (401), never served (200);
  (b) an authenticated caller from org A requesting org B's goal → 403 (IDOR);
  (c) an authenticated same-tenant caller still succeeds (200/201/204).

The unauthenticated cases work by overriding ``get_current_user`` to raise 401
exactly as the real dependency does when no user is present: if a route did NOT
declare the dependency the override would be a no-op and the request would
return 200 — so a passing test proves the dependency is wired on that route.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


def _make_goal(company_id: str) -> MagicMock:
    m = MagicMock()
    m.id = uuid.uuid4()
    m.company_id = company_id
    m.parent_goal_id = None
    m.title = "Test Goal"
    m.description = None
    m.level = "vision"
    m.status = "draft"
    m.owner_agent_id = None
    m.due_date = None
    m.created_at = datetime.now(timezone.utc)
    m.updated_at = datetime.now(timezone.utc)
    return m


def _make_app(
    *,
    authenticated: bool = True,
    caller_org_id: str,
    goal_company_id: str = None,
    goal_exists: bool = True,
) -> TestClient:
    """Build a FastAPI test client for goals auth/IDOR tests."""
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.goals import router as goals_router  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(goals_router)

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    goal_cid = goal_company_id if goal_company_id is not None else caller_org_id
    mock_goal = _make_goal(goal_cid) if goal_exists else None

    async def _fake_session():
        yield mock_session

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=mock_goal)
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        return result

    mock_session.execute = _execute

    app.dependency_overrides[get_async_session] = _fake_session

    def _fake_user() -> dict:
        if not authenticated:
            raise HTTPException(status_code=401, detail="Authentication required")
        return {"id": str(_FIXED_USER_ID), "user_id": str(_FIXED_USER_ID)}

    def _fake_tenant() -> TenantContext:
        if not authenticated:
            raise HTTPException(status_code=401, detail="Authentication required")
        return TenantContext(org_id=uuid.UUID(caller_org_id), user_id=_FIXED_USER_ID, is_platform_admin=False)

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[require_org_context] = _fake_tenant

    # GoalService.get returns the mock goal (used by goal_id-keyed routes).
    patch("llc.services.goal.GoalService.get", new=AsyncMock(return_value=mock_goal)).start()
    patch("llc.services.goal.GoalService.list_by_company", new=AsyncMock(return_value=[])).start()
    patch("llc.services.goal.GoalService.get_ancestors", new=AsyncMock(return_value=[])).start()
    patch("llc.services.goal.GoalService.delete", new=AsyncMock(return_value=True)).start()
    patch("llc.services.goal.GoalService.update", new=AsyncMock(return_value=mock_goal)).start()
    patch("llc.services.goal.GoalService.create", new=AsyncMock(return_value=mock_goal)).start()

    return TestClient(app, raise_server_exceptions=True)


class TestGoalsUnauthenticated:
    """(a) No credentials → 401, never 200."""

    def teardown_method(self, _m):
        patch.stopall()

    def test_list_unauth_rejected(self):
        org = str(uuid.uuid4())
        client = _make_app(authenticated=False, caller_org_id=org)
        resp = client.get(f"/goals?company_id={org}")
        assert resp.status_code == 401

    def test_create_unauth_rejected(self):
        org = str(uuid.uuid4())
        client = _make_app(authenticated=False, caller_org_id=org)
        resp = client.post("/goals", json={"company_id": org, "title": "X", "level": "vision"})
        assert resp.status_code == 401

    def test_get_goal_unauth_rejected(self):
        org = str(uuid.uuid4())
        client = _make_app(authenticated=False, caller_org_id=org)
        resp = client.get(f"/goals/{uuid.uuid4()}")
        assert resp.status_code == 401

    def test_delete_goal_unauth_rejected(self):
        org = str(uuid.uuid4())
        client = _make_app(authenticated=False, caller_org_id=org)
        resp = client.delete(f"/goals/{uuid.uuid4()}")
        assert resp.status_code == 401


class TestGoalsCrossTenantIdor:
    """(b) org A caller against org B's goal → 403."""

    def teardown_method(self, _m):
        patch.stopall()

    def test_get_cross_tenant_403(self):
        caller, other = str(uuid.uuid4()), str(uuid.uuid4())
        client = _make_app(caller_org_id=caller, goal_company_id=other)
        resp = client.get(f"/goals/{uuid.uuid4()}")
        assert resp.status_code == 403

    def test_patch_cross_tenant_403(self):
        caller, other = str(uuid.uuid4()), str(uuid.uuid4())
        client = _make_app(caller_org_id=caller, goal_company_id=other)
        resp = client.patch(f"/goals/{uuid.uuid4()}", json={"title": "Hacked"})
        assert resp.status_code == 403

    def test_delete_cross_tenant_403(self):
        caller, other = str(uuid.uuid4()), str(uuid.uuid4())
        client = _make_app(caller_org_id=caller, goal_company_id=other)
        resp = client.delete(f"/goals/{uuid.uuid4()}")
        assert resp.status_code == 403

    def test_ancestors_cross_tenant_403(self):
        caller, other = str(uuid.uuid4()), str(uuid.uuid4())
        client = _make_app(caller_org_id=caller, goal_company_id=other)
        resp = client.get(f"/goals/{uuid.uuid4()}/ancestors")
        assert resp.status_code == 403

    def test_tasks_cross_tenant_403(self):
        caller, other = str(uuid.uuid4()), str(uuid.uuid4())
        client = _make_app(caller_org_id=caller, goal_company_id=other)
        resp = client.get(f"/goals/{uuid.uuid4()}/tasks")
        assert resp.status_code == 403

    def test_list_cross_tenant_403(self):
        caller, other = str(uuid.uuid4()), str(uuid.uuid4())
        client = _make_app(caller_org_id=caller)
        resp = client.get(f"/goals?company_id={other}")
        assert resp.status_code == 403

    def test_create_cross_tenant_403(self):
        caller, other = str(uuid.uuid4()), str(uuid.uuid4())
        client = _make_app(caller_org_id=caller)
        resp = client.post("/goals", json={"company_id": other, "title": "X", "level": "vision"})
        assert resp.status_code == 403

    def test_get_missing_goal_404(self):
        caller = str(uuid.uuid4())
        client = _make_app(caller_org_id=caller, goal_exists=False)
        resp = client.get(f"/goals/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestGoalsSameTenantAllowed:
    """(c) Authorized same-tenant caller still works."""

    def teardown_method(self, _m):
        patch.stopall()

    def test_get_same_tenant_200(self):
        org = str(uuid.uuid4())
        client = _make_app(caller_org_id=org, goal_company_id=org)
        resp = client.get(f"/goals/{uuid.uuid4()}")
        assert resp.status_code == 200

    def test_list_same_tenant_200(self):
        org = str(uuid.uuid4())
        client = _make_app(caller_org_id=org)
        resp = client.get(f"/goals?company_id={org}")
        assert resp.status_code == 200

    def test_create_same_tenant_201(self):
        org = str(uuid.uuid4())
        client = _make_app(caller_org_id=org)
        resp = client.post("/goals", json={"company_id": org, "title": "X", "level": "vision"})
        assert resp.status_code == 201

    def test_delete_same_tenant_204(self):
        org = str(uuid.uuid4())
        client = _make_app(caller_org_id=org, goal_company_id=org)
        resp = client.delete(f"/goals/{uuid.uuid4()}")
        assert resp.status_code == 204

    def test_ancestors_same_tenant_200(self):
        org = str(uuid.uuid4())
        client = _make_app(caller_org_id=org, goal_company_id=org)
        resp = client.get(f"/goals/{uuid.uuid4()}/ancestors")
        assert resp.status_code == 200
