# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Second review round on the session lease (#20862, PR #20908), each finding pinned by a test."""

import asyncio
import fcntl
import json
import os

import fakeredis.aioredis
import pytest

from autobot_logging import terminal_logger as terminal_mod
from autobot_logging.terminal_logger import TerminalLogger
from autobot_shared.leader_lease import LeaderLease
from chat_history import file_io
from chat_history import session_lease as lease_mod
from chat_history.memory import MemoryMixin
from chat_history.session_lease import SessionLeaseError, SessionLeaseTimeout
from chat_history.session_lease_20862_test import _Manager, _msg, _on_disk, _plant, _raw, _texts
from chat_history.session_merge import dropped_keys, merge_snapshot
from testkit.async_bounds import bound_async_tests

_HELD_FOR_MS = 60_000  # a holder that outlives the test


@pytest.fixture()
def manager(tmp_path):
    return _Manager(str(tmp_path))


def _write(path, text: str = "{}") -> None:
    path.write_text(text, encoding="utf-8")


def _read_json(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _hold(fake_session_lease, session_id: str, holder: str = "backend-2-1:save_session:aa"):
    """Another worker's hold on *session_id*'s lease; returns the awaitable that sets it."""
    other = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)
    return other.set(lease_mod.CHAT_LEASE_KEY_PREFIX + session_id, holder, px=_HELD_FOR_MS)


# --- leader lease: a failing client factory ------------------------------------------------------------


async def test_a_client_factory_error_while_holding_is_no_answer_not_a_dead_heartbeat():
    failing = False

    async def factory(database):
        if failing:
            raise RuntimeError("factory down")
        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    lease = LeaderLease("k", database="main", client_factory=factory)
    assert await lease.hold_or_refresh() is True
    failing = True
    assert await lease.hold_or_refresh() is None  # no answer; leadership is left as it was
    assert lease.is_leader
    await lease.release()  # a factory error on release does not surface
    assert not lease.is_leader


async def test_a_client_factory_error_while_contesting_reaches_the_caller():
    async def factory(database):
        raise KeyError(database)

    with pytest.raises(KeyError):
        await LeaderLease("k", database="nowhere", client_factory=factory).hold_or_refresh()


# --- lease settings must be finite -----------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["inf", "nan", "-1", "0"])
def test_a_non_finite_or_non_positive_wait_falls_back_to_the_default(monkeypatch, raw):
    monkeypatch.setenv("AUTOBOT_CHAT_LEASE_WAIT_S", raw)
    monkeypatch.setenv("AUTOBOT_CHAT_LEASE_POLL_S", raw)
    assert lease_mod._seconds("AUTOBOT_CHAT_LEASE_WAIT_S") == 30.0
    assert lease_mod._seconds("AUTOBOT_CHAT_LEASE_POLL_S") == 0.05


# --- (a) a failed cleanup save is raised; it runs on the file as it is under the lease ----------------------


def _duplicated(tmp_path, session_id: str) -> None:
    twin = [_msg("same words", "2026-01-01 10:00:00"), _msg("same words", "2026-01-01 10:00:05")]
    _plant(tmp_path, session_id, json.dumps({"id": session_id, "messages": twin}))


async def test_a_cleanup_that_cannot_take_the_lease_is_raised_not_logged_away(
    manager, tmp_path, monkeypatch, fake_session_lease
):
    _duplicated(tmp_path, "c1")
    monkeypatch.setattr(lease_mod, "CHAT_LEASE_WAIT_S", 0.2)
    await _hold(fake_session_lease, "c1")
    with pytest.raises(SessionLeaseTimeout):
        await manager.load_session("c1")
    assert len(_on_disk(tmp_path, "c1")["messages"]) == 2  # untouched


