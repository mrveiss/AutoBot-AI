# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""DELETE /sources/{id} never returns a host path on a cleanup failure (#17065).

`source.error_message` is set once, at delete time, by
`delete_source_and_cleanup()` -- this proves the DELETE response carries the
sanitized value; a later `GET` would read back the same stored field, so
there is no second sanitization point to test separately.
"""

import errno
import shutil

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.codebase_analytics import source_paths, source_service
from api.codebase_analytics.endpoints import sources as sources_ep
from api.codebase_analytics.source_models import CodeSource, SourceStatus


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(sources_ep.router)
    return TestClient(app)


def test_a_failed_delete_reports_status_and_a_path_free_error_message(monkeypatch, tmp_path):
    clone_dir = tmp_path / "clone-1"
    clone_dir.mkdir()
    source = CodeSource(name="x", clone_path=str(clone_dir))

    async def _fake_get_source(_source_id):
        return source

    def _boom(_path):
        raise OSError(errno.EACCES, "Permission denied", str(clone_dir))

    async def _fake_save(_src):
        return True

    monkeypatch.setattr(sources_ep, "get_source", _fake_get_source)
    monkeypatch.setattr(source_paths, "CODE_SOURCES_BASE", tmp_path)
    monkeypatch.setattr(shutil, "rmtree", _boom)
    monkeypatch.setattr(source_service, "save_source", _fake_save)

    response = _client().delete(f"/sources/{source.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["status"] == SourceStatus.CLEANUP_FAILED.value
    assert str(clone_dir) not in body["error_message"]
    assert str(tmp_path) not in body["error_message"]
    assert "Permission denied" in body["error_message"]
