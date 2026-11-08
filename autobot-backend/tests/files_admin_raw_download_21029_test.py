# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#21029: ``GET /files/raw`` through a real FastAPI app and the REAL ``api.files`` path validator.

``/files/read`` decodes with ``errors="replace"``; ``/files/raw`` must return the bytes
untouched, only for an admin, only inside the allowed roots.
"""

import os
import pathlib
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import files as files_api
from api import files_admin_raw

PAYLOAD = bytes([0xFF, 0xD8, 0x00, 0x80, 0x89, 0x50, 0x4E, 0x47])


@pytest.fixture
def root(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setattr(files_api, "_ADMIN_ALLOWED_DIRS", (str(allowed),))
    return allowed


@pytest.fixture
def app(real_auth_middleware):
    """The route's own gate is replaced by the REAL ``check_admin_permission``."""
    app = FastAPI()
    app.include_router(files_admin_raw.router, prefix="/files")
    app.dependency_overrides[files_admin_raw.check_admin_permission] = real_auth_middleware.check_admin_permission
    return app


@pytest.fixture
def as_user(real_auth_middleware):
    def _patch(user):
        return patch.object(real_auth_middleware, "resolve_human_user", AsyncMock(return_value=user))

    return _patch


@pytest.fixture
def admin(app, as_user):
    with as_user({"username": "root", "role": "admin"}):
        yield TestClient(app, raise_server_exceptions=False)


def _get(client, path):
    return client.get("/files/raw", params={"path": str(path)})


def test_non_admin_is_refused(app, as_user, root):
    (root / "a.bin").write_bytes(PAYLOAD)
    with as_user({"username": "bob", "role": "user"}), patch("auth_rbac.audit_role_denied"):
        assert _get(TestClient(app, raise_server_exceptions=False), root / "a.bin").status_code == 403


def test_unauthenticated_is_refused(app, as_user, root):
    (root / "a.bin").write_bytes(PAYLOAD)
    with as_user(None):
        assert _get(TestClient(app, raise_server_exceptions=False), root / "a.bin").status_code == 401


def test_binary_file_is_returned_byte_exact(admin, root):
    (root / "blob.bin").write_bytes(PAYLOAD)
    response = _get(admin, root / "blob.bin")
    assert response.status_code == 200
    assert response.content == PAYLOAD
    assert response.headers["content-type"] == "application/octet-stream"
    assert "blob.bin" in response.headers["content-disposition"]


@pytest.mark.parametrize(
    "relative",
    ["../outside.bin", "sub/../../outside.bin", "%2e%2e/outside.bin", "..%2foutside.bin"],
)
def test_parent_segments_are_refused(admin, root, relative):
    (root.parent / "outside.bin").write_bytes(PAYLOAD)
    response = admin.get("/files/raw", params={"path": f"{root}/{relative}"})
    assert response.status_code == 400
    assert response.content != PAYLOAD


def test_absolute_path_outside_the_roots_is_refused(admin, root):
    outside = root.parent / "outside.bin"
    outside.write_bytes(PAYLOAD)
    response = _get(admin, outside)
    assert response.status_code == 400
    assert response.content != PAYLOAD


def test_link_leaving_the_root_is_refused(admin, root):
    outside = root.parent / "outside.bin"
    outside.write_bytes(PAYLOAD)
    (root / "link.bin").symlink_to(outside)
    response = _get(admin, root / "link.bin")
    assert response.status_code == 400
    assert response.content != PAYLOAD


def test_directory_is_refused(admin, root):
    (root / "folder").mkdir()
    assert _get(admin, root / "folder").status_code == 400


def test_missing_file_is_404(admin, root):
    assert _get(admin, root / "missing.bin").status_code == 404


def test_unreadable_file_is_403_not_500(admin, root, monkeypatch):
    target = root / "locked.bin"
    target.write_bytes(PAYLOAD)
    real_open = pathlib.Path.open

    def deny(self, *args, **kwargs):
        if self.name == "locked.bin":
            raise PermissionError(13, "denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", deny)
    assert _get(admin, target).status_code == 403


def test_filename_with_quote_and_non_ascii_is_encoded(admin, root):
    (root / 'é"q.bin').write_bytes(PAYLOAD)
    response = _get(admin, root / 'é"q.bin')
    assert response.status_code == 200
    assert (
        response.headers["content-disposition"] == "attachment; filename=\"__q.bin\"; filename*=utf-8''%C3%A9%22q.bin"
    )


