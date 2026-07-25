# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for graceful no_data on GET /patterns/cached-summary and
/patterns/cached-patterns when the pattern store is empty or unreadable
(Issue #12365).

NOTE: the top-level autobot-backend/conftest.py stubs
``code_intelligence.pattern_analysis`` as a bare MagicMock package (avoiding
its heavy real __init__ chain for unrelated test suites). ``unittest.mock.
patch("code_intelligence.pattern_analysis.storage.X")`` resolves via a
getattr chain that silently patches a throwaway attribute on that MagicMock
instead of the real module the endpoint imports at call time, making the
patch inert. We instead install a stub module directly at
``sys.modules["code_intelligence.pattern_analysis.storage"]`` so the
endpoint's local ``from code_intelligence.pattern_analysis.storage import
get_pattern_collection_async`` resolves to our controllable stub.
"""

import sys
from types import ModuleType
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.codebase_analytics.endpoints.pattern_analysis import router

_STORAGE_MODULE_NAME = "code_intelligence.pattern_analysis.storage"


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client():
    return TestClient(_make_app())


@pytest.fixture
def stub_storage():
    """Install a stub storage module the endpoint's local import resolves to."""
    original = sys.modules.get(_STORAGE_MODULE_NAME)
    mod = ModuleType(_STORAGE_MODULE_NAME)
    sys.modules[_STORAGE_MODULE_NAME] = mod
    yield mod
    if original is not None:
        sys.modules[_STORAGE_MODULE_NAME] = original
    else:
        sys.modules.pop(_STORAGE_MODULE_NAME, None)


class TestGetCachedPatternSummary:
    def test_no_collection_returns_no_data(self, client, stub_storage):
        """ChromaDB collection unavailable degrades to 200 no_data."""
        stub_storage.get_pattern_collection_async = AsyncMock(return_value=None)

        resp = client.get("/patterns/cached-summary")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "no_data"
        assert body["has_cached_data"] is False

    def test_empty_store_returns_no_data(self, client, stub_storage):
        """Zero indexed patterns degrades to 200 no_data, not an error."""
        mock_collection = AsyncMock()
        mock_collection.get.return_value = {"metadatas": []}
        stub_storage.get_pattern_collection_async = AsyncMock(return_value=mock_collection)

        resp = client.get("/patterns/cached-summary")

        assert resp.status_code == 200
        assert resp.json()["status"] == "no_data"

    def test_store_read_exception_returns_no_data_not_500(self, client, stub_storage):
        """A store-read failure degrades to 200 no_data instead of 500."""
        stub_storage.get_pattern_collection_async = AsyncMock(side_effect=RuntimeError("chromadb unavailable"))

        resp = client.get("/patterns/cached-summary")

        assert resp.status_code == 200
        assert resp.json()["status"] == "no_data"

    def test_populated_store_returns_success(self, client, stub_storage):
        """Cached results still return normally when present."""
        mock_collection = AsyncMock()
        mock_collection.get.return_value = {
            "metadatas": [
                {"pattern_type": "duplicate", "severity": "medium", "file_path": "a.py"},
            ]
        }
        stub_storage.get_pattern_collection_async = AsyncMock(return_value=mock_collection)

        resp = client.get("/patterns/cached-summary")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["has_cached_data"] is True
        assert body["total_patterns"] == 1


class TestGetCachedPatterns:
    def test_no_collection_returns_no_data(self, client, stub_storage):
        stub_storage.get_pattern_collection_async = AsyncMock(return_value=None)

        resp = client.get("/patterns/cached-patterns")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "no_data"
        assert body["patterns"] == []

    def test_store_read_exception_returns_no_data_not_500(self, client, stub_storage):
        """A store-read failure degrades to 200 no_data instead of 500."""
        stub_storage.get_pattern_collection_async = AsyncMock(side_effect=RuntimeError("chromadb unavailable"))

        resp = client.get("/patterns/cached-patterns")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "no_data"
