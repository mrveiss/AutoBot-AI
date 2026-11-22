# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""POST /files/upload takes ONE file in the form field ``file`` per request (#22015).

The file browser sends a multi-file selection as one request per file, so the route's per-file validation
(type, size, content, existing-file refusal) judges each file. These tests drive the real route.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.files as files_api


@pytest.fixture
def client(monkeypatch, tmp_path):
    async def _allowed(_request, _permission):
        return True, {"username": "tester", "role": "admin"}

    async def _no_emit(_target):
        return None

    monkeypatch.setattr(files_api, "SANDBOXED_ROOT", tmp_path)
    monkeypatch.setattr(files_api, "get_auth_middleware", lambda: SimpleNamespace(check_file_permissions=_allowed))
    monkeypatch.setattr(files_api, "_emit_document_uploaded", _no_emit)
    app = FastAPI()
    app.state.security_layer = SimpleNamespace(audit_log=lambda *a, **k: None)
    app.include_router(files_api.router, prefix="/api/files")
    return TestClient(app, raise_server_exceptions=False)


def _post(client, name, body=b"hello\n", **data):
    return client.post("/api/files/upload", files={"file": (name, body)}, data={"path": "docs", **data})


def test_one_file_is_stored_in_the_chosen_folder(client, tmp_path):
    response = _post(client, "a.txt")
    assert response.status_code == 200, response.text
    assert (tmp_path / "docs" / "a.txt").read_bytes() == b"hello\n"


def test_several_files_are_several_requests_each_stored(client, tmp_path):
    assert _post(client, "a.txt").status_code == 200
    assert _post(client, "b.txt", b"second\n").status_code == 200
    assert sorted(p.name for p in (tmp_path / "docs").iterdir()) == ["a.txt", "b.txt"]


def test_the_plural_field_the_old_frontend_sent_is_still_refused(client):
    response = client.post("/api/files/upload", files={"files": ("a.txt", b"x")}, data={"path": "docs"})
    assert response.status_code == 422
    assert [e["loc"][-1] for e in response.json()["detail"] if e["type"] == "missing"] == ["file"]


def test_a_disallowed_type_is_refused_with_the_reason(client, tmp_path):
    response = _post(client, "run.exe")
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]
    assert not (tmp_path / "docs" / "run.exe").exists()


def test_an_oversized_file_is_refused_with_the_reason(client, monkeypatch):
    monkeypatch.setattr(files_api, "MAX_FILE_SIZE", 4)
    response = _post(client, "big.txt", b"0123456789")
    assert response.status_code == 413
    assert "too large" in response.json()["detail"].lower()


def test_an_existing_file_is_refused_unless_overwrite_is_sent(client, tmp_path):
    assert _post(client, "a.txt").status_code == 200
    refused = _post(client, "a.txt", b"new\n", overwrite="false")
    assert refused.status_code == 409
    assert "already exists" in refused.json()["detail"]
    assert _post(client, "a.txt", b"new\n", overwrite="true").status_code == 200
    assert (tmp_path / "docs" / "a.txt").read_bytes() == b"new\n"
