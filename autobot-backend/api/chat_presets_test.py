# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for slash command presets API (GH#8595)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.chat_presets import router

USER = {"username": "testuser", "role": "user"}
HASH_KEY = "chat:presets:testuser"


def _make_app() -> FastAPI:
    app = FastAPI()

    async def _override_user():
        return USER

    from auth_middleware import get_current_user

    app.dependency_overrides[get_current_user] = _override_user
    app.include_router(router)
    return app


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    with patch(
        "api.chat_presets.get_async_redis_client", new_callable=AsyncMock, return_value=redis
    ) as p:
        p.return_value = redis
        yield redis


@pytest.fixture
def client(mock_redis):
    return TestClient(_make_app())


class TestListPresets:
    def test_empty(self, client, mock_redis):
        mock_redis.hgetall.return_value = {}
        resp = client.get("/chat/presets")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_sorted_by_created_at(self, client, mock_redis):
        p1 = {"id": "a", "name": "A", "description": "", "content": "x", "createdAt": "2025-01-01T00:00:00+00:00", "updatedAt": "2025-01-01T00:00:00+00:00"}
        p2 = {"id": "b", "name": "B", "description": "", "content": "y", "createdAt": "2025-01-02T00:00:00+00:00", "updatedAt": "2025-01-02T00:00:00+00:00"}
        mock_redis.hgetall.return_value = {"b": json.dumps(p2), "a": json.dumps(p1)}
        resp = client.get("/chat/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert [d["id"] for d in data] == ["a", "b"]


class TestCreatePreset:
    def test_creates_with_id(self, client, mock_redis):
        mock_redis.hset.return_value = 1
        resp = client.post("/chat/presets", json={"name": "greet", "description": "Greeting", "content": "Hello!"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "greet"
        assert data["content"] == "Hello!"
        assert "id" in data
        assert "createdAt" in data
        assert "updatedAt" in data
        mock_redis.hset.assert_awaited_once()


class TestUpdatePreset:
    def test_updates_existing(self, client, mock_redis):
        existing = {"id": "abc", "name": "old", "description": "d", "content": "c", "createdAt": "2025-01-01T00:00:00+00:00", "updatedAt": "2025-01-01T00:00:00+00:00"}
        mock_redis.hget.return_value = json.dumps(existing)
        mock_redis.hset.return_value = 0
        resp = client.put("/chat/presets/abc", json={"name": "new"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "new"
        assert data["content"] == "c"

    def test_404_if_missing(self, client, mock_redis):
        mock_redis.hget.return_value = None
        resp = client.put("/chat/presets/missing", json={"name": "x"})
        assert resp.status_code == 404


class TestDeletePreset:
    def test_deletes(self, client, mock_redis):
        mock_redis.hdel.return_value = 1
        resp = client.delete("/chat/presets/abc")
        assert resp.status_code == 204

    def test_404_if_missing(self, client, mock_redis):
        mock_redis.hdel.return_value = 0
        resp = client.delete("/chat/presets/missing")
        assert resp.status_code == 404
