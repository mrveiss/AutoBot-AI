# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The admin delete-conversation route removes chat files through the locked delete (#20862)."""

import threading
from unittest.mock import MagicMock

import fakeredis.aioredis
import pytest

from api import data_storage
from chat_history import session_lease as lease_mod
from chat_history.file_io import FileIOMixin
from chat_history.security import SecurityMixin
from chat_history.session import SessionMixin
from chat_history.session_lease import SessionLeaseTimeout, StaleGenerationError
from testkit.async_bounds import bound_async_tests

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
    with pytest.raises(SessionLeaseTimeout) as err:  # re-raised for the app-wide 409 handler, holder named
        await data_storage.delete_conversation("c2", MagicMock(), None)
    assert err.value.holder == "backend-2-1:save_session:aa"
    assert (chats / "c2_chat.json").exists()


async def test_the_route_lets_a_stale_generation_reach_the_app_wide_handler(route, monkeypatch):
    chats, manager = route

    async def _stale(session_id, *args, **kwargs):
        raise StaleGenerationError(session_id, 1, 2)

    monkeypatch.setattr(manager, "delete_session", _stale)
    with pytest.raises(StaleGenerationError):
        await data_storage.delete_conversation("c3", MagicMock(), None)


def test_size_and_cleanup_walks_leave_the_session_lock_sidecars_alone(tmp_path):
    (tmp_path / "a_chat.json").write_text("12345", encoding="utf-8")
    (tmp_path / "a_chat.json.lock").write_text("", encoding="utf-8")
    assert data_storage.get_dir_size(tmp_path) == (5, 1)
    removed, _freed, _errors = data_storage._scan_and_remove_files(tmp_path, None, False)[:3]
    assert removed == 1 and (tmp_path / "a_chat.json.lock").exists()


bound_async_tests(globals())  # no pytest-timeout in the repo: bound each test here
