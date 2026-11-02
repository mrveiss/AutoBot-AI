# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Renaming a session reads and writes its file through the encryption path (#19864)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from chat_history.security import SecurityMixin
from chat_history.session import SessionMixin


class _Stub:
    _update_redis_session_cache = AsyncMock()

    @staticmethod
    def _decrypt_data(data: str) -> dict:
        assert data == "ciphertext"
        return {"name": "old"}

    @staticmethod
    def _encrypt_data(data: dict) -> str:
        return f"encrypted:{data['name']}"


@pytest.fixture
def chat_file(tmp_path):
    path = tmp_path / "s_chat.json"
    path.write_text("ciphertext", encoding="utf-8")
    return str(path)


async def test_a_rename_reads_an_encrypted_chat(chat_file) -> None:
    updated = await SessionMixin._load_and_update_session_name(_Stub(), chat_file, "new")
    assert updated["name"] == "new"


async def test_a_rename_writes_through_the_encryption_path(chat_file) -> None:
    directory = str(Path(chat_file).parent)
    await SessionMixin._save_session_name_update(_Stub(), "s", directory, {"name": "new"}, "new")
    assert _read(chat_file) == "encrypted:new"


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_ciphertext_without_a_key_says_so() -> None:
    mixin = SecurityMixin.__new__(SecurityMixin)
    mixin.encryption_enabled = False
    with pytest.raises(ValueError, match="line 1 column 1.*no key is set"):
        mixin._decrypt_data("gAAAAciphertext")
