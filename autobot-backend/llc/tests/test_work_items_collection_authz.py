# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Authn/tenant-authz tests for the work-items collection routes (#14168).

``POST /work-items`` and ``GET /work-items`` previously carried only
``Depends(get_session)`` — no ``get_current_user``, no ``require_org_context``
— letting an unauthenticated caller enumerate or create work items in any
company by supplying its ``company_id``. This mirrors the pattern established
in ``test_company_crud_authz_12233.py`` (GH#12233, the earlier recurrence of
this same defect class): override ``get_current_user``/``require_org_context``
to simulate unauthenticated/cross-tenant callers, and assert both the HTTP
response *and* that the service layer was never invoked (no row crossed the
tenant boundary).

Also covers ``POST /work-items/{id}/coworker`` (#14168): previously reachable
with no ``require_org_context``/IDOR guard, and shadowed by a second,
fully-unauthenticated duplicate route hard-coding ``caller_role="owner"``.
Both gaps are closed by consolidating into one tenant-scoped handler.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.user_management.dependencies import get_current_user, require_org_context
from user_management.services import TenantContext

_USER_ID = uuid.uuid4()


def _mock_item(company_id: str) -> MagicMock:
    item = MagicMock()
    item.id = uuid.uuid4()
    item.company_id = company_id
    item.identifier = "WI-001"
    item.type = "task"
    item.title = "Mock item"
    item.description = None
    item.acceptance_criteria = []
    item.acceptance_criteria_done = []
    item.status = "backlog"
    item.priority = "medium"
    item.story_points = None
    item.labels = []
    item.linked_pr_urls = []
    item.requires_approval_before = []
    item.parent_id = None
    item.project_id = None
    item.sprint_id = None
    item.goal_id = None
    item.assignee_agent_id = None
    item.assignee_user_id = None
    item.assignee_type = None
    item.checkout_run_id = None
    item.checkout_locked_at = None
    item.checkout_intent = None
    item.version = 1
    item.created_by_agent_id = None
    item.created_by_user_id = None
    item.reviewer_user_id = None
    item.reviewer_agent_id = None
    item.scheduled_start = None
    item.scheduled_end = None
    item.started_at = None
    item.completed_at = None
    item.cancelled_at = None
    item.review_brief = None
    item.created_at = None
    item.updated_at = None
    item.co_working_enabled = False
    item.co_worker_type = None
    item.co_worker_agent_id = None
    item.co_worker_user_id = None
    item.outgoing_relations = []
    item.incoming_relations = []
    return item


def _make_app(*, org_id: str, unauth: bool = False) -> FastAPI:
    from llc.api.work_items import router as wi_router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(wi_router)

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_session] = _fake_session

    def _cur() -> dict:
        if unauth:
            raise HTTPException(status_code=401, detail="Authentication required")
        return {"id": str(_USER_ID), "user_id": str(_USER_ID)}

    def _ctx() -> TenantContext:
        return TenantContext(org_id=uuid.UUID(org_id), user_id=_USER_ID, is_platform_admin=False)

    app.dependency_overrides[get_current_user] = _cur
    app.dependency_overrides[require_org_context] = _ctx

    return app


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


# ---------------------------------------------------------------------------
# POST /work-items — create_work_item
# ---------------------------------------------------------------------------


class TestCreateWorkItemAuthz:
    def test_unauthenticated_is_rejected(self):
        create_mock = patch(
            "llc.services.work_item_service.WorkItemService.create",
            new=AsyncMock(),
        ).start()
        app = _make_app(org_id=str(uuid.uuid4()), unauth=True)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/work-items",
            json={"company_id": str(uuid.uuid4()), "type": "task", "title": "Hijack"},
        )
        assert resp.status_code == 401
        create_mock.assert_not_called()

    def test_cross_tenant_company_id_is_rejected(self):
        """An authenticated caller in org A cannot create a work item under org B."""
        create_mock = patch(
            "llc.services.work_item_service.WorkItemService.create",
            new=AsyncMock(),
        ).start()
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        app = _make_app(org_id=caller_org)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/work-items",
            json={"company_id": other_org, "type": "task", "title": "Hijack"},
        )
        assert resp.status_code == 404
        create_mock.assert_not_called()

    def test_own_company_succeeds(self):
        org = str(uuid.uuid4())
        item = _mock_item(org)
        create_mock = patch(
            "llc.services.work_item_service.WorkItemService.create",
            new=AsyncMock(return_value=item),
        ).start()
        patch("llc.api.work_items._relations_to_list", new=AsyncMock(return_value=[])).start()
        patch("llc.kb.collections.KbCollectionManager.ensure_collection", new=AsyncMock()).start()
        app = _make_app(org_id=org)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/work-items",
            json={"company_id": org, "type": "task", "title": "Legit item"},
        )
        assert resp.status_code == 201, resp.text
        create_mock.assert_awaited_once()
        assert create_mock.await_args.kwargs["company_id"] == org


# ---------------------------------------------------------------------------
# GET /work-items — list_work_items
# ---------------------------------------------------------------------------


