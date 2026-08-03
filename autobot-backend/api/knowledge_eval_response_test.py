# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for #13259: GET /test/fresh_stats and POST /test/rebuild_index
dropped their payloads.

Both declared response_model=DataResponse[XData] over a flat dict return; the
fix declares the concrete flat model directly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.knowledge_eval import router


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/knowledge")
    return TestClient(app)


class TestGetFreshKbStatsResponsePayload:
    def test_returns_the_real_stats_on_the_wire(self):
        client = _make_client()
        mock_kb = MagicMock()
        mock_kb.get_stats = AsyncMock(return_value={"document_count": 42})

        with (
            patch("knowledge_base.KnowledgeBase", return_value=mock_kb),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            response = client.get("/api/knowledge/test/fresh_stats")

        assert response.status_code == 200
        body = response.json()
        assert body["stats"]["document_count"] == 42
        assert body["source"] == "fresh_instance"
        assert body["success"] is True


class TestRebuildSearchIndexResponsePayload:
    def test_returns_the_real_rebuild_result_on_the_wire(self):
        client = _make_client()
        mock_kb = MagicMock()
        mock_kb.rebuild_search_index = AsyncMock(return_value={"status": "success", "documents_indexed": 17})

        with (
            patch("knowledge_base.KnowledgeBase", return_value=mock_kb),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            response = client.post("/api/knowledge/test/rebuild_index")

        assert response.status_code == 200
        body = response.json()
        assert body["result"]["documents_indexed"] == 17
        assert body["operation"] == "rebuild_search_index"
        assert body["success"] is True
