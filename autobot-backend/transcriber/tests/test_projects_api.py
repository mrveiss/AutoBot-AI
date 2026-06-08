# autobot-backend/transcriber/tests/test_projects_api.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.routes.projects import router


@pytest_asyncio.fixture
async def client(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    await db.connect()

    app = FastAPI()

    async def override_db():
        return db

    app.dependency_overrides[get_db] = override_db
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
