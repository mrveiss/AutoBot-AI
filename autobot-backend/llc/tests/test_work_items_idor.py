# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""IDOR hardening tests for work_items.py routes (GH#9861).

Tests that GET /work-items/{id}, PATCH /work-items/{id},
DELETE /work-items/{id}, GET /work-items/{id}/products, and
GET /work-items/{id}/handoff-brief all enforce tenant isolation.
"""

import uuid
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from user_management.services import TenantContext

_FIXED_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _make_idor_app(
    caller_org_id: str,
    item_company_id: Optional[str] = None,
    item_exists: bool = True,
):
    """Build a FastAPI test app for IDOR tests.

    caller_org_id: the org_id injected into the TenantContext.
    item_company_id: company_id on the work item returned by the service.
                     Defaults to caller_org_id (same tenant = allowed).
    item_exists: if False, WorkItemService.get() returns None.
    """
    # Deferred imports: must not be at module level (see test_suggest_ac_endpoint.py).
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.work_items import router as wi_router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(wi_router)

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.delete = AsyncMock()

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_session] = _fake_session

    # Auth overrides.
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

    # Service mock: WorkItemService.get()
    effective_company = item_company_id if item_company_id is not None else caller_org_id
    if item_exists:
        mock_item = MagicMock()
        mock_item.company_id = effective_company
        mock_item.title = "Mock item"
        mock_item.description = None
        mock_item.acceptance_criteria = []
        mock_item.status = "backlog"
        mock_item.priority = "medium"
        mock_item.story_points = None
        mock_item.labels = []
        mock_item.parent_id = None
        mock_item.project_id = None
        mock_item.sprint_id = None
        mock_item.goal_id = None
        mock_item.assignee_agent_id = None
        mock_item.assignee_user_id = None
        mock_item.assignee_type = None
        mock_item.checkout_run_id = None
        mock_item.checkout_locked_at = None
        mock_item.checkout_intent = None
        mock_item.version = 1
        mock_item.created_by_agent_id = None
        mock_item.created_by_user_id = None
        mock_item.reviewer_user_id = None
        mock_item.reviewer_agent_id = None
        mock_item.started_at = None
        mock_item.completed_at = None
        mock_item.cancelled_at = None
        mock_item.review_brief = None
        mock_item.created_at = None
        mock_item.updated_at = None
        mock_item.outgoing_relations = []
        mock_item.incoming_relations = []
        mock_item.id = uuid.uuid4()
        mock_item.identifier = "WI-001"
        mock_item.type = "task"
        # Make co_working_enabled falsy so _coworker_display returns None.
        mock_item.co_working_enabled = False
    else:
        mock_item = None

    patch("llc.services.work_item_service.WorkItemService.get", new=AsyncMock(return_value=mock_item)).start()
    # Also patch WorkItemService.update to return mock_item so PATCH succeeds.
    patch("llc.services.work_item_service.WorkItemService.update", new=AsyncMock(return_value=mock_item)).start()
    # Patch product service for /products route.
    patch(
        "llc.services.work_product_service.WorkProductService.list_by_work_item",
        new=AsyncMock(return_value=[]),
    ).start()
    # Patch handoff brief for /handoff-brief route.
    patch(
        "llc.services.handoff.HandoffService.get_brief",
        new=AsyncMock(return_value={"brief": "test"}),
    ).start()

    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWorkItemsIdor:
    def teardown_method(self, _method):
        patch.stopall()

    # GET own company → 200
    def test_get_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.get(f"/work-items/{uuid.uuid4()}")
        assert resp.status_code == 200

    # GET cross-tenant → 404
    def test_get_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.get(f"/work-items/{uuid.uuid4()}")
        assert resp.status_code == 404

    # GET not found → 404
    def test_get_not_found_returns_404(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_exists=False)
        resp = client.get(f"/work-items/{uuid.uuid4()}")
        assert resp.status_code == 404

    # PATCH own company → 200
    def test_patch_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.patch(f"/work-items/{uuid.uuid4()}", json={"title": "New title"})
        assert resp.status_code == 200

    # PATCH cross-tenant → 404
    def test_patch_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.patch(f"/work-items/{uuid.uuid4()}", json={"title": "Hijack"})
        assert resp.status_code == 404

    # DELETE own company → 204
    def test_delete_own_company_returns_204(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.delete(f"/work-items/{uuid.uuid4()}")
        assert resp.status_code == 204

    # DELETE cross-tenant → 404
    def test_delete_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.delete(f"/work-items/{uuid.uuid4()}")
        assert resp.status_code == 404

    # /products cross-tenant → 404
    def test_products_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.get(f"/work-items/{uuid.uuid4()}/products")
        assert resp.status_code == 404

    # /handoff-brief cross-tenant → 404
    def test_handoff_brief_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.get(f"/work-items/{uuid.uuid4()}/handoff-brief")
        assert resp.status_code == 404