class TestListWorkItemsAuthz:
    def test_unauthenticated_is_rejected(self):
        list_mock = patch(
            "llc.services.work_item_service.WorkItemService.list_by_project",
            new=AsyncMock(return_value=[]),
        ).start()
        app = _make_app(org_id=str(uuid.uuid4()), unauth=True)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/work-items", params={"company_id": str(uuid.uuid4())})
        assert resp.status_code == 401
        list_mock.assert_not_called()

    def test_cross_tenant_enumeration_is_rejected(self):
        """Company A caller cannot list company B's work items by supplying its id."""
        list_mock = patch(
            "llc.services.work_item_service.WorkItemService.list_by_project",
            new=AsyncMock(return_value=[_mock_item("should-not-be-returned")]),
        ).start()
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        app = _make_app(org_id=caller_org)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/work-items", params={"company_id": other_org})
        assert resp.status_code == 404
        list_mock.assert_not_called()
        # No cross-tenant row is ever serialized into the response body.
        assert "should-not-be-returned" not in resp.text

    def test_own_company_succeeds(self):
        org = str(uuid.uuid4())
        item = _mock_item(org)
        list_mock = patch(
            "llc.services.work_item_service.WorkItemService.list_by_project",
            new=AsyncMock(return_value=[item]),
        ).start()
        patch("llc.api.work_items._relations_to_list", new=AsyncMock(return_value=[])).start()
        app = _make_app(org_id=org)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/work-items", params={"company_id": org})
        assert resp.status_code == 200
        list_mock.assert_awaited_once()
        assert list_mock.await_args.kwargs["company_id"] == org
        assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# POST /work-items/{id}/coworker — set_coworker (consolidated, #14168)
# ---------------------------------------------------------------------------


class TestCoworkerAuthz:
    def test_unauthenticated_is_rejected(self):
        enable_mock = patch(
            "llc.services.work_item_service.WorkItemService.enable_coworking",
            new=AsyncMock(),
        ).start()
        app = _make_app(org_id=str(uuid.uuid4()), unauth=True)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/coworker",
            json={"co_worker_type": "agent", "co_worker_agent_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 401
        enable_mock.assert_not_called()

    def test_cross_tenant_work_item_is_rejected(self):
        """Caller authenticated into org A cannot set a co-worker on org B's item."""
        caller_org = str(uuid.uuid4())
        other_org = str(uuid.uuid4())
        enable_mock = patch(
            "llc.services.work_item_service.WorkItemService.enable_coworking",
            new=AsyncMock(),
        ).start()
        patch(
            "llc.services.work_item_service.WorkItemService.get",
            new=AsyncMock(return_value=_mock_item(other_org)),
        ).start()
        app = _make_app(org_id=caller_org)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/coworker",
            json={"co_worker_type": "agent", "co_worker_agent_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
        enable_mock.assert_not_called()

    def test_own_company_set_resolves_role_from_ctx_org_not_body(self):
        """company_id used for role resolution must be ctx.org_id, never client input."""
        org = str(uuid.uuid4())
        item = _mock_item(org)
        patch(
            "llc.services.work_item_service.WorkItemService.get",
            new=AsyncMock(return_value=item),
        ).start()
        enable_mock = patch(
            "llc.services.work_item_service.WorkItemService.enable_coworking",
            new=AsyncMock(return_value=item),
        ).start()
        resolve_mock = patch(
            "llc.api.work_items.resolve_actor_role",
            new=AsyncMock(return_value="owner"),
        ).start()
        patch("llc.api.work_items._relations_to_list", new=AsyncMock(return_value=[])).start()
        app = _make_app(org_id=org)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            f"/work-items/{uuid.uuid4()}/coworker",
            json={"co_worker_type": "agent", "co_worker_agent_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 200, resp.text
        resolve_mock.assert_awaited_once()
        assert resolve_mock.await_args.args[-1] == org
        enable_mock.assert_awaited_once()
        assert enable_mock.await_args.kwargs["company_id"] == org

    def test_omitting_co_worker_type_clears_via_disable_coworking(self):
        """The consolidated route preserves the "clear" behaviour of the old
        duplicate (now-removed) set_or_clear_coworker route."""
        org = str(uuid.uuid4())
        item = _mock_item(org)
        patch(
            "llc.services.work_item_service.WorkItemService.get",
            new=AsyncMock(return_value=item),
        ).start()
        disable_mock = patch(
            "llc.services.work_item_service.WorkItemService.disable_coworking",
            new=AsyncMock(return_value=item),
        ).start()
        patch(
            "llc.api.work_items.resolve_actor_role",
            new=AsyncMock(return_value="owner"),
        ).start()
        patch("llc.api.work_items._relations_to_list", new=AsyncMock(return_value=[])).start()
        app = _make_app(org_id=org)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(f"/work-items/{uuid.uuid4()}/coworker", json={})
        assert resp.status_code == 200, resp.text
        disable_mock.assert_awaited_once()
        assert disable_mock.await_args.kwargs["company_id"] == org
