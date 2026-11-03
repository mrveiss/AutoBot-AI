# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20030: an owned session under the older file name does not read as ownerless."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chat_history.session_metadata_persist_test import _StubManager


def _write(tmp_path: Path, name: str, metadata: dict) -> None:
    (tmp_path / name).write_text(json.dumps({"messages": [], "metadata": metadata}), encoding="utf-8")


@pytest.mark.parametrize("name", ["s1_chat.json", "chat_s1.json"])
@pytest.mark.parametrize("key", ["owner", "username"])
async def test_either_file_name_gives_the_owner(tmp_path: Path, name: str, key: str) -> None:
    _write(tmp_path, name, {key: "alice"})
    assert await _StubManager(str(tmp_path)).get_session_owner("s1") == "alice"


async def test_the_current_name_wins_when_both_exist(tmp_path: Path) -> None:
    _write(tmp_path, "s1_chat.json", {"owner": "alice"})
    _write(tmp_path, "chat_s1.json", {"owner": "bob"})
    assert await _StubManager(str(tmp_path)).get_session_owner("s1") == "alice"


@pytest.mark.parametrize("files", [[], ["chat_s1.json"]], ids=["no-file", "no-owner-on-file"])
async def test_no_owner_recorded_reads_none(tmp_path: Path, files: list) -> None:
    for name in files:
        _write(tmp_path, name, {})
    assert await _StubManager(str(tmp_path)).get_session_owner("s1") is None


def _link_out(tmp_path: Path) -> Path:
    """A chats directory whose s1 chat file is a link to a file outside it."""
    chats, outside = tmp_path / "chats", tmp_path / "elsewhere.json"
    chats.mkdir()
    outside.write_text(json.dumps({"messages": [], "metadata": {"owner": "mallory"}}), encoding="utf-8")
    (chats / "s1_chat.json").symlink_to(outside)
    return chats


async def test_a_chat_file_linked_outside_the_chats_directory_is_not_read(tmp_path: Path) -> None:
    """A link out of the chats directory is refused, not followed (validate_relative_path resolves it)."""
    from security.session_owner_errors import SessionOwnerUnreadable

    with pytest.raises(SessionOwnerUnreadable):
        await _StubManager(str(_link_out(tmp_path))).get_session_owner("s1")
