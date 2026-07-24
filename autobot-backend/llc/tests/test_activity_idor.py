# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""IDOR hardening tests for activity.py routes (#12215).

Mirrors test_boards_idor.py: GET /companies/{company_id}/activity previously
had no tenant check at all — any authenticated user could read any company's
activity log by supplying an arbitrary company_id path param. This confirms
the ``require_org_context`` + ``assert_company_access`` guard rejects a
mismatched (spoofed) company_id and accepts a matching one.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
_OTHER_ORG = "99999999-9999-9999-9999-999999999999"


def _make_client(caller_org_id: str) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.activity import router as activity_router  # noqa: PLC0415
    from llc.services.activity_log import ActivityLogPage  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(activity_router, prefix="/api/llc")

    async def _fake_session():
        yield AsyncMock()

    app.dependency_overrides[get_async_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_FIXED_USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(caller_org_id), user_id=_FIXED_USER_ID, is_platform_admin=False
    )

    empty_page = ActivityLogPage(items=[], page=1, page_size=50, total=0)
    patch("llc.api.activity._service.query", new=AsyncMock(return_value=empty_page)).start()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


class TestActivityLogIdor:
    def test_get_activity_own_tenant_ok(self):
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get(f"/api/llc/companies/{org}/activity")
        assert resp.status_code == 200

    def test_get_activity_cross_tenant_404(self):
        """Spoofed company_id (not the caller's own org) is rejected, not honoured."""
        org = str(uuid.uuid4())
        client = _make_client(org)
        resp = client.get(f"/api/llc/companies/{_OTHER_ORG}/activity")
        assert resp.status_code == 404
