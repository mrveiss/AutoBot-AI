# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for slash command presets API (GH#4449, GH#8595)."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.chat_presets import router

USER = {"username": "testuser", "role": "user", "org_id": "org123"}
ADMIN = {"username": "adminuser", "role": "admin", "org_id": "org123"}
USER_HASH_KEY = "chat:presets:user:testuser"
ORG_HASH_KEY = "chat:presets:org:org123"


def _make_app(current_user=None) -> FastAPI:
    app = FastAPI()

    async def _override_user():
        return current_user or USER

    from auth_middleware import get_current_user

    app.dependency_overrides[get_current_user] = _override_user
    app.include_router(router)
    return app


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    with patch(
        "api.chat_presets.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=redis,
    ) as p:
        p.return_value = redis
        yield redis


@pytest.fixture
def client(mock_redis):
    return TestClient(_make_app())


@pytest.fixture
def admin_client(mock_redis):
    return TestClient(_make_app(current_user=ADMIN))


class TestListPresets:
    def test_empty(self, client, mock_redis):
        mock_redis.hgetall.return_value = {}
        resp = client.get("/chat/presets")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_personal_presets_only(self, client, mock_redis):
        p1 = {
            "id": "a",
            "name": "A",
            "description": "",
            "content": "x",
            "scope": "personal",
            "createdAt": "2025-01-01T00:00:00+00:00",
            "updatedAt": "2025-01-01T00:00:00+00:00",
        }

        async def mock_hgetall(key):
            if key == USER_HASH_KEY:
                return {"a": json.dumps(p1)}
            return {}

        mock_redis.hgetall.side_effect = mock_hgetall
        resp = client.get("/chat/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "a"

    def test_returns_personal_and_org_presets(self, client, mock_redis):
        p1 = {
            "id": "a",
            "name": "Personal",
            "description": "",
            "content": "x",
            "scope": "personal",
            "createdAt": "2025-01-01T00:00:00+00:00",
            "updatedAt": "2025-01-01T00:00:00+00:00",
        }
        p2 = {
            "id": "b",
            "name": "Org",
            "description": "",
            "content": "y",
            "scope": "org",
            "createdAt": "2025-01-02T00:00:00+00:00",
            "updatedAt": "2025-01-02T00:00:00+00:00",
        }

        async def mock_hgetall(key):
            if key == USER_HASH_KEY:
                return {"a": json.dumps(p1)}
            elif key == ORG_HASH_KEY:
                return {"b": json.dumps(p2)}
            return {}

        mock_redis.hgetall.side_effect = mock_hgetall
        resp = client.get("/chat/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert [d["id"] for d in data] == ["a", "b"]


class TestCreatePreset:
    def test_creates_personal_preset(self, client, mock_redis):
        mock_redis.hset.return_value = 1
        resp = client.post(
            "/chat/presets",
            json={"name": "greet", "description": "Greeting", "content": "Hello!", "scope": "personal"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "greet"
        assert data["content"] == "Hello!"
        assert data["scope"] == "personal"
        assert "id" in data
        assert "createdAt" in data
        assert "updatedAt" in data
        mock_redis.hset.assert_awaited_once()

    def test_creates_org_preset_as_admin(self, admin_client, mock_redis):
        mock_redis.hset.return_value = 1
        resp = admin_client.post(
            "/chat/presets",
            json={"name": "standup", "description": "Team standup", "content": "Daily standup", "scope": "org"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "standup"
        assert data["scope"] == "org"

    def test_rejects_org_preset_for_non_admin(self, client, mock_redis):
        resp = client.post(
            "/chat/presets",
            json={"name": "standup", "description": "Team standup", "content": "Daily standup", "scope": "org"},
        )
        assert resp.status_code == 403
        assert "admin" in resp.json()["detail"].lower()


class TestUpdatePreset:
    def test_updates_personal_preset(self, client, mock_redis):
        existing = {
            "id": "abc",
            "name": "old",
            "description": "d",
            "content": "c",
            "scope": "personal",
            "createdAt": "2025-01-01T00:00:00+00:00",
            "updatedAt": "2025-01-01T00:00:00+00:00",
        }

        async def mock_hget(key, preset_id):
            if key == USER_HASH_KEY and preset_id == "abc":
                return json.dumps(existing)
            return None

        mock_redis.hget.side_effect = mock_hget
        mock_redis.hset.return_value = 0
        resp = client.put("/chat/presets/abc", json={"name": "new"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "new"
        assert data["content"] == "c"

    def test_admin_updates_org_preset(self, admin_client, mock_redis):
        existing = {
            "id": "xyz",
            "name": "old org",
            "description": "d",
            "content": "c",
            "scope": "org",
            "createdAt": "2025-01-01T00:00:00+00:00",
            "updatedAt": "2025-01-01T00:00:00+00:00",
        }

        async def mock_hget(key, preset_id):
            if key == ORG_HASH_KEY and preset_id == "xyz":
                return json.dumps(existing)
            return None

        mock_redis.hget.side_effect = mock_hget
        mock_redis.hset.return_value = 0
        resp = admin_client.put("/chat/presets/xyz", json={"name": "new org"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "new org"

    def test_non_admin_cannot_update_org_preset(self, client, mock_redis):
        existing = {
            "id": "xyz",
            "name": "org preset",
            "description": "d",
            "content": "c",
            "scope": "org",
            "createdAt": "2025-01-01T00:00:00+00:00",
            "updatedAt": "2025-01-01T00:00:00+00:00",
        }

        async def mock_hget(key, preset_id):
            if key == ORG_HASH_KEY and preset_id == "xyz":
                return json.dumps(existing)
            return None

        mock_redis.hget.side_effect = mock_hget
        resp = client.put("/chat/presets/xyz", json={"name": "hacked"})
        assert resp.status_code == 403

    def test_404_if_missing(self, client, mock_redis):
        mock_redis.hget.return_value = None
        resp = client.put("/chat/presets/missing", json={"name": "x"})
        assert resp.status_code == 404


class TestDeletePreset:
    def test_deletes_personal_preset(self, client, mock_redis):
        mock_redis.hdel.return_value = 1
        resp = client.delete("/chat/presets/abc")
        assert resp.status_code == 204

    def test_admin_deletes_org_preset(self, admin_client, mock_redis):
        existing = {
            "id": "xyz",
            "name": "org preset",
            "scope": "org",
        }

        async def mock_hdel(key, preset_id):
            return 0  # Not found in personal presets

        async def mock_hget(key, preset_id):
            if key == ORG_HASH_KEY and preset_id == "xyz":
                return json.dumps(existing)
            return None

        mock_redis.hdel.side_effect = mock_hdel
        mock_redis.hget.side_effect = mock_hget
        resp = admin_client.delete("/chat/presets/xyz")
        assert resp.status_code == 204

    def test_non_admin_cannot_delete_org_preset(self, client, mock_redis):
        existing = {
            "id": "xyz",
            "name": "org preset",
            "scope": "org",
        }

        async def mock_hdel(key, preset_id):
            return 0  # Not found in personal presets

        async def mock_hget(key, preset_id):
            if key == ORG_HASH_KEY and preset_id == "xyz":
                return json.dumps(existing)
            return None

        mock_redis.hdel.side_effect = mock_hdel
        mock_redis.hget.side_effect = mock_hget
        resp = client.delete("/chat/presets/xyz")
        assert resp.status_code == 403

    def test_404_if_missing(self, client, mock_redis):
        mock_redis.hdel.return_value = 0
        mock_redis.hget.return_value = None
        resp = client.delete("/chat/presets/missing")
        assert resp.status_code == 404
