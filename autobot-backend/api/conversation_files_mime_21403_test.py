# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The stored ``mime_type`` of an uploaded conversation file (#21403).

The extension is authoritative; the client-declared part type is untrusted and is only the fallback for an
extension that maps to no type, and then only from a short list of inert types. Checked on the real manager
and real SQLite (through the preview and download routes), and on the pure rule.
"""

from __future__ import annotations

import mimetypes

import pytest

from api.conversation_files_owner_upload_20133_test import world  # noqa: F401 -- fixture `real` builds on
from api.conversation_files_owner_upload_20133_test import _ALICE
from api.conversation_files_real_manager_20225_test import _SESSION, _as_admin, _rows, real  # noqa: F401 -- fixture
from conversation_file_route_api import resolve_mime_type

_REAL_GUESS = mimetypes.guess_type


def _untyped(monkeypatch, suffix=".cfg"):
    """Make ``mimetypes`` unable to type *suffix*, as on a host whose mime.types lacks it."""
    monkeypatch.setattr(
        mimetypes, "guess_type", lambda name, *a, **k: (None, None) if name.endswith(suffix) else _REAL_GUESS(name)
    )


def _upload(w, name, declared):
    w.user = dict(_ALICE)
    response = w.client.post(f"/api/conversation/{_SESSION}/upload", files={"file": (name, b"<b>x</b>\n", declared)})
    assert response.status_code == 200, response.text
    return response.json()["file_info"]["file_id"]


def _stored_mime(w, file_id):
    return _rows(w, "SELECT mime_type FROM conversation_files WHERE file_id = ?", (file_id,))


def test_a_declared_type_that_differs_from_the_extension_does_not_win(real):  # noqa: F811
    assert _stored_mime(real, _upload(real, "notes.txt", "image/png")) == [("text/plain",)]


@pytest.mark.parametrize("declared", ["text/html", "image/svg+xml", "text/html; charset=utf-8"])
def test_a_script_capable_declared_type_stays_metadata_only(real, monkeypatch, declared):  # noqa: F811
    _untyped(monkeypatch)
    file_id = _upload(real, "x.cfg", declared)
    assert _stored_mime(real, file_id) == [("application/octet-stream",)]
    admin = _as_admin(real).client
    preview = admin.get(f"/api/conversation/{_SESSION}/preview/{file_id}").json()
    assert (preview["preview_available"], preview["preview_type"], preview["preview_content"]) == (
        False,
        "metadata_only",
        None,
    )
    download = admin.get(f"/api/conversation/{_SESSION}/download/{file_id}")
    assert download.headers["content-type"].startswith("application/octet-stream")
    assert download.headers["content-disposition"].startswith("attachment")


def test_a_benign_declared_type_on_an_untyped_extension_is_stored(real, monkeypatch):  # noqa: F811
    _untyped(monkeypatch)
    file_id = _upload(real, "x.cfg", "text/plain; charset=utf-8")
    assert _stored_mime(real, file_id) == [("text/plain",)]
    preview = _as_admin(real).client.get(f"/api/conversation/{_SESSION}/preview/{file_id}").json()
    assert (preview["preview_type"], preview["preview_content"]) == ("text", "<b>x</b>\n")


def test_the_declared_type_is_the_fallback_for_an_extension_with_no_type(monkeypatch):
    monkeypatch.setattr(mimetypes, "guess_type", lambda name: (None, None))
    assert resolve_mime_type("data.zzz", "Application/JSON; charset=utf-8") == "application/json"


@pytest.mark.parametrize(
    "declared",
    [
        None,
        "",
        "application/octet-stream",
        "not a type",
        "text/html",
        "image/svg+xml",
        "image/webp",
        "*/*",
        "text/html\r\nX: y",
    ],
)
def test_a_missing_generic_unlisted_or_malformed_declared_type_falls_back_to_octet_stream(monkeypatch, declared):
    monkeypatch.setattr(mimetypes, "guess_type", lambda name: (None, None))
    assert resolve_mime_type("data.zzz", declared) == "application/octet-stream"


def test_the_extension_type_beats_a_declared_one_for_the_preview_and_download_checks():
    assert resolve_mime_type("pic.png", "text/html") == "image/png"
    assert resolve_mime_type("notes.txt", "image/svg+xml") == "text/plain"
