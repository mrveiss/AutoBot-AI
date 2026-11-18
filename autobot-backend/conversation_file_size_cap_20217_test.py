# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The per-file size cap answers with the same coded 413 on every route, and a failed dedupe keeps its bytes (#20217).

Real ``ConversationFileManager`` on real SQLite, reusing the fixtures of the quota store tests.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

import conversation_file_quota as quota
from api.conversation_files_owner_upload_20133_test import world  # noqa: F401 -- fixture
from api.conversation_files_real_manager_20225_test import (  # noqa: F401
    _SESSION,
    _as_admin,
    _rows,
    real,
)
from conversation_file_manager import ConversationFileManager

_API = "/api/conversation/" + _SESSION


def _code(response) -> str:
    assert response.status_code == 413, response.text
    return response.json()["detail"]["code"]


def test_create_and_generate_past_the_size_cap_answer_413_with_the_stable_code(real, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ConversationFileManager, "MAX_FILE_SIZE", 10)
    admin = _as_admin(real)
    created = admin.client.post(f"{_API}/files/create", json={"filename": "big.txt", "content": "x" * 11})
    generated = admin.client.post(f"{_API}/generate", json={"filename": "big2.txt", "content": "y" * 11})
    assert _code(created) == quota.FILE_TOO_LARGE
    assert _code(generated) == quota.FILE_TOO_LARGE
    assert created.json()["detail"]["max_bytes"] == 10
    assert _rows(real, "SELECT COUNT(*) FROM conversation_files") == [(0,)]


def test_the_manager_raises_the_coded_refusal_not_a_plain_value_error(real, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ConversationFileManager, "MAX_FILE_SIZE", 4)
    with pytest.raises(quota.UploadRefused) as caught:
        asyncio.run(real.real.add_file(_SESSION, b"12345", "f.txt", uploaded_by="dora"))
    assert caught.value.status_code == 413 and caught.value.detail["code"] == quota.FILE_TOO_LARGE


def test_a_failed_deduplicated_add_leaves_the_existing_files_bytes_in_place(real, monkeypatch):  # noqa: F811
    asyncio.run(real.real.add_file(_SESSION, b"k" * 5, "k.txt", uploaded_by="dora"))
    stored = [p for p in (real.tmp / "storage").rglob("*") if p.is_file()]
    monkeypatch.setattr(real.real, "_handle_deduplicated_file", AsyncMock(side_effect=RuntimeError("db down")))
    with pytest.raises(RuntimeError):
        asyncio.run(real.real.add_file(_SESSION, b"k" * 5, "k.txt", uploaded_by="dora"))
    assert stored and all(p.exists() for p in stored)
