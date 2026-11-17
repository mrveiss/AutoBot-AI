# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The stored ``mime_type`` of an uploaded conversation file (#21403).

The extension is authoritative; the client-declared part type is untrusted and is only the fallback for an
extension that maps to no type. Checked on the real manager and real SQLite, and on the pure rule.
"""

from __future__ import annotations

import pytest

from api.conversation_files_owner_upload_20133_test import world  # noqa: F401 -- fixture `real` builds on
from api.conversation_files_owner_upload_20133_test import _ALICE
from api.conversation_files_real_manager_20225_test import _SESSION, _rows, real  # noqa: F401 -- fixture
from conversation_file_route_api import resolve_mime_type


def _stored_mime(w, name, declared):
    w.user = dict(_ALICE)
    response = w.client.post(f"/api/conversation/{_SESSION}/upload", files={"file": (name, b"body\n", declared)})
    assert response.status_code == 200, response.text
    return _rows(
        w, "SELECT mime_type FROM conversation_files WHERE file_id = ?", (response.json()["file_info"]["file_id"],)
    )


def test_a_declared_type_that_differs_from_the_extension_does_not_win(real):  # noqa: F811
    assert _stored_mime(real, "notes.txt", "image/png") == [("text/plain",)]


def test_the_declared_type_is_the_fallback_for_an_extension_with_no_type(monkeypatch):
    monkeypatch.setattr("mimetypes.guess_type", lambda name: (None, None))
    assert resolve_mime_type("data.zzz", "Application/X-Zzz; charset=utf-8") == "application/x-zzz"


@pytest.mark.parametrize(
    "declared",
    [None, "", "application/octet-stream", "not a type", "text/html\r\nX: y", "a/b/c", "*/*", "x" * 300 + "/y"],
)
def test_a_missing_generic_or_malformed_declared_type_falls_back_to_octet_stream(monkeypatch, declared):
    monkeypatch.setattr("mimetypes.guess_type", lambda name: (None, None))
    assert resolve_mime_type("data.zzz", declared) == "application/octet-stream"


def test_the_extension_type_beats_a_declared_one_for_the_preview_and_download_checks():
    assert resolve_mime_type("pic.png", "text/html") == "image/png"
    assert resolve_mime_type("notes.txt", "image/svg+xml") == "text/plain"
