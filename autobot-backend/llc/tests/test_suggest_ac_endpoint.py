# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for POST /work-items/suggest-ac (GH#9861)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _make_app(session_item=None, suggester_result=None):
    """Build a minimal FastAPI app with the work-items router.

    session_item: return value of WorkItemService.get() — None means not found.
    suggester_result: dict returned by AcSuggester.suggest().
    """
    # Deferred import: llc.api.work_items must not be imported at module level
    # because pytest collects all tests before running them and the import chain
    # breaks when llc/api/__init__.py is partially initialised by other tests.
    from llc.api.work_items import router as wi_router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(wi_router)

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    async def _fake_session():
        yield mock_session

    app.dependency_overrides[get_session] = _fake_session

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

    def test_missing_company_id_returns_422(self):
        client = _make_app()
        resp = client.post("/work-items/suggest-ac", json={"title": "Build login page"})
        assert resp.status_code == 422

    def test_no_title_no_work_item_id_returns_422(self):
        client = _make_app()
        resp = client.post(
            "/work-items/suggest-ac",
            json={"company_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 422

    def test_inline_title_returns_suggestions(self):
        client = _make_app(suggester_result={"suggestions": ["Must do X", "Must not Y"], "sources": ["doc1"]})
        resp = client.post(
            "/work-items/suggest-ac",
            json={
                "company_id": str(uuid.uuid4()),
                "title": "Implement password reset",
                "description": "Allow users to reset their password",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["suggestions"] == ["Must do X", "Must not Y"]
        assert body["sources"] == ["doc1"]

    def test_work_item_id_resolved_from_db(self):
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
        )
        resp = client.post(
            "/work-items/suggest-ac",
            json={"company_id": company_id, "work_item_id": work_item_id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["suggestions"] == ["AC from DB item"]

    def test_llm_unavailable_returns_empty_list(self):
        """When AcSuggester returns empty suggestions, endpoint returns 200 with []."""
        client = _make_app(suggester_result={"suggestions": [], "sources": []})
        resp = client.post(
            "/work-items/suggest-ac",
            json={"company_id": str(uuid.uuid4()), "title": "Anything"},
        )
        assert resp.status_code == 200
        assert resp.json()["suggestions"] == []

    def test_unknown_work_item_id_returns_404(self):
        """work_item_id that resolves to None → 404."""
        client = _make_app(session_item=None)
        resp = client.post(
            "/work-items/suggest-ac",
            json={
                "company_id": str(uuid.uuid4()),
                "work_item_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 404

    def test_cross_tenant_work_item_returns_404(self):
        """work_item_id that belongs to a different company → 404."""
        requester_company = str(uuid.uuid4())
        item_company = str(uuid.uuid4())  # different
        mock_item = MagicMock()
        mock_item.title = "Other company's item"
        mock_item.company_id = item_company
        client = _make_app(session_item=mock_item)
        resp = client.post(
            "/work-items/suggest-ac",
            json={
                "company_id": requester_company,
                "work_item_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 404
