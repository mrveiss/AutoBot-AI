# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20030: the ownerless report lists chat files without deleting, creating or dropping any."""

from chat_history.session_listing import SessionListingMixin


class _Manager(SessionListingMixin):
    def __init__(self, directory: str) -> None:
        self.directory = directory

    def _get_chats_directory(self) -> str:
        return self.directory

    async def _cleanup_old_session_files(self) -> None:
        raise AssertionError("a report must never run the old-file cleanup")


def _chats(tmp_path):
    (tmp_path / "a_chat.json").write_text("not json, not decryptable", encoding="utf-8")
    (tmp_path / "chat_b.json").write_text("{}", encoding="utf-8")
    (tmp_path / "chat_a.json").write_text("{}", encoding="utf-8")  # the older name of the same session
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    return str(tmp_path)


async def test_lists_both_file_names_once_each_without_reading_them(tmp_path) -> None:
    assert await _Manager(_chats(tmp_path)).list_session_ids() == [{"chatId": "a"}, {"chatId": "b"}]


async def test_an_absent_directory_lists_nothing_and_is_not_created(tmp_path) -> None:
    missing = tmp_path / "chats"
    assert await _Manager(str(missing)).list_session_ids() == []
    assert not missing.exists()
