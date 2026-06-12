# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""IDOR hardening tests for work_items.py routes (GH#9861).

Tests that the following routes enforce tenant isolation (own=200/expected,
cross-tenant=404, in line with the pattern established in the original 5 routes):
  GET    /work-items/{id}
  PATCH  /work-items/{id}
  DELETE /work-items/{id}
  GET    /work-items/{id}/products
  GET    /work-items/{id}/handoff-brief
  POST   /work-items/{id}/checkout          (M4)
  POST   /work-items/{id}/release           (M4)
  POST   /work-items/{id}/transition        (M4)
  POST   /work-items/{id}/claim             (M4)
  POST   /work-items/{id}/unclaim           (M4)
  POST   /work-items/{id}/comments          (M4)
  POST   /work-items/{id}/review/approve    (M4)
  POST   /work-items/{id}/review/request-changes (M4)
  POST   /work-items/{id}/relations         (M4)
  DELETE /work-items/{id}/relations/{rid}   (M4)
  POST   /work-items/{id}/attachments       (M4)
  GET    /work-items/{id}/attachments       (M4)
  GET    /work-items/{id}/attachments/{aid}/download (M4)
  GET    /work-items/{id}/attachments/{aid}/text     (M4)
  DELETE /work-items/{id}/attachments/{aid}          (M4)
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
    # M4 route patches — service operations called after IDOR check.
    patch(
        "llc.services.work_item_service.WorkItemService.checkout",
        new=AsyncMock(return_value=mock_item),
    ).start()
    patch(
        "llc.services.work_item_service.WorkItemService.release",
        new=AsyncMock(return_value=mock_item),
    ).start()
    patch(
        "llc.services.work_item_service.WorkItemService.transition_status",
        new=AsyncMock(return_value=mock_item),
    ).start()
    patch(
        "llc.services.work_item_service.WorkItemService.claim_human",
        new=AsyncMock(return_value=mock_item),
    ).start()
    patch(
        "llc.services.work_item_service.WorkItemService.unclaim_human",
        new=AsyncMock(return_value=mock_item),
    ).start()
    _mock_comment = MagicMock()
    _mock_comment.id = uuid.uuid4()
    _mock_comment.work_item_id = uuid.uuid4()
    _mock_comment.company_id = caller_org_id
    _mock_comment.body = "test"
    _mock_comment.author_agent_id = None
    _mock_comment.author_user_id = None
    _mock_comment.created_at = None
    patch(
        "llc.services.work_item_service.WorkItemService.add_comment",
        new=AsyncMock(return_value=_mock_comment),
    ).start()
    patch(
        "llc.services.comment_wake_service.CommentWakeService.trigger_comment_wake",
        new=AsyncMock(return_value=None),
    ).start()
    patch(
        "llc.services.handoff.HandoffService.approve",
        new=AsyncMock(return_value=mock_item),
    ).start()
    patch(
        "llc.services.handoff.HandoffService.request_changes",
        new=AsyncMock(return_value=mock_item),
    ).start()
    _mock_rel = MagicMock()
    _mock_rel.id = uuid.uuid4()
    _mock_rel.relation_type = "blocks"
    patch(
        "llc.services.work_item_relations.WorkItemRelationService.add",
        new=AsyncMock(return_value=_mock_rel),
    ).start()
    patch(
        "llc.services.work_item_relations.WorkItemRelationService.remove",
        new=AsyncMock(return_value=None),
    ).start()
    _mock_attachment = MagicMock()
    _mock_attachment.id = uuid.uuid4()
    _mock_attachment.work_item_id = uuid.uuid4()
    _mock_attachment.company_id = caller_org_id
    _mock_attachment.filename = "test.txt"
    _mock_attachment.content_type = "text/plain"
    _mock_attachment.size_bytes = 4
    _mock_attachment.text_extracted = None
    _mock_attachment.uploaded_by_agent_id = None
    _mock_attachment.uploaded_by_user_id = None
    _mock_attachment.created_at = None
    patch(
        "llc.services.attachment_service.AttachmentService.upload",
        new=AsyncMock(return_value=_mock_attachment),
    ).start()
    patch(
        "llc.services.attachment_service.AttachmentService.list_attachments",
        new=AsyncMock(return_value=[]),
    ).start()
    patch(
        "llc.services.attachment_service.AttachmentService.download",
        new=AsyncMock(return_value=(_mock_attachment, b"data")),
    ).start()
    patch(
        "llc.services.attachment_service.AttachmentService.get_text",
        new=AsyncMock(return_value="extracted text"),
    ).start()
    patch(
        "llc.services.attachment_service.AttachmentService.delete",
        new=AsyncMock(return_value=None),
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


class TestWorkItemsIdorM4:
    """M4 tenant-isolation tests for routes hardened in the review-fix pass (GH#9861).

    Each test follows the same pattern: own company → expected success status,
    cross-tenant → 404.
    """

    def teardown_method(self, _method):
        from unittest.mock import patch

        patch.stopall()

    # --- checkout ---

    def test_checkout_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.post(f"/work-items/{uuid.uuid4()}/checkout", json={"agent_id": "agent-1"})
        assert resp.status_code == 200

    def test_checkout_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.post(f"/work-items/{uuid.uuid4()}/checkout", json={"agent_id": "agent-1"})
        assert resp.status_code == 404

    # --- release ---

    def test_release_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.post(f"/work-items/{uuid.uuid4()}/release", json={"agent_id": "agent-1"})
        assert resp.status_code == 200

    def test_release_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.post(f"/work-items/{uuid.uuid4()}/release", json={"agent_id": "agent-1"})
        assert resp.status_code == 404

    # --- transition ---

    def test_transition_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.post(f"/work-items/{uuid.uuid4()}/transition", json={"status": "in_progress"})
        assert resp.status_code == 200

    def test_transition_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.post(f"/work-items/{uuid.uuid4()}/transition", json={"status": "in_progress"})
        assert resp.status_code == 404

    # --- claim ---

    def test_claim_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/claim",
            json={"user_id": str(uuid.uuid4()), "company_id": org},
        )
        assert resp.status_code == 200

    def test_claim_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/claim",
            json={"user_id": str(uuid.uuid4()), "company_id": caller_org},
        )
        assert resp.status_code == 404

    # --- unclaim ---

    def test_unclaim_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/unclaim",
            json={"user_id": str(uuid.uuid4()), "company_id": org},
        )
        assert resp.status_code == 200

    def test_unclaim_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/unclaim",
            json={"user_id": str(uuid.uuid4()), "company_id": caller_org},
        )
        assert resp.status_code == 404

    # --- comments ---

    def test_comments_own_company_returns_201(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/comments",
            json={"company_id": org, "body": "hello"},
        )
        assert resp.status_code == 201

    def test_comments_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/comments",
            json={"company_id": caller_org, "body": "hello"},
        )
        assert resp.status_code == 404

    # --- review/approve ---

    def test_review_approve_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/review/approve",
            json={"reviewer_user_id": str(uuid.uuid4()), "company_id": org},
        )
        assert resp.status_code == 200

    def test_review_approve_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/review/approve",
            json={"reviewer_user_id": str(uuid.uuid4()), "company_id": caller_org},
        )
        assert resp.status_code == 404

    # --- review/request-changes ---

    def test_review_request_changes_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/review/request-changes",
            json={
                "reviewer_user_id": str(uuid.uuid4()),
                "company_id": org,
                "change_request": "Please fix tests",
            },
        )
        assert resp.status_code == 200

    def test_review_request_changes_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/review/request-changes",
            json={
                "reviewer_user_id": str(uuid.uuid4()),
                "company_id": caller_org,
                "change_request": "Please fix tests",
            },
        )
        assert resp.status_code == 404

    # --- relations (POST) ---

    def test_add_relation_own_company_returns_201(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/relations",
            json={
                "company_id": org,
                "target_id": str(uuid.uuid4()),
                "relation_type": "blocks",
            },
        )
        assert resp.status_code == 201

    def test_add_relation_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/relations",
            json={
                "company_id": caller_org,
                "target_id": str(uuid.uuid4()),
                "relation_type": "blocks",
            },
        )
        assert resp.status_code == 404

    # --- relations (DELETE) ---

    def test_remove_relation_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.delete(
            f"/work-items/{uuid.uuid4()}/relations/{uuid.uuid4()}",
            params={"company_id": caller_org},
        )
        assert resp.status_code == 404

    # --- attachments list ---

    def test_list_attachments_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.get(
            f"/work-items/{uuid.uuid4()}/attachments",
            params={"company_id": org},
        )
        assert resp.status_code == 200

    def test_list_attachments_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.get(
            f"/work-items/{uuid.uuid4()}/attachments",
            params={"company_id": caller_org},
        )
        assert resp.status_code == 404

    # --- attachments download (cross-tenant file read) ---

    def test_download_attachment_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.get(
            f"/work-items/{uuid.uuid4()}/attachments/{uuid.uuid4()}/download",
            params={"company_id": caller_org},
        )
        assert resp.status_code == 404

    def test_download_attachment_own_company_returns_200(self):
        org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=org, item_company_id=org)
        resp = client.get(
            f"/work-items/{uuid.uuid4()}/attachments/{uuid.uuid4()}/download",
            params={"company_id": org},
        )
        assert resp.status_code == 200

    # --- attachments text ---

    def test_attachment_text_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.get(
            f"/work-items/{uuid.uuid4()}/attachments/{uuid.uuid4()}/text",
            params={"company_id": caller_org},
        )
        assert resp.status_code == 404

    # --- attachments delete ---

    def test_delete_attachment_cross_tenant_returns_404(self):
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        client = _make_idor_app(caller_org_id=caller_org, item_company_id=other_org)
        resp = client.delete(
            f"/work-items/{uuid.uuid4()}/attachments/{uuid.uuid4()}",
            params={"company_id": caller_org},
        )
        assert resp.status_code == 404
