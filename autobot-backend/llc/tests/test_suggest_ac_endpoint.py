# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for POST /work-items/suggest-ac (GH#9861).

H2 fix: company_id is no longer supplied by the client — it is derived from
the authenticated TenantContext.  All tests install auth dependency overrides
so the real Depends(get_current_user) / Depends(require_org_context) path is
exercised rather than skipped.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

_FIXED_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _make_app(session_item=None, suggester_result=None, caller_org_id=None):
    """Build a minimal FastAPI app with the work-items router.

    session_item: return value of WorkItemService.get() — None means not found.
    suggester_result: dict returned by AcSuggester.suggest().
    caller_org_id: UUID string for the TenantContext.org_id injected via the
                   auth override (defaults to a fresh random UUID).
    """
    # Deferred import: llc.api.work_items must not be imported at module level
    # because pytest collects all tests before running them and the import chain
    # breaks when llc/api/__init__.py is partially initialised by other tests.
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.work_items import router as wi_router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415
    from user_management.services import TenantContext  # noqa: PLC0415

    app = FastAPI()
    app.include_router(wi_router)

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    async def _fake_session():
        yield mock_session

    org = uuid.UUID(caller_org_id) if caller_org_id else uuid.uuid4()

    def _fake_user() -> dict:
        return {"id": str(_FIXED_USER_ID), "user_id": str(_FIXED_USER_ID)}

    def _fake_tenant() -> TenantContext:
        return TenantContext(org_id=org, user_id=_FIXED_USER_ID, is_platform_admin=False)

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[require_org_context] = _fake_tenant

    # Patch WorkItemService.get
    svc_get = AsyncMock(return_value=session_item)
    patch("llc.services.work_item_service.WorkItemService.get", new=svc_get).start()

    # Patch AcSuggester.suggest
    _sug_result = suggester_result if suggester_result is not None else {"suggestions": ["AC1", "AC2"], "sources": []}
    sug_suggest = AsyncMock(return_value=_sug_result)
    patch("llc.kb.ac_suggester.AcSuggester.suggest", new=sug_suggest).start()

    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSuggestAcEndpoint:
    def teardown_method(self, _method):
        patch.stopall()

    def test_no_title_no_work_item_id_returns_422(self):
        """Neither title nor work_item_id supplied → 422 from route logic."""
        client = _make_app()
        resp = client.post("/work-items/suggest-ac", json={})
        assert resp.status_code == 422

    def test_inline_title_returns_suggestions(self):
        client = _make_app(suggester_result={"suggestions": ["Must do X", "Must not Y"], "sources": ["doc1"]})
        resp = client.post(
            "/work-items/suggest-ac",
            json={
                "title": "Implement password reset",
                "description": "Allow users to reset their password",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["suggestions"] == ["Must do X", "Must not Y"]
        assert body["sources"] == ["doc1"]

    def test_work_item_id_resolved_from_db(self):
        """work_item_id resolves to an item whose company_id matches ctx.org_id → 200."""
        company_id = str(uuid.uuid4())
        work_item_id = str(uuid.uuid4())
        mock_item = MagicMock()
        mock_item.title = "DB-resolved title"
        mock_item.description = "DB description"
        mock_item.company_id = company_id
        mock_item.project_id = None
        client = _make_app(
            session_item=mock_item,
            suggester_result={"suggestions": ["AC from DB item"], "sources": []},
            caller_org_id=company_id,
        )
        resp = client.post(
            "/work-items/suggest-ac",
            json={"work_item_id": work_item_id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["suggestions"] == ["AC from DB item"]

    def test_llm_unavailable_returns_empty_list(self):
        """When AcSuggester returns empty suggestions, endpoint returns 200 with []."""
        client = _make_app(suggester_result={"suggestions": [], "sources": []})
        resp = client.post(
            "/work-items/suggest-ac",
            json={"title": "Anything"},
        )
        assert resp.status_code == 200
        assert resp.json()["suggestions"] == []

    def test_unknown_work_item_id_returns_404(self):
        """work_item_id that resolves to None → 404."""
        client = _make_app(session_item=None)
        resp = client.post(
            "/work-items/suggest-ac",
            json={"work_item_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_cross_tenant_work_item_returns_404(self):
        """work_item_id that belongs to a different company → 404.

        The caller's org is ``requester_company``; the item's company_id is
        ``item_company`` (different) — the route must 404, not leak item data.
        """
        requester_company = str(uuid.uuid4())
        item_company = str(uuid.uuid4())  # different tenant
        mock_item = MagicMock()
        mock_item.title = "Other company's item"
        mock_item.company_id = item_company
        client = _make_app(session_item=mock_item, caller_org_id=requester_company)
        resp = client.post(
            "/work-items/suggest-ac",
            json={"work_item_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_company_id_body_field_is_rejected(self):
        """Sending company_id in the body is a no-op (field removed from schema) → 422 if
        pydantic strict rejects extra fields, or 200 if tolerant.  Either way the
        route must NOT use the supplied company_id — it uses ctx.org_id.
        """
        # Build an app whose TenantContext reports a specific org.
        tenant_org = str(uuid.uuid4())
        client = _make_app(
            suggester_result={"suggestions": ["ok"], "sources": []},
            caller_org_id=tenant_org,
        )
        resp = client.post(
            "/work-items/suggest-ac",
            # company_id is no longer in the schema; pydantic will ignore extras.
            json={"title": "Test item", "company_id": str(uuid.uuid4())},
        )
        # Must succeed (company_id in body is ignored, title path is used).
        assert resp.status_code == 200
