# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The owner's file panel: list, download, preview and delete under the upload's ownership rule (#20195).

Maintainer decision 2026-10-31. Each route is gated by ``_authorize_file_operation(existing_only=True)``
(the real ``SecurityLayer`` grants, the real STRICT ownership gate, the REAL manager on real SQLite):

| route    | grant      | ``user`` (owner) | ``readonly`` (owner) | non-owner | admin | no credential |
|----------|------------|------------------|----------------------|-----------|-------|---------------|
| list     | files.view | 200              | 200                  | 403       | 200   | 401           |
| preview  | files.view | 200              | 200                  | 403       | 200   | 401           |
| download | files.download | 200          | 200                  | 403       | 200   | 401           |
| delete   | files.delete | 200 (ownership) | 403                 | 403       | 200   | 401           |

Delete stays soft: the row is flagged, the bytes stay on disk (removal is #20234).
"""

# flake8: noqa: F811 -- fixtures imported from the sibling test modules are redefined as test arguments

from __future__ import annotations

import pytest

from api.conversation_files_owner_upload_20133_test import (  # noqa: F401 -- fixture
    _ADMIN,
    _ALICE,
    _BOB,
    _READONLY,
    world,
)
from api.conversation_files_real_manager_20225_test import _BODY, _SESSION, _rows, _seed, real  # noqa: F401

_BASE = f"/api/conversation/{_SESSION}"


def _call(w, kind: str, file_id: str):
    return {
        "list": lambda: w.client.get(f"{_BASE}/list"),
        "preview": lambda: w.client.get(f"{_BASE}/preview/{file_id}"),
        "download": lambda: w.client.get(f"{_BASE}/download/{file_id}"),
        "delete": lambda: w.client.delete(f"{_BASE}/files/{file_id}"),
    }[kind]()


_READS = ("list", "preview", "download")


@pytest.mark.parametrize("kind", [*_READS, "delete"])
def test_the_owner_may_use_every_panel_route(real, kind):
    file_id = _seed(real)
    real.user = dict(_ALICE)
    response = _call(real, kind, file_id)
    assert response.status_code == 200, (kind, response.text)


def test_the_owner_reads_the_real_bytes_and_text(real):
    file_id = _seed(real)
    real.user = dict(_ALICE)
    assert real.client.get(f"{_BASE}/download/{file_id}").content == _BODY
    preview = real.client.get(f"{_BASE}/preview/{file_id}").json()
    assert preview["preview_content"] == _BODY.decode() and "file_path" not in preview["file_info"]
    assert real.client.get(f"{_BASE}/list").json()["total_files"] == 1


def test_the_owner_delete_is_soft_the_bytes_stay_on_disk(real):
    file_id = _seed(real)
    real.user = dict(_ALICE)
    assert _call(real, "delete", file_id).status_code == 200
    assert _rows(real, "SELECT is_deleted FROM conversation_files WHERE file_id = ?", (file_id,)) == [(1,)]
    assert [p.read_bytes() for p in (real.tmp / "storage").rglob("*") if p.is_file()] == [_BODY]
    assert real.client.get(f"{_BASE}/list").json()["total_files"] == 0


@pytest.mark.parametrize("kind", [*_READS, "delete"])
def test_a_non_owner_is_refused_on_every_panel_route(real, kind):
    file_id = _seed(real)
    real.user = dict(_BOB)
    assert _call(real, kind, file_id).status_code == 403
    assert _rows(real, "SELECT is_deleted FROM conversation_files WHERE file_id = ?", (file_id,)) == [(0,)]


@pytest.mark.parametrize("kind", [*_READS, "delete"])
def test_an_admin_may_use_every_panel_route_on_any_conversation(real, kind):
    file_id = _seed(real)
    real.user = dict(_ADMIN)
    assert _call(real, kind, file_id).status_code == 200


@pytest.mark.parametrize("kind", [*_READS, "delete"])
def test_an_unauthenticated_request_is_401(real, kind):
    file_id = _seed(real)
    real.user = None
    assert _call(real, kind, file_id).status_code == 401
    assert _rows(real, "SELECT is_deleted FROM conversation_files WHERE file_id = ?", (file_id,)) == [(0,)]


@pytest.mark.parametrize("kind", _READS)
def test_readonly_may_view_and_download_its_own(real, kind):
    file_id = _seed(real)
    real.user = dict(_READONLY)
    assert _call(real, kind, file_id).status_code == 200


def test_readonly_must_not_delete_even_its_own(real):
    file_id = _seed(real)
    real.user = dict(_READONLY)
    assert _call(real, "delete", file_id).status_code == 403
    assert _rows(real, "SELECT is_deleted FROM conversation_files WHERE file_id = ?", (file_id,)) == [(0,)]


def test_a_non_admin_gets_404_on_an_unowned_conversation_not_a_claim(real):
    file_id = _seed(real)
    real.user, real.owner = dict(_ALICE), None
    assert _call(real, "list", file_id).status_code == 404


def test_the_real_grants_behind_the_table(real):
    layer = real.security_layer
    grants = {
        (role, op): layer.check_permission(role, f"files.{op}")
        for role in ("user", "readonly")
        for op in ("view", "download", "delete")
    }
    assert grants == {
        ("user", "view"): True,
        ("user", "download"): True,
        ("user", "delete"): False,
        ("readonly", "view"): True,
        ("readonly", "download"): True,
        ("readonly", "delete"): False,
    }
