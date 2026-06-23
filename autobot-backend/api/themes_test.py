# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import theme_install
from api import themes as themes_api
from auth_middleware import check_admin_permission


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(theme_install, "themes_dir", lambda: tmp_path)
    app = FastAPI()
    # Mirror the core-router registry, which mounts every router under "/api".
    # This guards against the /api/api/themes double-prefix regression (#10472).
    app.include_router(themes_api.router, prefix="/api")
    app.dependency_overrides[check_admin_permission] = lambda: True
    return TestClient(app)


def _zip(theme_id="aqua"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("theme.json", json.dumps({"id": theme_id, "name": "Aqua", "author": "me", "version": "1.0.0"}))
        zf.writestr("theme.css", f'[data-theme-variant="{theme_id}"] {{ --bg-primary:#eef; }}')
    return buf.getvalue()


def test_upload_list_serve_delete(client):
    r = client.post("/api/themes", files={"file": ("aqua.zip", _zip(), "application/zip")})
    assert r.status_code == 200, r.text
    assert client.get("/api/themes").json()[0]["id"] == "aqua"
    css = client.get("/api/themes/aqua/theme.css")
    assert css.status_code == 200 and "data-theme-variant" in css.text
    assert client.delete("/api/themes/aqua").status_code == 200
    assert client.get("/api/themes").json() == []
