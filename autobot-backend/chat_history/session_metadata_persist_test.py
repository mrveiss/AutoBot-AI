# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for on-disk metadata persistence at session creation — Issue #12129.

Before the fix, ``create_session()`` built a session dict that included
``metadata`` for the return value / Memory Graph entity only. The actual
on-disk write went through ``save_session()``, whose signature had no
``metadata`` parameter, so ``metadata`` (including ``owner``) was never
written to the session file. ``get_session_owner()`` therefore always
returned ``None`` for freshly created sessions.

These tests prove:
- create_session(metadata=...) persists metadata to the session file.
- get_session_owner() can read the owner back immediately after creation.
- A later save_session() call WITHOUT metadata does not clobber
  previously persisted metadata (merge, not clobber).

Uses a lightweight stub manager (real SessionMixin/SecurityMixin/FileIOMixin,
real disk I/O against a pytest tmp_path) rather than the fully-configured
ChatHistoryManager, to avoid pulling in Redis/config subsystems.
"""

import json
import threading

import pytest

from chat_history.file_io import FileIOMixin
from chat_history.security import SecurityMixin
from chat_history.session import SessionMixin


class _StubManager(SessionMixin, SecurityMixin, FileIOMixin):
    """Minimal manager exercising real session persistence on real disk."""

    def __init__(self, chats_directory: str):
        self._chats_directory = chats_directory
        self.redis_client = None
        self.encryption_enabled = False
        self.max_messages = 10000
        self.max_session_files = 1000
        self._counter_lock = threading.Lock()
        self._session_save_counter = 0
        self.memory_graph = None
        self.memory_graph_enabled = False

    def _get_chats_directory(self) -> str:
        return self._chats_directory

    async def _init_memory_graph(self) -> None:
        return None

    async def _cleanup_old_session_files(self) -> None:
        return None


@pytest.fixture()
def manager(tmp_path):
    return _StubManager(str(tmp_path))


def _read_session_file(tmp_path, session_id):
    chat_file = tmp_path / f"{session_id}_chat.json"
    with open(chat_file, "r", encoding="utf-8") as f:
        return json.loads(f.read())


class TestCreateSessionPersistsMetadata:
    """create_session(metadata=...) must persist metadata to disk (#12129)."""

    @pytest.mark.asyncio
    async def test_metadata_written_to_session_file(self, manager, tmp_path):
        session_id = "sess-owner-persist"
        await manager.create_session(session_id=session_id, title="Test", metadata={"owner": "alice"})

        on_disk = _read_session_file(tmp_path, session_id)
        assert on_disk["metadata"]["owner"] == "alice"

    @pytest.mark.asyncio
    async def test_get_session_owner_reads_back_immediately(self, manager):
        session_id = "sess-owner-readback"
        await manager.create_session(session_id=session_id, title="Test", metadata={"owner": "alice"})

        owner = await manager.get_session_owner(session_id)
        assert owner == "alice"

    @pytest.mark.asyncio
    async def test_returned_dict_agrees_with_persisted_file(self, manager, tmp_path):
        session_id = "sess-owner-agree"
        returned = await manager.create_session(session_id=session_id, title="Test", metadata={"owner": "bob"})

        on_disk = _read_session_file(tmp_path, session_id)
        assert returned["metadata"]["owner"] == on_disk["metadata"]["owner"] == "bob"


class TestSaveSessionMergesNotClobbers:
    """A later save_session() without metadata must not wipe existing metadata (#12129)."""

    @pytest.mark.asyncio
    async def test_save_without_metadata_preserves_existing(self, manager, tmp_path):
        session_id = "sess-merge-not-clobber"
        await manager.create_session(session_id=session_id, title="Test", metadata={"owner": "alice"})

        # Subsequent save with new messages, no metadata argument.
        await manager.save_session(session_id, messages=[{"role": "user", "content": "hi"}])

        on_disk = _read_session_file(tmp_path, session_id)
        assert on_disk["metadata"]["owner"] == "alice"
        assert on_disk["messages"] == [{"role": "user", "content": "hi"}]

    @pytest.mark.asyncio
    async def test_save_with_new_metadata_merges_with_existing(self, manager, tmp_path):
        session_id = "sess-merge-additional"
        await manager.create_session(session_id=session_id, title="Test", metadata={"owner": "alice"})

        await manager.save_session(session_id, messages=[], metadata={"team_id": "team-1"})

        on_disk = _read_session_file(tmp_path, session_id)
        assert on_disk["metadata"]["owner"] == "alice"
        assert on_disk["metadata"]["team_id"] == "team-1"
