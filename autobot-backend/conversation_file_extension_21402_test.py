# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A conversation file reports ONE ``extension`` on the upload, list and info routes (#21402).

The list/info SQL took everything after the FIRST dot (and the whole name when there was none) while the
upload response took the text after the LAST dot. Real SQLite and the real schema; only the Redis cache
invalidation is stubbed.
"""

from unittest.mock import AsyncMock

import pytest

from conversation_file_manager import ConversationFileManager
from conversation_file_route_api import file_extension

_SESSION = "session-ext"


@pytest.fixture
async def manager(tmp_path):
    mgr = ConversationFileManager(storage_dir=tmp_path / "storage", db_path=tmp_path / "files.db")
    mgr._initialize_schema()
    mgr._invalidate_session_cache = AsyncMock()
    return mgr


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("README", None),
        ("a.tar.gz", "gz"),
        (".bashrc", None),
        ("file.", None),
        ("A.TXT", "txt"),
        ("notes.md", "md"),
        ("dir.d/README", None),
        ("dir.d\\script.PY", "py"),
        ("", None),
    ],
)
def test_file_extension_rule(name, expected):
    assert file_extension(name) == expected


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [("README", b"plain readme", None), ("a.tar.gz", b"archive bytes", "gz")],
)
@pytest.mark.asyncio
async def test_upload_list_and_info_report_the_same_extension(manager, filename, content, expected):
    uploaded = await manager.upload_file(_SESSION, filename, content, "alice")
    listed = (await manager.list_files(_SESSION))["files"]
    info = await manager.get_file_info(_SESSION, uploaded["file_id"])

    assert [f["extension"] for f in listed] == [expected]
    assert uploaded["extension"] == expected
    assert info["extension"] == expected
