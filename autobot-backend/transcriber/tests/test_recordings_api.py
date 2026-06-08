# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_recordings_api.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import io

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.routes.projects import router as projects_router
from transcriber.routes.recordings import router as recordings_router


@pytest_asyncio.fixture
async def client(tmp_path):
    a = FastAPI()
    db = Database(str(tmp_path / "test.db"))
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    async def override_db():
        return db

    await db.connect()
    a.dependency_overrides[get_db] = override_db
    a.state.transcriber_upload_dir = str(upload_dir)
    a.include_router(projects_router, prefix="/api/transcriber")
    a.include_router(recordings_router, prefix="/api/transcriber")

    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_upload_recording(client, tmp_path):
    r = await client.post("/api/transcriber/projects", json={"name": "P", "description": ""})
    pid = r.json()["id"]
    audio_bytes = b"RIFF" + b"\x00" * 100
    r2 = await client.post(
        f"/api/transcriber/projects/{pid}/recordings",
        files={"file": ("test.wav", io.BytesIO(audio_bytes), "audio/wav")},
    )
    assert r2.status_code == 202
    data = r2.json()
    assert data["status"] == "pending"
    assert data["project_id"] == pid


@pytest.mark.asyncio
async def test_list_recordings(client, tmp_path):
    r = await client.post("/api/transcriber/projects", json={"name": "P", "description": ""})
    pid = r.json()["id"]
    await client.post(
        f"/api/transcriber/projects/{pid}/recordings",
        files={"file": ("a.wav", io.BytesIO(b"RIFF" + b"\x00" * 10), "audio/wav")},
    )
    r2 = await client.get(f"/api/transcriber/projects/{pid}/recordings")
    assert r2.status_code == 200
    assert len(r2.json()) == 1


@pytest.mark.asyncio
async def test_delete_recording(client, tmp_path):
    r = await client.post("/api/transcriber/projects", json={"name": "P", "description": ""})
    pid = r.json()["id"]
    r2 = await client.post(
        f"/api/transcriber/projects/{pid}/recordings",
        files={"file": ("b.wav", io.BytesIO(b"RIFF" + b"\x00" * 10), "audio/wav")},
    )
    rid = r2.json()["id"]
    r3 = await client.delete(f"/api/transcriber/recordings/{rid}")
    assert r3.status_code == 204
