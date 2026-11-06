# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The admin delete-conversation route removes chat files through the locked delete (#20862)."""

import threading
from unittest.mock import MagicMock

import fakeredis.aioredis
import pytest
from fastapi import HTTPException

from api import data_storage
from chat_history import session_lease as lease_mod
from chat_history.file_io import FileIOMixin
from chat_history.security import SecurityMixin
from chat_history.session import SessionMixin

_HELD_FOR_MS = 60_000  # outlives the test wait


def _plant(path) -> None:
    path.write_text("log", encoding="utf-8")


class _Manager(SessionMixin, SecurityMixin, FileIOMixin):
    def __init__(self, directory: str):
        self._directory = directory
        self.redis_client = None
        self.encryption_enabled = False
        self.max_messages = 10000
        self.max_session_files = 1000
        self._counter_lock = threading.Lock()
        self._session_save_counter = 0
        self.memory_graph = None
        self.memory_graph_enabled = False

    def _get_chats_directory(self) -> str:
        return self._directory

    async def _init_memory_graph(self) -> None:
        return None

    async def _cleanup_old_session_files(self) -> None:
        return None


@pytest.fixture()
def route(tmp_path, monkeypatch):
    chats = tmp_path / "chats"
    chats.mkdir()
    manager = _Manager(str(chats))
    monkeypatch.setattr(data_storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_storage, "get_chat_history_manager", lambda request: manager)
    return chats, manager


async def test_the_route_deletes_the_chat_and_transcript_through_the_manager(route):
    chats, manager = route
    await manager.save_session("c1", messages=[{"sender": "user", "text": "hi", "timestamp": "t"}])
    _plant(chats / "c1_terminal_transcript.txt")
    result = await data_storage.delete_conversation("c1", MagicMock(), None)
    assert sorted(result["files_deleted"]) == ["c1_chat.json", "c1_terminal_transcript.txt"]
    assert not (chats / "c1_chat.json").exists()


async def test_the_route_waits_for_the_session_lease_and_does_not_delete_around_it(
    route, monkeypatch, fake_session_lease
):
    chats, manager = route
    await manager.save_session("c2", messages=[{"sender": "user", "text": "hi", "timestamp": "t"}])
    monkeypatch.setattr(lease_mod, "CHAT_LEASE_WAIT_S", 0.2)
    holder = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)
    await holder.set(lease_mod.CHAT_LEASE_KEY_PREFIX + "c2", "backend-2-1:save_session:aa", px=_HELD_FOR_MS)
    with pytest.raises(HTTPException) as err:  # the route's error boundary reports the lease timeout, not a delete
        await data_storage.delete_conversation("c2", MagicMock(), None)
    assert err.value.status_code == 500
    assert (chats / "c2_chat.json").exists()