async def test_a_cleanup_keeps_a_message_appended_after_the_load(manager, tmp_path):
    _duplicated(tmp_path, "c2")
    stale = await manager._load_session_from_file("c2")  # what load_session read before the append
    await manager._add_message_to_session("c2", _msg("appended later", "2026-01-01 10:09:00"))
    cleaned = await manager._process_loaded_messages("c2", stale)
    assert _texts(tmp_path, "c2") == ["same words", "appended later"]
    assert [m["text"] for m in cleaned] == ["same words", "appended later"]


# --- (b) the terminal chat stub goes through the one atomic writer and file lock ----------------------------


async def test_the_terminal_stub_is_written_atomically_under_the_session_file_lock(tmp_path, monkeypatch):
    seen = {}
    real_atomic = terminal_mod.atomic_write

    async def probing_check() -> None:
        fd = os.open(str(tmp_path / "t1_chat.json") + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            with pytest.raises(BlockingIOError):  # the writer is inside the session file lock
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)
        seen["file_before_replace"] = (tmp_path / "t1_chat.json").exists()

    async def spy(file_path, content, before_replace=None, **kwargs):
        async def both() -> None:
            await before_replace()  # the lease check
            await probing_check()

        await real_atomic(file_path, content, both, **kwargs)

    monkeypatch.setattr(terminal_mod, "atomic_write", spy)
    await TerminalLogger(data_dir=str(tmp_path))._ensure_chat_json_exists("t1")
    assert seen == {"file_before_replace": False}  # never visible half-written
    assert _read_json(tmp_path / "t1_chat.json")["chatId"] == "t1"
    assert json.loads(_raw(tmp_path, "t1"))["write_generation"] >= 1  # fenced like every other writer


async def test_a_failed_stub_write_leaves_no_chat_file(tmp_path, monkeypatch):
    def refuse(*_args):
        raise OSError("disk full")

    real_open = file_io.aiofiles.open

    def open_only_the_temp(path, *args, **kwargs):  # the in-place fallback hits the same full disk
        if not os.path.basename(path).startswith(".tmp_chat_"):
            raise OSError("disk full")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "replace", refuse)
    monkeypatch.setattr(file_io.aiofiles, "open", open_only_the_temp)
    with pytest.raises(OSError):
        await TerminalLogger(data_dir=str(tmp_path))._ensure_chat_json_exists("t2")
    assert not (tmp_path / "t2_chat.json").exists()
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".tmp_chat_")]


async def test_an_established_session_never_waits_for_the_lease_to_log_a_command(
    tmp_path, monkeypatch, fake_session_lease
):
    _plant(tmp_path, "t3", json.dumps({"chatId": "t3", "messages": []}))
    monkeypatch.setattr(lease_mod, "CHAT_LEASE_WAIT_S", 0.2)
    await _hold(fake_session_lease, "t3")
    entry = await TerminalLogger(data_dir=str(tmp_path)).log_command("t3", "ls", "AUTOBOT")
    assert entry["command"] == "ls"


# --- best-effort passes are bounded and retried -------------------------------------------------------------


class _Cleaner(MemoryMixin):
    def __init__(self, directory: str):
        self.max_session_files = 0
        self._directory = directory

    def _get_chats_directory(self) -> str:
        return self._directory


async def test_a_cleanup_pass_skips_a_busy_session_and_the_next_pass_takes_it(
    tmp_path, monkeypatch, fake_session_lease
):
    monkeypatch.setattr(lease_mod, "CHAT_LEASE_BEST_EFFORT_WAIT_S", 0.05)
    for name in ("a", "b", "c"):
        _write(tmp_path / f"chat_{name}.json")
    await _hold(fake_session_lease, "b")
    cleaner = _Cleaner(str(tmp_path))
    await cleaner._cleanup_old_session_files()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["chat_b.json"]  # busy one kept, not waited 30s for
    other = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)
    await other.delete(lease_mod.CHAT_LEASE_KEY_PREFIX + "b")
    await cleaner._cleanup_old_session_files()
    assert list(tmp_path.iterdir()) == []


