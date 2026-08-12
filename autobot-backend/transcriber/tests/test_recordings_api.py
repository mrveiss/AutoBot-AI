# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_recordings_api.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
import asyncio
import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from transcriber.database import Database
from transcriber.deps import DEFAULT_USER, get_db
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

    try:
        try:
            async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
                yield c
        finally:
            # #13861: aiosqlite's connection runs on a NON-daemon worker thread, so a
            # fixture that connects and never closes keeps the interpreter alive after the
            # suite has passed. Under xdist the execnet worker exits hard and hides it; in a
            # serial invocation the job hangs until CI cancels it, with no failure to look at.
            await db.close()
    finally:
        # #13861: aiosqlite's connection runs on a NON-daemon worker thread, so a
        # fixture that connects and never closes keeps the interpreter alive after
        # the suite has passed. Under xdist the execnet worker exits hard and hides
        # it; in a serial invocation — co-located-smoke is exactly that — the job
        # hangs until CI cancels it, with no failure to look at.
        await db.close()


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
async def test_upload_recording_with_relative_upload_dir(tmp_path, monkeypatch):
    """GH#12310: a *relative* upload dir (the shipped default) must still yield 202.

    Production set ``transcriber_upload_dir`` to a cwd-relative path, but
    ``create_recording`` rejects non-absolute filepaths, so every upload 500'd
    and left an orphaned file behind. The route now resolves the dir to an
    absolute path before writing/inserting.
    """
    monkeypatch.chdir(tmp_path)
    rel_upload = "data/transcriber/uploads"
    (tmp_path / rel_upload).mkdir(parents=True)

    a = FastAPI()
    db = Database(str(tmp_path / "test.db"))
    await db.connect()

    async def override_db():
        return db

    a.dependency_overrides[get_db] = override_db
    a.state.transcriber_upload_dir = rel_upload  # relative, exactly as shipped
    a.include_router(projects_router, prefix="/api/transcriber")
    a.include_router(recordings_router, prefix="/api/transcriber")

    async with AsyncClient(transport=ASGITransport(app=a), base_url="http://test") as c:
        r = await c.post("/api/transcriber/projects", json={"name": "P", "description": ""})
        pid = r.json()["id"]
        # Deferred `from tasks.transcriber_tasks import transcribe_recording`
        # in the handler — patch the source module to skip the Celery broker.
        with patch("tasks.transcriber_tasks.transcribe_recording", MagicMock()):
            r2 = await c.post(
                f"/api/transcriber/projects/{pid}/recordings",
                files={"file": ("rel.wav", io.BytesIO(b"RIFF" + b"\x00" * 100), "audio/wav")},
            )

    assert r2.status_code == 202, r2.text
    rid = r2.json()["id"]
    rec = await db.get_recording(rid)
    # Stored filepath is absolute and the audio landed under the resolved dir.
    assert rec is not None
    stored = rec["filepath"]
    assert stored.startswith("/"), stored
    saved = tmp_path / rel_upload
    files = list(saved.iterdir())
    assert len(files) == 1, files
    assert files[0].read_bytes().startswith(b"RIFF")

    # #13861: aiosqlite's worker thread is non-daemon, so an unclosed
    # connection keeps the interpreter alive after the test passes.
    await db.close()


@pytest.mark.asyncio
async def test_failed_insert_unlinks_orphan(client, tmp_path, monkeypatch):
    """GH#12310: a DB insert failure must not leak the partial upload file."""
    import transcriber.routes.recordings as rec_mod

    # Locate the resolved upload dir the fixture wired up.
    r = await client.post("/api/transcriber/projects", json={"name": "P", "description": ""})
    pid = r.json()["id"]

    async def boom(*args, **kwargs):
        raise ValueError("filepath must be absolute, got: 'x'")

    monkeypatch.setattr(rec_mod.Database, "create_recording", boom, raising=True)
    # The ASGI test transport re-raises the handler exception (no server-side
    # 500 wrapper); in production this surfaces as HTTP 500. Either way the
    # partial upload must be cleaned up.
    with pytest.raises(ValueError):
        await client.post(
            f"/api/transcriber/projects/{pid}/recordings",
            files={"file": ("orphan.wav", io.BytesIO(b"RIFF" + b"\x00" * 10), "audio/wav")},
        )
    # No orphan left behind in the upload dir.
    upload_dir = tmp_path / "uploads"
    assert list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_upload_recording_rejects_oversized_and_cleans_up(client, tmp_path, monkeypatch):
    """GH#12331: uploads exceeding MAX_FILE_SIZE are rejected with 413 during
    streaming (never buffered in memory) and the partial file is deleted."""
    import transcriber.routes.recordings as rec_mod

    monkeypatch.setattr(rec_mod, "MAX_FILE_SIZE", 10)

    r = await client.post("/api/transcriber/projects", json={"name": "P", "description": ""})
    pid = r.json()["id"]

    oversized = b"RIFF" + b"\x00" * 100  # 104 bytes > 10-byte patched cap
    r2 = await client.post(
        f"/api/transcriber/projects/{pid}/recordings",
        files={"file": ("too_big.wav", io.BytesIO(oversized), "audio/wav")},
    )
    assert r2.status_code == 413, r2.text

    # No partial file left behind in the upload dir.
    upload_dir = tmp_path / "uploads"
    assert list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_upload_recording_at_limit_succeeds(client, tmp_path, monkeypatch):
    """GH#12331: an upload at or under MAX_FILE_SIZE is written through untouched."""
    import transcriber.routes.recordings as rec_mod

    monkeypatch.setattr(rec_mod, "MAX_FILE_SIZE", 104)

    r = await client.post("/api/transcriber/projects", json={"name": "P", "description": ""})
    pid = r.json()["id"]

    exact = b"RIFF" + b"\x00" * 100  # exactly 104 bytes == patched cap
    with patch("tasks.transcriber_tasks.transcribe_recording", MagicMock()):
        r2 = await client.post(
            f"/api/transcriber/projects/{pid}/recordings",
            files={"file": ("exact.wav", io.BytesIO(exact), "audio/wav")},
        )
    assert r2.status_code == 202, r2.text

    upload_dir = tmp_path / "uploads"
    files = list(upload_dir.iterdir())
    assert len(files) == 1
    assert len(files[0].read_bytes()) == 104


@pytest.mark.asyncio
async def test_upload_recording_cancelled_mid_write_cleans_up(tmp_path):
    """GH#12417: a client disconnect mid-upload raises asyncio.CancelledError,
    a BaseException (not Exception) — the partial file must still be unlinked
    and the CancelledError must still propagate (never swallowed)."""
    import transcriber.routes.recordings as rec_mod

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    db = Database(str(tmp_path / "test.db"))
    await db.connect()
    pid = await db.create_project("P", "", user_id=DEFAULT_USER)

    class FlakyFile:
        filename = "cancelled.wav"

        def __init__(self):
            self._reads = 0

        async def read(self, n):
            self._reads += 1
            if self._reads == 1:
                return b"RIFF" + b"\x00" * 10
            raise asyncio.CancelledError()

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(transcriber_upload_dir=str(upload_dir))),
        state=SimpleNamespace(),
    )

    with pytest.raises(asyncio.CancelledError):
        await rec_mod.upload_recording(pid, request, FlakyFile(), db)

    # No orphan left behind — cleanup ran despite the BaseException.
    assert list(upload_dir.iterdir()) == []

    # #13861: aiosqlite's worker thread is non-daemon, so an unclosed
    # connection keeps the interpreter alive after the test passes.
    await db.close()


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
