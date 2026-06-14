# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_multiuser_authz.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Multi-user authorization regression tests for transcriber rows (#10023).

Pins the #9968 IDOR fix: a second authenticated user must NOT be able to
read, modify, or delete the first user's projects/recordings. All access
goes through transcriber.deps.can_access (#9863 single ownership policy);
if that policy is weakened or a route stops calling it, these tests go red.
"""

import io
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from transcriber.database import Database
from transcriber.deps import DEFAULT_USER, can_access, get_db
from transcriber.routes.projects import router as projects_router
from transcriber.routes.recordings import router as recordings_router

USER_HEADER = "x-test-user"


@pytest_asyncio.fixture
async def client(tmp_path):
    """App with both routers and header-driven request.state.user identity."""
    app = FastAPI()
    db = Database(str(tmp_path / "test.db"))
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    async def override_db():
        return db

    @app.middleware("http")
    async def set_user(request: Request, call_next):
        uid = request.headers.get(USER_HEADER)
        if uid:
            request.state.user = SimpleNamespace(id=uid)
        return await call_next(request)

    await db.connect()
    app.dependency_overrides[get_db] = override_db
    app.state.transcriber_upload_dir = str(upload_dir)
    app.include_router(projects_router, prefix="/api/transcriber")
    app.include_router(recordings_router, prefix="/api/transcriber")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _create_project(client, user: str) -> int:
    r = await client.post(
        "/api/transcriber/projects",
        json={"name": f"{user}-project", "description": ""},
        headers={USER_HEADER: user},
    )
    assert r.status_code == 201
    return r.json()["id"]


async def _upload_recording(client, user: str, pid: int) -> int:
    r = await client.post(
        f"/api/transcriber/projects/{pid}/recordings",
        files={"file": ("a.wav", io.BytesIO(b"RIFF" + b"\x00" * 32), "audio/wav")},
        headers={USER_HEADER: user},
    )
    assert r.status_code == 202
    return r.json()["id"]


def test_can_access_policy_unit():
    """can_access: owner yes, other user no, legacy DEFAULT_USER rows shared."""
    assert can_access({"user_id": "alice"}, "alice") is True
    assert can_access({"user_id": "alice"}, "bob") is False
    assert can_access({"user_id": DEFAULT_USER}, "bob") is True
    # Rows from before auth wiring (no user_id stamp) stay readable.
    assert can_access({}, "bob") is True


@pytest.mark.asyncio
async def test_second_user_cannot_read_first_users_project(client):
    pid = await _create_project(client, "alice")
    r = await client.get(f"/api/transcriber/projects/{pid}", headers={USER_HEADER: "bob"})
    assert r.status_code == 404, "IDOR (#9968): bob read alice's project"
    # Owner still sees it
    r = await client.get(f"/api/transcriber/projects/{pid}", headers={USER_HEADER: "alice"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_second_user_cannot_modify_or_delete_project(client):
    pid = await _create_project(client, "alice")
    r = await client.patch(
        f"/api/transcriber/projects/{pid}",
        json={"name": "hijacked"},
        headers={USER_HEADER: "bob"},
    )
    assert r.status_code == 404, "IDOR (#9968): bob modified alice's project"
    r = await client.delete(f"/api/transcriber/projects/{pid}", headers={USER_HEADER: "bob"})
    assert r.status_code == 404, "IDOR (#9968): bob deleted alice's project"
    # Row untouched
    r = await client.get(f"/api/transcriber/projects/{pid}", headers={USER_HEADER: "alice"})
    assert r.status_code == 200
    assert r.json()["name"] == "alice-project"


@pytest.mark.asyncio
async def test_project_listing_is_scoped_per_user(client):
    pid = await _create_project(client, "alice")
    r = await client.get("/api/transcriber/projects", headers={USER_HEADER: "bob"})
    assert r.status_code == 200
    assert pid not in [p["id"] for p in r.json()], "bob's listing leaked alice's project"


@pytest.mark.asyncio
async def test_second_user_cannot_access_recordings(client):
    pid = await _create_project(client, "alice")
    rid = await _upload_recording(client, "alice", pid)

    r = await client.get(f"/api/transcriber/projects/{pid}/recordings", headers={USER_HEADER: "bob"})
    assert r.status_code == 404, "IDOR (#9968): bob listed alice's recordings"
    r = await client.get(f"/api/transcriber/recordings/{rid}", headers={USER_HEADER: "bob"})
    assert r.status_code == 404, "IDOR (#9968): bob read alice's recording"
    r = await client.delete(f"/api/transcriber/recordings/{rid}", headers={USER_HEADER: "bob"})
    assert r.status_code == 404, "IDOR (#9968): bob deleted alice's recording"
    r = await client.post(
        f"/api/transcriber/projects/{pid}/recordings",
        files={"file": ("b.wav", io.BytesIO(b"RIFF" + b"\x00" * 8), "audio/wav")},
        headers={USER_HEADER: "bob"},
    )
    assert r.status_code == 404, "IDOR (#9968): bob uploaded into alice's project"


@pytest.mark.asyncio
async def test_legacy_default_rows_stay_accessible(client):
    """Pre-auth rows (stamped DEFAULT_USER) remain readable by any caller."""
    r = await client.post(
        "/api/transcriber/projects", json={"name": "legacy", "description": ""}
    )  # no user header -> DEFAULT_USER
    pid = r.json()["id"]
    r = await client.get(f"/api/transcriber/projects/{pid}", headers={USER_HEADER: "bob"})
    assert r.status_code == 200
