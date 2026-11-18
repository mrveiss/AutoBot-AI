# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19713 over HTTP: a video goes up in chunks past the size guard, and reaches the transcriber by path."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fastapi
import pytest
from fastapi.testclient import TestClient

from api import knowledge_chunked_upload as route
from auth_middleware import check_admin_permission
from middleware.validation_middleware import ValidationMiddleware
from services import chunked_upload as uploads

_URL = "/api/knowledge_base/uploads"
_VIDEO = bytes(range(256)) * 12_000  # about 3 MB, past the guard's 1 MiB in one chunk


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOBOT_UPLOAD_STAGING_DIR", str(tmp_path))
    app = fastapi.FastAPI()
    app.add_middleware(ValidationMiddleware)
    app.include_router(route.router, prefix="/api/knowledge_base")
    app.dependency_overrides[check_admin_permission] = lambda: True
    auth = MagicMock(get_user_from_request=lambda request: {"user_id": request.headers.get("x-user", "alice")})
    with patch.object(route, "get_auth_middleware", return_value=auth):
        yield TestClient(app)


def _read(path: str) -> bytes:
    return Path(path).read_bytes()


def _create(client: TestClient, **extra) -> dict:
    body = {"filename": "talk.mp4", "total_size": len(_VIDEO), "target": "transcript", **extra}
    reply = client.post(_URL, json=body)
    assert reply.status_code == 200, reply.text
    return reply.json()


def _send_all(client: TestClient, upload_id: str) -> None:
    sent = 0
    while sent < len(_VIDEO):
        piece = _VIDEO[sent : sent + uploads.CHUNK_BYTES]
        headers = {"X-Chunk-SHA256": hashlib.sha256(piece).hexdigest(), "Content-Type": "application/octet-stream"}
        reply = client.put(f"{_URL}/{upload_id}/chunks", params={"offset": sent}, content=piece, headers=headers)
        assert reply.status_code == 200, reply.text
        sent = reply.json()["received"]


def test_a_chunk_past_the_size_guard_reaches_the_route_and_a_video_reaches_the_transcriber(client) -> None:
    upload = _create(client, title="Talk", category="audio", tags=["a"])
    _send_all(client, upload["upload_id"])

    seen = {}

    async def transcribe(**kwargs):
        seen.update(kwargs, content=_read(kwargs["source"]))
        return SimpleNamespace(document_id="doc", word_count=3)

    with (
        patch("api.knowledge.get_or_create_knowledge_base", AsyncMock(return_value=object())),
        patch("api.knowledge._ingest_audio_source", transcribe),
    ):
        reply = client.post(f"{_URL}/{upload['upload_id']}/complete")
    assert reply.status_code == 202, reply.text
    assert seen["content"] == _VIDEO and seen["source"].endswith(".mp4") and seen["title"] == "Talk"
    final = client.get(f"{_URL}/{upload['upload_id']}").json()
    assert final["state"] == "done" and final["result"] == {"document_id": "doc", "word_count": 3}
    assert final["sha256"] == hashlib.sha256(_VIDEO).hexdigest()
    assert not Path(seen["source"]).exists(), "the staged file goes once the handoff is recorded"


def test_a_failed_handoff_says_why_and_can_be_tried_again(client) -> None:
    upload = _create(client)
    _send_all(client, upload["upload_id"])
    with (
        patch("api.knowledge.get_or_create_knowledge_base", AsyncMock(return_value=object())),
        patch("api.knowledge._ingest_audio_source", AsyncMock(side_effect=RuntimeError("whisper down"))),
    ):
        client.post(f"{_URL}/{upload['upload_id']}/complete")
    failed = client.get(f"{_URL}/{upload['upload_id']}").json()
    assert failed["state"] == "failed" and failed["error"] == "upload.handoff_failed", "a code, no internals"
    with (
        patch("api.knowledge.get_or_create_knowledge_base", AsyncMock(return_value=object())),
        patch(
            "api.knowledge._ingest_audio_source",
            AsyncMock(return_value=SimpleNamespace(document_id="d", word_count=1)),
        ),
    ):
        assert client.post(f"{_URL}/{upload['upload_id']}/complete").status_code == 202
    assert client.get(f"{_URL}/{upload['upload_id']}").json()["state"] == "done"


