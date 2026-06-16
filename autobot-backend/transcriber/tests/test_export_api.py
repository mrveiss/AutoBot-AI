# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_export_api.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Integration tests for the real transcriber export endpoint (#9958).

Verifies that POST /api/transcriber/recordings/{recording_id}/export
returns real segment content for seeded recordings and enforces
ownership (404 for a different user's recording).
"""

from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.routes.export import router as export_router
from transcriber.routes.projects import router as projects_router
from transcriber.routes.recordings import router as recordings_router

USER_HEADER = "x-test-user"
OWNER = "alice"
OTHER = "bob"


@pytest_asyncio.fixture
async def seeded(tmp_path):
    """App with a seeded recording owned by OWNER with two segments."""
    app = FastAPI()
    db = Database(str(tmp_path / "test.db"))
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    async def override_db():
        return db

    @app.middleware("http")
    async def inject_user(request: Request, call_next):
        uid = request.headers.get(USER_HEADER)
        if uid:
            request.state.user = SimpleNamespace(id=uid)
        return await call_next(request)

    await db.connect()
    app.dependency_overrides[get_db] = override_db
    app.state.transcriber_db = db
    app.state.transcriber_upload_dir = str(upload_dir)
    app.include_router(projects_router, prefix="/api/transcriber")
    app.include_router(recordings_router, prefix="/api/transcriber")
    app.include_router(export_router, prefix="/api/transcriber")

    # Seed data: project → recording → speaker → 2 segments
    pid = await db.create_project("Test Project", "", OWNER)
    fake_file = upload_dir / "sample.wav"
    fake_file.write_bytes(b"RIFF" + b"\x00" * 32)
    rid = await db.create_recording(pid, "sample.wav", str(fake_file), OWNER)
    spk_id = await db.create_speaker(rid, "SPEAKER_00", "Alice Speaker", "en")
    await db.create_segment(rid, spk_id, 0.0, 3.5, "Hello from segment one.")
    await db.create_segment(rid, spk_id, 4.0, 7.0, "Hello from segment two.")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, rid


@pytest.mark.asyncio
async def test_export_srt_returns_real_content(seeded):
    """SRT export embeds the real seeded segment text."""
    client, rid = seeded
    r = await client.post(
        f"/api/transcriber/recordings/{rid}/export",
        json={"format": "srt", "include_speaker_names": True},
        headers={USER_HEADER: OWNER},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "-->" in body
    assert "Hello from segment one." in body
    assert "Hello from segment two." in body


@pytest.mark.asyncio
async def test_export_vtt_returns_real_content(seeded):
    """VTT export begins with WEBVTT and includes seeded segment text."""
    client, rid = seeded
    r = await client.post(
        f"/api/transcriber/recordings/{rid}/export",
        json={"format": "vtt", "include_speaker_names": True},
        headers={USER_HEADER: OWNER},
    )
    assert r.status_code == 200
    body = r.text
    assert body.startswith("WEBVTT")
    assert "Hello from segment one." in body


@pytest.mark.asyncio
async def test_export_docx_returns_bytes(seeded):
    """DOCX export returns a non-empty binary ZIP (DOCX magic bytes PK)."""
    pytest.importorskip("docx", reason="python-docx not installed")
    client, rid = seeded
    r = await client.post(
        f"/api/transcriber/recordings/{rid}/export",
        json={"format": "docx"},
        headers={USER_HEADER: OWNER},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert r.content[:2] == b"PK"


@pytest.mark.asyncio
async def test_export_pdf_returns_bytes(seeded):
    """PDF export returns content starting with PDF magic bytes."""
    pytest.importorskip("weasyprint", reason="weasyprint not installed")
    client, rid = seeded
    r = await client.post(
        f"/api/transcriber/recordings/{rid}/export",
        json={"format": "pdf"},
        headers={USER_HEADER: OWNER},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_export_ownership_denied_for_other_user(seeded):
    """A different user cannot export a recording they do not own."""
    client, rid = seeded
    r = await client.post(
        f"/api/transcriber/recordings/{rid}/export",
        json={"format": "srt"},
        headers={USER_HEADER: OTHER},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_export_nonexistent_recording_returns_404(seeded):
    """Export of a recording that does not exist returns 404."""
    client, _ = seeded
    r = await client.post(
        "/api/transcriber/recordings/99999/export",
        json={"format": "srt"},
        headers={USER_HEADER: OWNER},
    )
    assert r.status_code == 404