def test_file_vanishing_before_validation_is_404(admin, root, monkeypatch):
    target = root / "gone.bin"
    target.write_bytes(PAYLOAD)
    real_validate = files_admin_raw._validate_admin_path

    def vanish_first(path):
        target.unlink()
        return real_validate(path)

    monkeypatch.setattr(files_admin_raw, "_validate_admin_path", vanish_first)
    assert _get(admin, target).status_code == 404


def test_file_vanishing_after_the_check_before_streaming_is_404(admin, root, monkeypatch):
    target = root / "late.bin"
    target.write_bytes(PAYLOAD)
    real_open = pathlib.Path.open

    def vanish_then_open(self, *args, **kwargs):
        if self.name == "late.bin":
            self.unlink()
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", vanish_then_open)
    assert _get(admin, target).status_code == 404


def _record_threads(app, monkeypatch, inline):
    """Return (loop_idents, worker_idents) seen while serving one request; ``inline`` defeats to_thread."""
    import threading

    loop_idents, worker_idents = [], []

    @app.middleware("http")
    async def note_loop(request, call_next):
        loop_idents.append(threading.get_ident())
        return await call_next(request)

    for name in ("_prepare_download", "_read_chunk"):
        real = getattr(files_admin_raw, name)

        def wrapped(*args, _real=real):
            worker_idents.append(threading.get_ident())
            return _real(*args)

        monkeypatch.setattr(files_admin_raw, name, wrapped)
    if inline:

        async def direct(func, *args):
            return func(*args)

        monkeypatch.setattr(files_admin_raw.asyncio, "to_thread", direct)
    return loop_idents, worker_idents


@pytest.mark.parametrize("inline,expect_off_loop", [(False, True), (True, False)])
def test_preparation_and_reads_run_off_the_event_loop(app, as_user, root, monkeypatch, inline, expect_off_loop):
    (root / "t.bin").write_bytes(PAYLOAD)
    loop_idents, worker_idents = _record_threads(app, monkeypatch, inline)
    with as_user({"username": "root", "role": "admin"}):
        assert _get(TestClient(app, raise_server_exceptions=False), root / "t.bin").status_code == 200
    assert len(worker_idents) >= 2 and loop_idents
    assert all(w != loop_idents[0] for w in worker_idents) is expect_off_loop


def test_growing_file_sends_only_the_declared_length(admin, root, monkeypatch):
    target = root / "grow.bin"
    target.write_bytes(PAYLOAD)
    real_read = files_admin_raw._read_chunk

    def grow_then_read(handle, limit):
        with target.open("ab") as extra:
            extra.write(b"EXTRA")
        return real_read(handle, limit)

    monkeypatch.setattr(files_admin_raw, "_read_chunk", grow_then_read)
    response = _get(admin, target)
    assert response.content == PAYLOAD
    assert response.headers["content-length"] == str(len(PAYLOAD))


def test_truncated_file_is_an_error_not_a_short_success(admin, root, monkeypatch):
    target = root / "shrink.bin"
    target.write_bytes(PAYLOAD)
    real_read = files_admin_raw._read_chunk

    def shrink_then_read(handle, limit):
        target.write_bytes(b"")
        return real_read(handle, limit)

    monkeypatch.setattr(files_admin_raw, "_read_chunk", shrink_then_read)
    with pytest.raises(Exception):
        TestClient(admin.app, raise_server_exceptions=True).get("/files/raw", params={"path": str(target)})


def _run_response(response, receive_messages):
    import asyncio

    sent = []

    async def receive():
        return receive_messages.pop(0) if receive_messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send))
    return sent


def test_handle_is_closed_after_normal_completion(root):
    (root / "c.bin").write_bytes(PAYLOAD)
    handle = (root / "c.bin").open("rb")
    response = files_admin_raw._HandleResponse(handle, len(PAYLOAD))
    _run_response(response, [])
    assert handle.closed


def test_handle_is_closed_after_disconnect_before_first_chunk(root):
    (root / "d.bin").write_bytes(PAYLOAD)
    handle = (root / "d.bin").open("rb")
    response = files_admin_raw._HandleResponse(handle, len(PAYLOAD))

    async def refuse(message):
        raise OSError("client went away")

    import asyncio

    async def run():
        async def receive():
            return {"type": "http.disconnect"}

        await response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, refuse)

    with pytest.raises(OSError):
        asyncio.run(run())
    assert handle.closed


def test_content_length_matches_and_large_file_is_exact(admin, root):
    data = os.urandom(files_admin_raw._CHUNK_BYTES * 3 + 7)
    (root / "big.bin").write_bytes(data)
    response = _get(admin, root / "big.bin")
    assert response.content == data
    assert response.headers["content-length"] == str(len(data))
