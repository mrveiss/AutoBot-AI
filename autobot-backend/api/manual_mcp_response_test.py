# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for #13259: all 3 manual_mcp endpoints dropped their
payload.

Each declared response_model=DataResponse[XData] over a flat dict return; the
fix declares the concrete flat model directly.
"""

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.manual_mcp import router
from auth_middleware import get_current_user


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/manual-mcp")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "test-user", "role": "admin"}
    return TestClient(app)


class TestLookupManPageResponsePayload:
    def test_returns_the_real_man_page_result_on_the_wire(self):
        client = _make_client()
        fake_page = {"command": "ls", "section": "1", "title": "list directory contents"}

        with patch("api.manual_mcp._lookup_man_page", new=AsyncMock(return_value=fake_page)):
            response = client.post(
                "/api/manual-mcp/mcp/lookup_man_page",
                json={"command": "ls", "section": "1"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["command"] == "ls"
        assert body["result"]["title"] == "list directory contents"
        assert body["success"] is True


class TestSearchManPagesResponsePayload:
    def test_returns_the_real_search_results_on_the_wire(self):
        client = _make_client()
        fake_results = [{"command": "grep", "section": "1", "summary": "search text"}]

        with patch("api.manual_mcp._query_doc_index", new=AsyncMock(return_value=fake_results)):
            response = client.post(
                "/api/manual-mcp/mcp/search_man_pages",
                json={"query": "grep"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["results"][0]["command"] == "grep"
        assert body["query"] == "grep"


class TestGetDocIndexResponsePayload:
    def test_returns_the_real_doc_index_results_on_the_wire(self):
        client = _make_client()
        fake_results = [{"command": "awk", "section": "1", "summary": "pattern scanning"}]

        with patch("api.manual_mcp._query_doc_index", new=AsyncMock(return_value=fake_results)):
            response = client.post(
                "/api/manual-mcp/mcp/get_doc_index",
                json={"query": "awk"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["results"][0]["summary"] == "pattern scanning"
