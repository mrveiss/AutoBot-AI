# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /recordings/{id}/progress SSE stream (#20910).

Pins ownership (same 404 as get_recording), the event shape useSseProgress.ts
parses, termination on complete/error, and the max-duration bound. Status
changes are driven from the fake sleep, so there are no real sleeps.
"""

import json
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from transcriber.database import Database
from transcriber.deps import authenticate, get_transcriber_db_from_request
from transcriber.models import RecordingStatus
from transcriber.routes import recordings as rec_routes

USER_HEADER = "x-test-user"


@pytest_asyncio.fixture
async def db(tmp_path):
    _db = Database(str(tmp_path / "t.db"))
    await _db.connect()
    try:
        yield _db
    finally:
        await _db.close()


@pytest_asyncio.fixture
async def client(db):
    app = FastAPI()

    @app.middleware("http")
    async def set_user(request: Request, call_next):
        uid = request.headers.get(USER_HEADER)
        if uid:
            request.state.user = SimpleNamespace(id=uid)
        return await call_next(request)

    app.dependency_overrides[get_transcriber_db_from_request] = lambda: db
    app.dependency_overrides[authenticate] = lambda: None
    app.include_router(rec_routes.router, prefix="/api/transcriber")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def rec_id(db, tmp_path):
    pid = await db.create_project("p", "", "alice")
    return await db.create_recording(pid, "a.wav", str(tmp_path / "a.wav"), "alice")


def _script_sleep(monkeypatch, db, rid, statuses):
    """Replace the route's pause: each tick advances the recording to the next status."""
    steps = list(statuses)
    ticks = []

    async def fake_sleep(_delay):
        ticks.append(1)
        if steps:
            await db.update_recording_status(rid, steps.pop(0))

    monkeypatch.setattr(rec_routes, "_sleep", fake_sleep)
    return ticks


def _events(body: str) -> list[dict]:
    return [json.loads(c[len("data: ") :]) for c in body.split("\n\n") if c.startswith("data: ")]


async def _stream(client, rid, user="alice"):
    return await client.get(f"/api/transcriber/recordings/{rid}/progress", headers={USER_HEADER: user})


@pytest.mark.asyncio
async def test_owner_streams_until_complete(client, db, rec_id, monkeypatch):
    _script_sleep(monkeypatch, db, rec_id, [RecordingStatus.PROCESSING.value, RecordingStatus.COMPLETE.value])
    r = await _stream(client, rec_id)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert _events(r.text) == [
        {"percent": 0, "step": "pending"},
        {"percent": 0, "step": "processing"},
        {"percent": 100, "step": "complete"},
    ]


@pytest.mark.asyncio
async def test_stream_ends_with_error_event(client, db, rec_id, monkeypatch):
    _script_sleep(monkeypatch, db, rec_id, [RecordingStatus.ERROR.value])
    events = _events((await _stream(client, rec_id)).text)
    assert events[-1] == {"error": True, "step": "error"}
    assert all("percent" not in e for e in events[1:])


@pytest.mark.asyncio
async def test_unchanged_status_emits_once(client, db, rec_id, monkeypatch):
    seq = [RecordingStatus.PENDING.value, RecordingStatus.PENDING.value, RecordingStatus.COMPLETE.value]
    ticks = _script_sleep(monkeypatch, db, rec_id, seq)
    events = _events((await _stream(client, rec_id)).text)
    assert [e["step"] for e in events] == ["pending", "complete"]
    assert len(ticks) == 3


@pytest.mark.asyncio
async def test_non_owner_and_unknown_id_get_404(client, rec_id):
    assert (await _stream(client, rec_id, user="bob")).status_code == 404
    assert (await _stream(client, rec_id + 999)).status_code == 404


@pytest.mark.asyncio
async def test_max_duration_bound_ends_with_timeout_event(client, db, rec_id, monkeypatch):
    monkeypatch.setattr(rec_routes, "_PROGRESS_POLL_S", 1.0)
    monkeypatch.setattr(rec_routes, "_PROGRESS_MAX_S", 3.0)
    ticks = _script_sleep(monkeypatch, db, rec_id, [])
    events = _events((await _stream(client, rec_id)).text)
    assert len(ticks) == 3
    assert events == [{"percent": 0, "step": "pending"}, {"error": True, "step": "timeout"}]


@pytest.mark.asyncio
async def test_recording_deleted_mid_stream_reports_missing(client, db, rec_id, monkeypatch):
    async def fake_sleep(_delay):
        await db._db().execute("DELETE FROM recordings WHERE id=?", (rec_id,))
        await db._db().commit()

    monkeypatch.setattr(rec_routes, "_sleep", fake_sleep)
    events = _events((await _stream(client, rec_id)).text)
    assert events[-1] == {"error": True, "step": "missing"}


@pytest.mark.parametrize("raw", ["abc", "0", "-5", "nan"])
def test_poll_interval_env_cannot_become_a_busy_loop(monkeypatch, raw):
    import importlib

    monkeypatch.setenv("AUTOBOT_TRANSCRIBER_PROGRESS_POLL_S", raw)
    try:
        mod = importlib.reload(rec_routes)
        assert mod._PROGRESS_POLL_S == 1.0
    finally:
        monkeypatch.delenv("AUTOBOT_TRANSCRIBER_PROGRESS_POLL_S")
        importlib.reload(rec_routes)
