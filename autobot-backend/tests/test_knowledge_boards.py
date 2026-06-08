# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for the knowledge boards API (Issue #3242).

Covers:
- GET  /boards — list boards, always includes __global__
- POST /boards — create a board; duplicate guard; reserved ID guard
- DELETE /boards/{board_id} — delete a board; 404 for unknown; guard on __global__

The tests use an in-process fake Redis hash so no real Redis is required.
The knowledge-base singleton is monkey-patched on each request via
``app.state`` / dependency overrides so nothing from the real KB init runs.
"""

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.knowledge_boards as boards_mod
from api.knowledge_boards import (
    _BOARDS_KEY,
    GLOBAL_BOARD_ID,
)
from api.knowledge_boards import router as boards_router
from tests.helpers.fake_kb import MinimalFakeKB
from tests.helpers.fake_redis import AsyncHashFakeRedis

# ---------------------------------------------------------------------------
# Fake KB stub and app factory
# ---------------------------------------------------------------------------


def _make_app(fake_redis: AsyncHashFakeRedis) -> FastAPI:
    """Build a minimal FastAPI app with the boards router wired up."""

    async def _fake_get_kb(app, force_refresh=False):  # noqa: ANN001
        return MinimalFakeKB(fake_redis)

    app = FastAPI()
    # Patch module-level factory so _get_redis() resolves correctly
    boards_mod.get_or_create_knowledge_base = _fake_get_kb

    # Bypass admin auth for all tests
    app.dependency_overrides[boards_mod.check_admin_permission] = lambda: True

    app.include_router(boards_router, prefix="/api/knowledge_base")
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_board(fake_redis: AsyncHashFakeRedis, board_id: str, name: str) -> dict:
    """Synchronously seed a board entry into the fake Redis store."""
    entry = {"board_id": board_id, "name": name, "description": "", "created_at": "2026-01-01T00:00:00+00:00"}
    # Direct store manipulation (sync path for test setup)
    fake_redis._store.setdefault(_BOARDS_KEY, {})[board_id] = json.dumps(entry).encode("utf-8")
    return entry


# ===========================================================================
# Test class
# ===========================================================================


class TestKnowledgeBoardsList:
    """GET /boards always returns at least the global sentinel."""

    def test_empty_store_returns_global_board(self):
        fake_redis = AsyncHashFakeRedis()
        client = TestClient(_make_app(fake_redis))
        resp = client.get("/api/knowledge_base/boards")
        assert resp.status_code == 200
        data = resp.json()
        assert "boards" in data
        ids = [b["board_id"] for b in data["boards"]]
        assert GLOBAL_BOARD_ID in ids

    def test_seeded_boards_appear_in_list(self):
        fake_redis = AsyncHashFakeRedis()
        _seed_board(fake_redis, "project-alpha", "Project Alpha")
        client = TestClient(_make_app(fake_redis))
        resp = client.get("/api/knowledge_base/boards")
        assert resp.status_code == 200
        data = resp.json()
        ids = [b["board_id"] for b in data["boards"]]
        assert "project-alpha" in ids
        assert GLOBAL_BOARD_ID in ids
        assert data["total"] == 2

    def test_total_count_includes_global(self):
        fake_redis = AsyncHashFakeRedis()
        _seed_board(fake_redis, "board-a", "Board A")
        _seed_board(fake_redis, "board-b", "Board B")
        client = TestClient(_make_app(fake_redis))
        resp = client.get("/api/knowledge_base/boards")
        assert resp.json()["total"] == 3  # global + board-a + board-b


class TestKnowledgeBoardsCreate:
    """POST /boards — creation, validation, and duplicate handling."""

    def test_create_board_returns_201(self):
        fake_redis = AsyncHashFakeRedis()
        client = TestClient(_make_app(fake_redis))
        resp = client.post(
            "/api/knowledge_base/boards",
            json={"board_id": "my-project", "name": "My Project"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["board_id"] == "my-project"
        assert data["created"] is True

    def test_create_board_without_id_autogenerates(self):
        fake_redis = AsyncHashFakeRedis()
        client = TestClient(_make_app(fake_redis))
        resp = client.post(
            "/api/knowledge_base/boards",
            json={"name": "Auto ID Board"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "board_id" in data
        assert data["board_id"]  # non-empty

    def test_create_board_persists_in_redis(self):
        fake_redis = AsyncHashFakeRedis()
        client = TestClient(_make_app(fake_redis))
        client.post(
            "/api/knowledge_base/boards",
            json={"board_id": "persisted-board", "name": "Persisted"},
        )
        stored = fake_redis._store.get(_BOARDS_KEY, {}).get("persisted-board")
        assert stored is not None
        entry = json.loads(stored)
        assert entry["name"] == "Persisted"

    def test_duplicate_board_id_returns_409(self):
        fake_redis = AsyncHashFakeRedis()
        _seed_board(fake_redis, "existing-board", "Existing Board")
        client = TestClient(_make_app(fake_redis))
        resp = client.post(
            "/api/knowledge_base/boards",
            json={"board_id": "existing-board", "name": "Duplicate"},
        )
        assert resp.status_code == 409

    def test_reserved_global_board_id_returns_422(self):
        """__global__ is reserved; the validator should reject it."""
        fake_redis = AsyncHashFakeRedis()
        client = TestClient(_make_app(fake_redis))
        resp = client.post(
            "/api/knowledge_base/boards",
            json={"board_id": GLOBAL_BOARD_ID, "name": "Should Fail"},
        )
        # Pydantic validator raises ValueError → FastAPI returns 422
        assert resp.status_code == 422

    def test_invalid_board_id_chars_returns_422(self):
        """Board IDs must match [a-z0-9_-]."""
        fake_redis = AsyncHashFakeRedis()
        client = TestClient(_make_app(fake_redis))
        resp = client.post(
            "/api/knowledge_base/boards",
            json={"board_id": "UPPERCASE_NOT_ALLOWED", "name": "Bad ID"},
        )
        assert resp.status_code == 422

    def test_board_id_with_spaces_returns_422(self):
        fake_redis = AsyncHashFakeRedis()
        client = TestClient(_make_app(fake_redis))
        resp = client.post(
            "/api/knowledge_base/boards",
            json={"board_id": "spaces not allowed", "name": "Bad"},
        )
        assert resp.status_code == 422


class TestKnowledgeBoardsDelete:
    """DELETE /boards/{board_id} — removal and guard cases."""

    def test_delete_existing_board_returns_200(self):
        fake_redis = AsyncHashFakeRedis()
        _seed_board(fake_redis, "to-delete", "To Delete")
        client = TestClient(_make_app(fake_redis))
        resp = client.delete("/api/knowledge_base/boards/to-delete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["board_id"] == "to-delete"

    def test_delete_removes_board_from_redis(self):
        fake_redis = AsyncHashFakeRedis()
        _seed_board(fake_redis, "gone-board", "Gone Board")
        client = TestClient(_make_app(fake_redis))
        client.delete("/api/knowledge_base/boards/gone-board")
        remaining = fake_redis._store.get(_BOARDS_KEY, {}).get("gone-board")
        assert remaining is None

    def test_delete_unknown_board_returns_404(self):
        fake_redis = AsyncHashFakeRedis()
        client = TestClient(_make_app(fake_redis))
        resp = client.delete("/api/knowledge_base/boards/does-not-exist")
        assert resp.status_code == 404

    def test_delete_global_board_returns_400(self):
        """The __global__ sentinel must never be deletable."""
        fake_redis = AsyncHashFakeRedis()
        client = TestClient(_make_app(fake_redis))
        resp = client.delete(f"/api/knowledge_base/boards/{GLOBAL_BOARD_ID}")
        assert resp.status_code == 400
