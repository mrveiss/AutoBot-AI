# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for chat conversation folder endpoints (GH#8987).

Covers the two acceptance criteria added in this change:
- Folders carry an ``archived`` flag (default False) in create + serialize.
- PUT /chat/folders/{id} can set/clear ``archived`` and it persists in Redis.
"""

import json
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.chat_folders import _serialize_folder, router
from auth_middleware import get_current_user

_USER = {"user_id": "alice", "username": "alice", "role": "user"}


class _FakeRedis:
    """Minimal async Redis stand-in backed by a dict (string get/set only)."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value: str) -> None:
        self._store[key] = value


def _make_client(redis: _FakeRedis) -> TestClient:
    app = FastAPI()
    app.include_router(router)

    async def _override_user():
        return _USER

    app.dependency_overrides[get_current_user] = _override_user

    async def _fake_get_redis(*args, **kwargs):
        return redis

    # The route imports get_redis_client lazily inside the function body.
    patcher = patch("autobot_shared.redis_client.get_redis_client", _fake_get_redis)
    patcher.start()
    client = TestClient(app)
    client._redis_patcher = patcher  # type: ignore[attr-defined]
    return client


def test_serialize_folder_defaults_archived_false():
    out = _serialize_folder({"id": "f1", "name": "Work"})
    assert out["archived"] is False
    assert out["pinned"] is False


def test_serialize_folder_preserves_archived_true():
    out = _serialize_folder({"id": "f1", "name": "Work", "archived": True})
    assert out["archived"] is True


def test_create_folder_is_unarchived_by_default():
    redis = _FakeRedis()
    client = _make_client(redis)
    try:
        resp = client.post("/chat/folders", json={"name": "Work"})
        assert resp.status_code == 201
        assert resp.json()["archived"] is False
    finally:
        client._redis_patcher.stop()  # type: ignore[attr-defined]


def test_update_folder_archives_and_persists():
    redis = _FakeRedis()
    client = _make_client(redis)
    try:
        folder_id = client.post("/chat/folders", json={"name": "Old"}).json()["id"]

        resp = client.put(f"/chat/folders/{folder_id}", json={"archived": True})
        assert resp.status_code == 200
        assert resp.json()["archived"] is True

        stored = json.loads(redis._store["chat:folders:alice"])
        assert stored[0]["archived"] is True

        # Unarchive round-trips back to False.
        resp = client.put(f"/chat/folders/{folder_id}", json={"archived": False})
        assert resp.json()["archived"] is False
    finally:
        client._redis_patcher.stop()  # type: ignore[attr-defined]
