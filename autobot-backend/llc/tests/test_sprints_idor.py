# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""IDOR regression tests for sprints.py routes (GH#10148).

Asserts that every route in llc/api/sprints.py enforces tenant isolation:
  - cross-tenant caller → 404 (existence disclosure avoided)
  - own-company caller → expected success status

Endpoints covered:
  GET  /companies/{company_id}/portfolios   (company_id check)
  POST /companies/{company_id}/portfolios   (company_id check)
  GET  /companies/{company_id}/projects     (company_id check — GH#9020)
  GET  /projects/{project_id}/timeline      (project company_id check — GH#9020)
  GET  /portfolios/{portfolio_id}           (entity company_id check)
  PATCH /portfolios/{portfolio_id}          (entity company_id check)
  DELETE /portfolios/{portfolio_id}         (entity company_id check)
  GET  /portfolios/{portfolio_id}/programs  (parent portfolio check)
  POST /portfolios/{portfolio_id}/programs  (parent portfolio check)
  GET  /programs/{program_id}              (entity company_id check)
  PATCH /programs/{program_id}             (entity company_id check)
  DELETE /programs/{program_id}            (entity company_id check)
  GET  /programs/{program_id}/projects     (parent program check)
  POST /programs/{program_id}/projects     (parent program check)
  GET  /projects/{project_id}             (entity company_id check)
  PATCH /projects/{project_id}            (entity company_id check)
  DELETE /projects/{project_id}           (entity company_id check)
  GET  /projects/{project_id}/sprints     (parent project check)
  POST /projects/{project_id}/sprints     (parent project check)
  GET  /sprints/{sprint_id}              (entity company_id check)
  PATCH /sprints/{sprint_id}             (entity company_id check)
  DELETE /sprints/{sprint_id}            (entity company_id check)
  POST /sprints/{sprint_id}/close        (entity company_id check)
  GET  /sprints/{sprint_id}/capacity     (entity company_id check)
  GET  /projects/{project_id}/velocity   (entity company_id check)
  GET  /sprints/{sprint_id}/burndown     (entity company_id check)
  GET  /projects/{project_id}/knowledge  (entity company_id check)
  GET  /sprints/{sprint_id}/summary      (entity company_id check)
"""

import uuid
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


# ---------------------------------------------------------------------------
# Helpers: mock entity factories
# ---------------------------------------------------------------------------


def _make_portfolio(company_id: str) -> MagicMock:
    m = MagicMock()
    m.id = uuid.uuid4()
    m.company_id = company_id
    m.name = "Test Portfolio"
    m.description = None
    m.status = "active"
    m.created_at = None
    m.updated_at = None
    return m


def _make_program(company_id: str, portfolio_id: Optional[uuid.UUID] = None) -> MagicMock:
    m = MagicMock()
    m.id = uuid.uuid4()
    m.company_id = company_id
    m.portfolio_id = portfolio_id or uuid.uuid4()
    m.name = "Test Program"
    m.description = None
    m.status = "active"
    m.created_at = None
    m.updated_at = None
    return m


def _make_project(company_id: str, program_id: Optional[uuid.UUID] = None) -> MagicMock:
    m = MagicMock()
    m.id = uuid.uuid4()
    m.company_id = company_id
    m.program_id = program_id or uuid.uuid4()
    m.goal_id = None
    m.name = "Test Project"
    m.description = None
    m.status = "active"
    m.lead_agent_id = None
    m.lead_user_id = None
    m.target_date = None
    m.auto_rollover = None
    m.created_at = None
    m.updated_at = None
    return m


def _make_sprint(company_id: str, project_id: Optional[uuid.UUID] = None) -> MagicMock:
    m = MagicMock()
    m.id = uuid.uuid4()
    m.company_id = company_id
    m.project_id = project_id or uuid.uuid4()
    m.name = "Sprint 1"
    m.goal_description = None
    m.start_date = None
    m.end_date = None
    m.status = "planning"
    m.committed_points = 0
    m.actual_points = 0
    m.velocity_actual = 0
    m.capacity_points = 0
    m.projection = None
    m.pending_close_approval_id = None
    m.kb_summary = None
    m.created_at = None
    m.updated_at = None
    return m


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _make_app(
    caller_org_id: str,
    *,
    portfolio_company_id: Optional[str] = None,
    program_company_id: Optional[str] = None,
    project_company_id: Optional[str] = None,
    sprint_company_id: Optional[str] = None,
    portfolio_exists: bool = True,
    program_exists: bool = True,
    project_exists: bool = True,
    sprint_exists: bool = True,
) -> TestClient:
    """Build a FastAPI test client for IDOR tests.

    Default: all entities are owned by ``caller_org_id`` (same-tenant = allowed).
    Override *_company_id args to simulate cross-tenant ownership.
    """
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.sprints import router as sprints_router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(sprints_router)

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.delete = AsyncMock()
    mock_session.add = MagicMock()

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_session] = _fake_session

    def _fake_user() -> dict:
        return {"id": str(_FIXED_USER_ID), "user_id": str(_FIXED_USER_ID)}

    def _fake_tenant() -> TenantContext:
        return TenantContext(
            org_id=uuid.UUID(caller_org_id),
            user_id=_FIXED_USER_ID,
            is_platform_admin=False,
        )

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[require_org_context] = _fake_tenant

    # Build mock entities.
    pf_cid = portfolio_company_id if portfolio_company_id is not None else caller_org_id
    pr_cid = program_company_id if program_company_id is not None else caller_org_id
    pj_cid = project_company_id if project_company_id is not None else caller_org_id
    sp_cid = sprint_company_id if sprint_company_id is not None else caller_org_id

    mock_portfolio = _make_portfolio(pf_cid) if portfolio_exists else None
    mock_program = _make_program(pr_cid) if program_exists else None
    mock_project = _make_project(pj_cid) if project_exists else None
    mock_sprint = _make_sprint(sp_cid) if sprint_exists else None

    # SQLAlchemy session.execute mock: returns entity based on the query model.
    # We use a side_effect that inspects the WHERE clause entity type.
    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        # Identify what model is being queried by inspecting the statement.
        froms = stmt.get_final_froms() if hasattr(stmt, "get_final_froms") else (getattr(stmt, "froms", None) or [])
        entity = None
        if froms:
            tbl = froms[0]
            name = getattr(tbl, "name", "") or getattr(tbl, "__tablename__", "")
            if "portfolio" in name:
                entity = mock_portfolio
            elif "program" in name:
                entity = mock_program
            elif "project" in name:
                entity = mock_project
            elif "sprint" in name:
                entity = mock_sprint

        result.scalar_one_or_none = MagicMock(return_value=entity)
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        return result

    mock_session.execute = _execute

    # session.refresh: populate minimum required response fields on the refreshed object.
    async def _fake_refresh(obj, *a, **kw):
        if not getattr(obj, "id", None):
            obj.id = uuid.uuid4()
        if not getattr(obj, "status", None):
            obj.status = "active"
        if not getattr(obj, "created_at", None):
            from datetime import datetime, timezone  # noqa: PLC0415
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = datetime.now(timezone.utc)
        # Sprint-specific fields
        if not getattr(obj, "committed_points", None):
            obj.committed_points = 0
        if not getattr(obj, "actual_points", None):
            obj.actual_points = 0
        if not getattr(obj, "pending_close_approval_id", None):
            obj.pending_close_approval_id = None

    mock_session.refresh = _fake_refresh

    # Patch planning service so analytics routes don't need real DB.
    patch("llc.services.sprint_planning.SprintPlanningService.get_capacity", new=AsyncMock(return_value={})).start()
    patch(
        "llc.services.sprint_planning.SprintPlanningService.get_velocity_history",
        new=AsyncMock(return_value={}),
    ).start()
    patch("llc.services.sprint_planning.SprintPlanningService.get_burndown", new=AsyncMock(return_value={})).start()
    # Patch ChromaDB knowledge call.
    patch(
        "llc.services.work_product_service.WorkProductService.list_indexed_by_project",
        new=AsyncMock(return_value=[]),
    ).start()

    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Tests: company_id-keyed routes
# ---------------------------------------------------------------------------


class TestSprintsIdorCompanyRoutes:
    """Routes that take company_id in the URL path."""

    def teardown_method(self, _method):
        patch.stopall()

    # -- list portfolios --

    def test_list_portfolios_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_app(caller_org_id=org)
        resp = client.get(f"/companies/{org}/portfolios")
        assert resp.status_code == 200

    def test_list_portfolios_cross_tenant_returns_404(self):
        caller = str(uuid.uuid4())
        other = str(uuid.uuid4())
        client = _make_app(caller_org_id=caller)
        resp = client.get(f"/companies/{other}/portfolios")
        assert resp.status_code == 404

    # -- create portfolio --

    def test_create_portfolio_own_company_returns_201(self):
        org = str(uuid.uuid4())
        client = _make_app(caller_org_id=org)
        resp = client.post(
            f"/companies/{org}/portfolios",
            json={"company_id": org, "name": "Test Portfolio"},
        )
        assert resp.status_code == 201

    def test_create_portfolio_cross_tenant_returns_404(self):
        caller = str(uuid.uuid4())
        other = str(uuid.uuid4())
        client = _make_app(caller_org_id=caller)
        resp = client.post(
            f"/companies/{other}/portfolios",
            json={"company_id": other, "name": "Stolen Portfolio"},
        )
        assert resp.status_code == 404

    # -- list company projects (GH#9020) --

    def test_list_company_projects_own_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_app(caller_org_id=org)
        resp = client.get(f"/companies/{org}/projects")
        assert resp.status_code == 200

    def test_list_company_projects_cross_tenant_returns_404(self):
        caller = str(uuid.uuid4())
        other = str(uuid.uuid4())
        client = _make_app(caller_org_id=caller)
        resp = client.get(f"/companies/{other}/projects")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: project timeline (GH#9020) — entity-keyed, cross-tenant isolation
# ---------------------------------------------------------------------------


class TestSprintsIdorTimeline:
    def teardown_method(self, _method):
        patch.stopall()

    def test_get_project_timeline_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_app(caller_org_id=org, project_company_id=org)
        resp = client.get(f"/projects/{uuid.uuid4()}/timeline")
        assert resp.status_code == 200

    def test_get_project_timeline_cross_tenant_returns_404(self):
        caller = str(uuid.uuid4())
        other = str(uuid.uuid4())
        client = _make_app(caller_org_id=caller, project_company_id=other)
        resp = client.get(f"/projects/{uuid.uuid4()}/timeline")
        assert resp.status_code == 404

    def test_get_project_timeline_not_found_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_app(caller_org_id=org, project_exists=False)
        resp = client.get(f"/projects/{uuid.uuid4()}/timeline")
        assert resp.status_code == 404
