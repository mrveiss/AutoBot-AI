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
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient

from api.transcripts import _resolve_user_id
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
    """can_access: strict ownership — owner yes, everyone else no.

    Cases required by #9968:
    (a) owner == caller → allow
    (b) different real users → deny
    (c) DEFAULT_USER row + DEFAULT_USER caller (single_user mode) → allow
    (d) DEFAULT_USER row + real user → DENY  (was the IDOR)
    (e) unowned / empty user_id → deny
    """
    # (a) owner == caller → allow
    assert can_access({"user_id": "alice"}, "alice") is True
    # (b) different real users → deny
    assert can_access({"user_id": "alice"}, "bob") is False
    # (c) single_user: DEFAULT_USER caller accesses DEFAULT_USER row → allow
    assert can_access({"user_id": DEFAULT_USER}, DEFAULT_USER) is True
    # (d) IDOR fix: real user must NOT access DEFAULT_USER-owned row
    assert can_access({"user_id": DEFAULT_USER}, "bob") is False
    # (e) unowned (no user_id key) → deny
    assert can_access({}, "bob") is False
    # (e) explicit empty string user_id → deny
    assert can_access({"user_id": ""}, "bob") is False


def test_resolve_user_id_returns_real_identity():
    """_resolve_user_id: returns user_id or username when present."""
    assert _resolve_user_id({"user_id": "alice"}) == "alice"
    assert _resolve_user_id({"username": "bob"}) == "bob"
    # user_id takes precedence over username
    assert _resolve_user_id({"user_id": "alice", "username": "other"}) == "alice"


def test_resolve_user_id_raises_when_no_identity():
    """_resolve_user_id: raises 403 — never silently returns DEFAULT_USER (#9968)."""
    with pytest.raises(HTTPException) as exc_info:
        _resolve_user_id({})
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        _resolve_user_id({"user_id": None, "username": None})
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        _resolve_user_id({"user_id": "", "username": ""})
    assert exc_info.value.status_code == 403


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
async def test_legacy_default_rows_not_accessible_to_other_users(client):
    """DEFAULT_USER rows are NOT shared across real users (#9968 IDOR fix).

    Pre-auth rows (stamped DEFAULT_USER) are accessible only by the
    DEFAULT_USER caller (single_user mode).  Real authenticated users are
    denied — the old "any caller can read default rows" behaviour was the
    IDOR.  Cross-user reassignment of legacy rows is tracked separately.
    """
    r = await client.post(
        "/api/transcriber/projects", json={"name": "legacy", "description": ""}
    )  # no user header -> DEFAULT_USER
    pid = r.json()["id"]
    # Real user bob is DENIED access to a DEFAULT_USER-owned row
    r = await client.get(f"/api/transcriber/projects/{pid}", headers={USER_HEADER: "bob"})
    assert r.status_code == 404, "IDOR (#9968): real user should not access DEFAULT_USER rows"
    # DEFAULT_USER caller (single_user) can still access its own rows
    r = await client.get(f"/api/transcriber/projects/{pid}", headers={USER_HEADER: DEFAULT_USER})
    assert r.status_code == 200
