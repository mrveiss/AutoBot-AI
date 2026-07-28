# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""IDOR hardening tests for routines.py routes (#12215).

Mirrors test_boards_idor.py / test_sprints_idor.py: routines.py previously
had NO tenant check at all — any authenticated user could list/create
routines for an arbitrary company, or read/update/delete/trigger any other
company's routine by UUID. This confirms every route now enforces
``require_org_context`` + ``assert_company_access``, so a caller in org A
cannot act on org B's routines (cross-tenant → 404, own-tenant → success).
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llc.models.enums import RoutineProduces, RoutineStatus
from llc.models.routine import LLCRoutine
from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
_OTHER_ORG = "99999999-9999-9999-9999-999999999999"


def _routine(company_id: str) -> MagicMock:
    row = MagicMock(spec=LLCRoutine)
    row.id = uuid.uuid4()
    row.company_id = uuid.UUID(company_id)
    row.name = "nightly-sync"
    row.cron_schedule = "*/5 * * * *"
    row.description = None
    row.env = {}
    row.status = RoutineStatus.ACTIVE
    row.produces = RoutineProduces.NEW_WORK_ITEM
    row.work_item_template = {}
    row.assignee_agent_id = None
    row.recurring_work_item_id = None
    row.last_fired_at = None
    row.created_at = datetime.now(tz=timezone.utc)
    row.updated_at = datetime.now(tz=timezone.utc)
    return row


def _make_client(caller_org_id: str, routine: Optional[MagicMock] = None) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.routines import router as routines_router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(routines_router, prefix="/api/llc")

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org_id), user_id=_FIXED_USER_ID, is_platform_admin=False
    )

    patch("llc.services.routine_service.RoutineService.get", new=AsyncMock(return_value=routine)).start()
    patch("llc.services.routine_service.RoutineService.list", new=AsyncMock(return_value=[])).start()
    patch(
        "llc.services.routine_service.RoutineService.create",
        new=AsyncMock(return_value=_routine(caller_org_id)),
    ).start()
    patch("llc.services.routine_service.RoutineService.delete", new=AsyncMock(return_value=None)).start()
    patch("llc.services.routine_service.RoutineService.list_runs", new=AsyncMock(return_value=[])).start()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


class TestRoutinesIdor:
    def test_get_routine_own_tenant_ok(self):
        org = str(uuid.uuid4())
        routine = _routine(org)
        client = _make_client(org, routine=routine)
        resp = client.get(f"/api/llc/routines/{routine.id}")
        assert resp.status_code == 200

    def test_get_routine_cross_tenant_404(self):
        org = str(uuid.uuid4())
        routine = _routine(_OTHER_ORG)
        client = _make_client(org, routine=routine)
        resp = client.get(f"/api/llc/routines/{routine.id}")
        assert resp.status_code == 404

    def test_delete_routine_cross_tenant_404(self):
        org = str(uuid.uuid4())
        routine = _routine(_OTHER_ORG)
        client = _make_client(org, routine=routine)
        resp = client.delete(f"/api/llc/routines/{routine.id}")
        assert resp.status_code == 404

    def test_trigger_routine_cross_tenant_404(self):
        org = str(uuid.uuid4())
        routine = _routine(_OTHER_ORG)
        client = _make_client(org, routine=routine)
        resp = client.post(f"/api/llc/routines/{routine.id}/trigger")
        assert resp.status_code == 404

    def test_list_routine_runs_cross_tenant_404(self):
        org = str(uuid.uuid4())
        routine = _routine(_OTHER_ORG)
        client = _make_client(org, routine=routine)
        resp = client.get(f"/api/llc/routines/{routine.id}/runs")
        assert resp.status_code == 404

    def test_update_routine_cross_tenant_404(self):
        org = str(uuid.uuid4())
        routine = _routine(_OTHER_ORG)
        client = _make_client(org, routine=routine)
        resp = client.patch(f"/api/llc/routines/{routine.id}", json={"name": "renamed"})
        assert resp.status_code == 404

    def test_list_routines_rejects_foreign_company(self):
        """Spoofed company_id (not the caller's own org) is rejected, not honoured."""
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get(f"/api/llc/companies/{_OTHER_ORG}/routines")
        assert resp.status_code == 404

    def test_create_routine_rejects_foreign_company(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.post(
            f"/api/llc/companies/{_OTHER_ORG}/routines",
            json={"name": "x", "cron_schedule": "*/5 * * * *", "produces": "new_work_item"},
        )
        assert resp.status_code == 404

    def test_list_routines_own_company_ok(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get(f"/api/llc/companies/{org}/routines")
        assert resp.status_code == 200
