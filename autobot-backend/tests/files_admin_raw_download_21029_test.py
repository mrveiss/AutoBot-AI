# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#21029: ``GET /files/raw`` through a real FastAPI app and the REAL ``api.files`` path validator.

``/files/read`` decodes with ``errors="replace"``; ``/files/raw`` must return the bytes
untouched, only for an admin, only inside the allowed roots.
"""

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
    assert response.headers["content-disposition"] == "attachment; filename*=utf-8''%C3%A9%22q.bin"
