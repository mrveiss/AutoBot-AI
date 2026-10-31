# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Renaming a session reads its file through the decrypt path (#19864)."""

from __future__ import annotations

import pytest

from chat_history.session import SessionMixin


class _Stub:
    @staticmethod
    def _decrypt_data(data: str) -> dict:
        assert data == "ciphertext"
        return {"name": "old"}


@pytest.fixture
def chat_file(tmp_path):
    path = tmp_path / "s_chat.json"
    path.write_text("ciphertext", encoding="utf-8")
    return str(path)


async def test_a_rename_reads_an_encrypted_chat(chat_file) -> None:
    updated = await SessionMixin._load_and_update_session_name(_Stub(), chat_file, "new")
    assert updated["name"] == "new"
