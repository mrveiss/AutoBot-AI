# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The co-worker route answers a refusal with its public text, a plain ValueError with fixed text (#21579)."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api.work_items import router as work_items_router
from llc.deps import get_session
from llc.services.company_os.errors import CompanyOsNotFound
from llc.services.work_item_service import CoWorkingPermissionError
from user_management.services import TenantContext

USER_ID = uuid.uuid4()
ORG = str(uuid.uuid4())
DENIAL = "Only a board member or the lead may change co-workers"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(work_items_router)

    async def _session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(USER_ID), "user_id": str(USER_ID)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=uuid.UUID(ORG), user_id=USER_ID, is_platform_admin=False
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _post_coworker(error: Exception):
    existing = SimpleNamespace(company_id=ORG)
    patch("llc.services.work_item_service.WorkItemService.get", new=AsyncMock(return_value=existing)).start()
    patch("llc.api.work_items.resolve_actor_role", new=AsyncMock(return_value="member")).start()
    patch(
        "llc.api.work_items.require_member_targets", new=AsyncMock()
    ).start()  # membership: test_named_targets_*_20521
    patch("llc.services.work_item_service.WorkItemService.enable_coworking", new=AsyncMock(side_effect=error)).start()
    body = {"co_worker_type": "agent", "co_worker_agent_id": str(uuid.uuid4())}
    return _client().post(f"/work-items/{uuid.uuid4()}/coworker", json=body)


def test_permission_refusal_is_403_with_its_public_text():
    resp = _post_coworker(CoWorkingPermissionError(DENIAL))
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == DENIAL


def test_missing_work_item_is_404_with_its_public_text():
    resp = _post_coworker(CompanyOsNotFound("Work item 7 not found"))
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Work item 7 not found"


def test_plain_value_error_is_422_with_fixed_text_never_its_own():
    resp = _post_coworker(ValueError("LEAK-MARKER postgres://db.internal:5432"))
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == "Unprocessable request"
    assert "LEAK-MARKER" not in resp.text
