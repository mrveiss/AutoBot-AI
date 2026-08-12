# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tenant-scope tests for GET /api/llc/agent/context/{item_id} (#13756).

The route bound ``require_org_context`` but never applied it, so any
authenticated caller could read another company's work item, its goal
ancestry and its KB context by supplying the item UUID.
"""

import uuid
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
_COMPANY_A = "11111111-1111-1111-1111-111111111111"
_COMPANY_B = "22222222-2222-2222-2222-222222222222"


def _make_item(company_id: str) -> MagicMock:
    item = MagicMock()
    item.id = uuid.uuid4()
    item.company_id = company_id
    item.project_id = None
    item.goal_id = uuid.uuid4()
    item.title = "Company A private item"
    item.description = "Confidential"
    item.status = "todo"
    item.priority = "high"
    item.acceptance_criteria = "Never leaks"
    return item


def _make_app(caller_org_id: str, item: MagicMock):
    """FastAPI app for the context route, with a scope-honouring item store."""
    # Deferred imports: must not be at module level (see test_suggest_ac_endpoint.py).
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.context import router as context_router  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(context_router)

    async def _fake_session():
        yield AsyncMock()

    def _fake_user() -> dict:
        return {"id": str(_USER_ID), "user_id": str(_USER_ID)}

    def _fake_tenant() -> TenantContext:
        return TenantContext(org_id=uuid.UUID(caller_org_id), user_id=_USER_ID, is_platform_admin=False)

    app.dependency_overrides[get_async_session] = _fake_session
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[require_org_context] = _fake_tenant

    async def _scoped_get(_session, work_item_id, *, company_id: Optional[str] = None):
        """Stand in for the DB: the row is only visible under its own company."""
        if str(work_item_id) != str(item.id):
            return None
        if company_id is not None and str(company_id) != item.company_id:
            return None
        return item

    return app, _scoped_get


@pytest.mark.parametrize("mode", ["fat", "thin"])
def test_own_company_item_is_readable(mode: str) -> None:
    item = _make_item(_COMPANY_A)
    app, scoped_get = _make_app(_COMPANY_A, item)

    with (
        patch("llc.services.work_item_service.WorkItemService.get", new=AsyncMock(side_effect=scoped_get)),
        patch("llc.services.goal.GoalService.get_goal_ancestry_for_work_item", new=AsyncMock(return_value=[])),
        patch("llc.kb.rag_assembler.LLCRAGAssembler.assemble", new=AsyncMock(side_effect=Exception("no KB"))),
    ):
        response = TestClient(app).get(f"/agent/context/{item.id}?mode={mode}")

    assert response.status_code == 200
    assert response.json()["work_item_id"] == str(item.id)


@pytest.mark.parametrize("mode", ["fat", "thin"])
def test_other_companys_item_is_404(mode: str) -> None:
    """Company B's caller supplying company A's item UUID gets 404, no ancestry."""
    item = _make_item(_COMPANY_A)
    app, scoped_get = _make_app(_COMPANY_B, item)
    ancestry = AsyncMock(return_value=[{"id": "g1", "title": "Company A goal"}])

    with (
        patch("llc.services.work_item_service.WorkItemService.get", new=AsyncMock(side_effect=scoped_get)),
        patch("llc.services.goal.GoalService.get_goal_ancestry_for_work_item", new=ancestry),
    ):
        response = TestClient(app).get(f"/agent/context/{item.id}?mode={mode}")

    assert response.status_code == 404
    assert "Company A" not in response.text
    ancestry.assert_not_awaited()