def test_a_wrong_offset_answers_with_where_to_resume(client) -> None:
    upload = _create(client)
    reply = client.put(f"{_URL}/{upload['upload_id']}/chunks", params={"offset": 5}, content=b"x")
    assert reply.status_code == 409 and reply.json()["detail"] == {"received": 0}


def test_someone_else_cant_see_or_add_to_an_upload(client) -> None:
    upload = _create(client)
    other = {"x-user": "mallory"}
    assert client.get(f"{_URL}/{upload['upload_id']}", headers=other).status_code == 404
    assert (
        client.put(
            f"{_URL}/{upload['upload_id']}/chunks", params={"offset": 0}, content=b"x", headers=other
        ).status_code
        == 404
    )


def test_a_document_is_held_to_the_document_limit(client) -> None:
    body = {"filename": "big.pdf", "total_size": route.DOCUMENT_MAX_BYTES + 1, "target": "document"}
    assert client.post(_URL, json=body).status_code == 413


def test_a_transcript_of_a_type_that_isnt_media_is_refused(client) -> None:
    body = {"filename": "evil.exe", "total_size": 10, "target": "transcript"}
    assert client.post(_URL, json=body).status_code >= 400


def test_the_limits_come_from_the_backend(client) -> None:
    limits = client.get(f"{_URL}/limits").json()
    assert limits["chunk_bytes"] == uploads.CHUNK_BYTES and ".mp4" in limits["media_extensions"]


def test_every_route_needs_the_admin_permission() -> None:
    for candidate in route.router.routes:
        calls = [dep.call for dep in candidate.dependant.dependencies]
        assert check_admin_permission in calls, candidate.path


def test_a_full_store_answers_507_with_a_code(client, monkeypatch) -> None:
    monkeypatch.setattr(uploads, "MAX_STAGED_BYTES", 1)
    reply = client.post(_URL, json={"filename": "t.mp4", "total_size": 10, "target": "transcript"})
    assert reply.status_code == 507 and reply.json()["detail"]["code"] == "upload.no_space"


def test_an_admin_can_remove_a_listed_session_and_it_is_audited(client, monkeypatch) -> None:
    upload = _create(client)
    other = {"x-user": "another-admin"}
    assert client.delete(f"{_URL}/expired/{upload['upload_id']}", headers=other).status_code == 409, "not listed yet"
    monkeypatch.setattr(uploads, "SESSION_TTL_S", -1)
    durable = AsyncMock(return_value=False)
    with patch.object(route, "audit_log", durable):
        assert client.delete(f"{_URL}/expired/{upload['upload_id']}", headers=other).status_code == 503
    assert client.get(f"{_URL}/{upload['upload_id']}").status_code == 200, "no record, so nothing was removed"
    durable.return_value = True
    with patch.object(route, "audit_log", durable):
        assert client.delete(f"{_URL}/expired/{upload['upload_id']}", headers=other).status_code == 200
    kwargs = durable.await_args.kwargs
    assert kwargs["durable"] is True and kwargs["user_id"] == "another-admin"
    assert kwargs["resource"] == upload["upload_id"]
    assert client.get(f"{_URL}/{upload['upload_id']}").status_code == 404


def test_a_chunk_for_a_cancelled_upload_answers_404(client) -> None:
    upload = _create(client)
    assert client.delete(f"{_URL}/{upload['upload_id']}").status_code == 200
    assert client.put(f"{_URL}/{upload['upload_id']}/chunks", params={"offset": 0}, content=b"x").status_code == 404