async def test_a_pass_stops_waiting_once_its_budget_is_spent(monkeypatch):
    monkeypatch.setattr(lease_mod, "CHAT_LEASE_PASS_BUDGET_S", 0.05)
    budget = lease_mod.LeaseBudget()
    assert not budget.spent
    await asyncio.sleep(0.1)
    assert budget.spent and budget.wait_s() == 0.0


async def test_a_listing_skips_a_busy_orphan_quickly_and_recovers_it_next_time(
    manager, tmp_path, monkeypatch, fake_session_lease
):
    monkeypatch.setattr(lease_mod, "CHAT_LEASE_BEST_EFFORT_WAIT_S", 0.05)
    _write(tmp_path / "o1_terminal.log", "x")
    await _hold(fake_session_lease, "o1")
    sessions: list = []
    await manager._recover_orphaned_terminal_sessions(str(tmp_path), set(), sessions)
    assert sessions == [] and not (tmp_path / "o1_chat.json").exists()
    other = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)
    await other.delete(lease_mod.CHAT_LEASE_KEY_PREFIX + "o1")
    await manager._recover_orphaned_terminal_sessions(str(tmp_path), set(), sessions)
    assert [s["id"] for s in sessions] == ["o1"]


# --- messages and merging -----------------------------------------------------------------------------------


async def test_a_metadata_update_that_matches_nothing_writes_nothing(manager, tmp_path):
    await manager.save_session("n1", messages=[_msg("hi", "t0")])
    before = _raw(tmp_path, "n1")
    assert await manager.update_message_metadata("n1", {"tag": "nope"}, {"a": 1}) is False
    assert _raw(tmp_path, "n1") == before  # same bytes, same generation


def test_distinct_messages_with_one_id_are_each_kept_by_a_snapshot_save():
    first, second = {"id": "m", "text": "one"}, {"id": "m", "text": "two"}
    merged = merge_snapshot([first, second], [dict(first), dict(second)])
    assert [m["text"] for m in merged] == ["one", "two"]


async def test_an_imported_session_with_a_repeated_id_survives_a_snapshot_save(manager, tmp_path):
    twin = [
        {"id": "m", "sender": "user", "text": "one", "timestamp": "t0"},
        {"id": "m", "sender": "bot", "text": "two"},
    ]
    await manager.save_session("r1", messages=twin, replace=True)
    await manager.save_session("r1", messages=twin)
    assert _texts(tmp_path, "r1") == ["one", "two"]


async def test_a_save_drops_what_the_route_deduplicated_but_keeps_a_concurrent_addition(manager, tmp_path):
    stored = {"id": "a", "sender": "user", "text": "hello", "timestamp": "t0"}
    await manager.save_session("d1", messages=[stored])
    loaded = [stored]
    snapshot = [{"id": "b", "sender": "user", "text": "hello", "timestamp": "t1"}]  # same words, new id
    discard = dropped_keys(loaded, snapshot)
    await manager._add_message_to_session("d1", {"id": "z", "sender": "bot", "text": "meanwhile", "timestamp": "t2"})
    await manager.save_session("d1", messages=snapshot, discard=discard)
    assert sorted(m["id"] for m in _on_disk(tmp_path, "d1")["messages"]) == ["b", "z"]  # "a" was the duplicate of "b"


# --- data and descriptors ------------------------------------------------------------------------------------


async def test_the_delete_route_reports_a_file_the_manager_could_not_remove(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from api import data_storage

    chats = tmp_path / "chats"
    chats.mkdir()
    _write(chats / "x1_chat.json")

    class _Refusing:
        async def delete_session(self, session_id):
            return False

    monkeypatch.setattr(data_storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_storage, "get_chat_history_manager", lambda request: _Refusing())
    result = await data_storage.delete_conversation("x1", MagicMock(), None)
    assert result["success"] is False and result["errors"] == ["Error deleting chat file"]


def test_the_lease_error_hierarchy_is_unchanged():
    assert issubclass(SessionLeaseTimeout, SessionLeaseError)
    assert file_io.atomic_write.__name__ == "atomic_write"


bound_async_tests(globals())
