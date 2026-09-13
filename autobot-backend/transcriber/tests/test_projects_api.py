# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_projects_api.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from transcriber.database import Database
from transcriber.deps import authenticate, get_db
from transcriber.routes.projects import router

TEST_CALLER = "test-user"


def _as_test_user(request: Request) -> None:
    """Stand in for authenticate: these tests exercise ownership, not login (#15758)."""
    request.state.user = SimpleNamespace(id=TEST_CALLER, is_admin=False)


@pytest_asyncio.fixture
async def client(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    await db.connect()

    app = FastAPI()

    async def override_db():
        return db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[authenticate] = _as_test_user
    app.include_router(router, prefix="/api/transcriber")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    await db.close()


@pytest.mark.asyncio
async def test_create_project(client):
    r = await client.post("/api/transcriber/projects", json={"name": "My Project", "description": "desc"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "My Project"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_projects(client):
    await client.post("/api/transcriber/projects", json={"name": "P1", "description": ""})
    r = await client.get("/api/transcriber/projects")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_delete_project(client):
    r = await client.post("/api/transcriber/projects", json={"name": "P", "description": ""})
    pid = r.json()["id"]
    r2 = await client.delete(f"/api/transcriber/projects/{pid}")
    assert r2.status_code == 204
    r3 = await client.get(f"/api/transcriber/projects/{pid}")
    assert r3.status_code == 404
