# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Renaming a session reads and writes its file through the encryption path (#19864)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from chat_history.file_io import FileIOMixin
from chat_history.security import SecurityMixin
from chat_history.session import SessionMixin

_MESSAGES = [{"id": "m1", "sender": "user", "text": "hi", "timestamp": "t0"}]
_METADATA = {"owner": "bob"}


class _Stub(SessionMixin, FileIOMixin):
    """A manager whose chat file is ciphertext, so a rename must decrypt it and encrypt the result."""

    def __init__(self, directory: str) -> None:
        self._directory = directory
        self._update_redis_session_cache = AsyncMock()
        self.encrypted: list = []  # everything that reached _encrypt_data

    def _get_chats_directory(self) -> str:
        return self._directory

    @staticmethod
    def _decrypt_data(data: str) -> dict:
        assert data == "ciphertext"
        return {"name": "old", "messages": _MESSAGES, "metadata": _METADATA}

    def _encrypt_data(self, data: dict) -> str:
        self.encrypted.append(data)
        return f"encrypted:{data['name']}"


@pytest.fixture
def chat_file(tmp_path):
    path = tmp_path / "s_chat.json"
    path.write_text("ciphertext", encoding="utf-8")
    return str(path)


async def test_a_rename_reads_an_encrypted_chat(chat_file) -> None:
    stub = _Stub(str(Path(chat_file).parent))
    assert await stub.update_session_name("s", "new") is True


async def test_a_rename_writes_through_the_encryption_path(chat_file) -> None:
    stub = _Stub(str(Path(chat_file).parent))
    await stub.update_session_name("s", "new")
    assert _read(chat_file) == "encrypted:new"
    (written,) = stub.encrypted
    assert written["name"] == "new"
    assert written["messages"] == _MESSAGES  # the rename keeps what the decrypted file carried
    assert written["metadata"] == _METADATA


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_ciphertext_without_a_key_says_so() -> None:
    mixin = SecurityMixin.__new__(SecurityMixin)
    mixin.encryption_enabled = False
    with pytest.raises(ValueError, match="line 1 column 1.*no key is set"):
        mixin._decrypt_data("gAAAAciphertext")
