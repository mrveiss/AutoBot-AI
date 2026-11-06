# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-session lease: owner writes and session saves no longer lose each other's changes (#20862).

Real session persistence on a pytest tmp_path, with the lease store bound to an in-memory Redis by
the autouse ``fake_session_lease`` fixture.
"""

import asyncio
import json
import threading

import fakeredis.aioredis
import pytest

from chat_history import session_lease as lease_mod
from chat_history.file_io import FileIOMixin
from chat_history.messages import MessagesMixin
from chat_history.security import SecurityMixin
from chat_history.session import SessionMixin
from chat_history.session_lease import (
    SessionLeaseTimeout,
    StaleGenerationError,
    session_lease,
)
from chat_history.session_merge import merge_concurrent_tail

_HELD_FOR_MS = 60_000  # a holder that outlives every test wait
_SHORT_HOLD_MS = 300  # a holder that finishes inside the wait bound


class _Manager(SessionMixin, MessagesMixin, SecurityMixin, FileIOMixin):
    """Minimal manager with real disk persistence."""

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
    return _Manager(str(tmp_path))


def _msg(text: str, stamp: str) -> dict:
    return {"sender": "user", "text": text, "timestamp": stamp}


def _on_disk(tmp_path, session_id: str) -> dict:
    return json.loads((tmp_path / f"{session_id}_chat.json").read_text(encoding="utf-8"))


def _raw(tmp_path, session_id: str) -> str:
    return (tmp_path / f"{session_id}_chat.json").read_text(encoding="utf-8")


def _rewrite_generation(tmp_path, session_id: str, generation: int) -> None:
    data = _on_disk(tmp_path, session_id)
    data["write_generation"] = generation
    (tmp_path / f"{session_id}_chat.json").write_text(json.dumps(data), encoding="utf-8")


def _texts(tmp_path, session_id: str) -> list:
    return [m["text"] for m in _on_disk(tmp_path, session_id)["messages"]]


async def test_two_concurrent_message_adds_keep_both(manager, tmp_path):
    await manager.save_session("s1", messages=[_msg("first", "t0")])
    await asyncio.gather(
        manager._add_message_to_session("s1", _msg("from-a", "t1")),
        manager._add_message_to_session("s1", _msg("from-b", "t2")),
    )
    assert sorted(_texts(tmp_path, "s1")) == ["first", "from-a", "from-b"]


async def test_two_concurrent_snapshot_saves_keep_both(manager, tmp_path):
    base = [_msg("first", "t0")]
    await manager.save_session("s2", messages=base)
    await asyncio.gather(
        manager.save_session("s2", messages=base + [_msg("from-a", "t1")]),
        manager.save_session("s2", messages=base + [_msg("from-b", "t2")]),
    )
    assert sorted(_texts(tmp_path, "s2")) == ["first", "from-a", "from-b"]


@pytest.mark.parametrize("round_", range(5))
async def test_owner_change_during_a_save_is_preserved(manager, tmp_path, round_):
    sid = f"s3-{round_}"
    await manager.save_session(sid, messages=[_msg("first", "t0")], metadata={"owner": "alice"})
    await asyncio.gather(
        manager.save_session(sid, messages=[_msg("first", "t0"), _msg("second", "t1")]),
        manager.update_session_metadata(sid, {"owner": "bob"}),
    )
    data = _on_disk(tmp_path, sid)
    assert data["metadata"]["owner"] == "bob"
    assert [m["text"] for m in data["messages"]] == ["first", "second"]


async def test_a_rename_during_a_save_keeps_both(manager, tmp_path):
    await manager.save_session("s4", messages=[_msg("first", "t0")], name="old")
    await asyncio.gather(
        manager._add_message_to_session("s4", _msg("second", "t1")),
        manager.update_session_name("s4", "new"),
    )
    data = _on_disk(tmp_path, "s4")
    assert data["name"] == "new"
    assert [m["text"] for m in data["messages"]] == ["first", "second"]


async def test_a_stale_generation_write_is_rejected(manager, tmp_path):
    await manager.save_session("s5", messages=[_msg("first", "t0")])
    before = _raw(tmp_path, "s5")

    async def newer_file(*_args):
        return 10**9

    manager._stored_generation = newer_file
    with pytest.raises(StaleGenerationError) as err:
        await manager.save_session("s5", messages=[_msg("late", "t9")])
    assert err.value.file_generation == 10**9
    assert _raw(tmp_path, "s5") == before


async def test_generations_grow_with_each_lease_and_are_written_to_the_file(manager, tmp_path):
    await manager.save_session("s6", messages=[_msg("a", "t0")])
    first = _on_disk(tmp_path, "s6")["write_generation"]
    await manager.save_session("s6", messages=[_msg("a", "t0"), _msg("b", "t1")])
    assert _on_disk(tmp_path, "s6")["write_generation"] > first


async def test_a_flushed_counter_restarts_above_the_files_generation(manager, tmp_path, fake_session_lease):
    await manager.save_session("s7", messages=[_msg("a", "t0")])
    _rewrite_generation(tmp_path, "s7", 500)
    await manager.save_session("s7", messages=[_msg("a", "t0"), _msg("b", "t1")])
    assert _on_disk(tmp_path, "s7")["write_generation"] > 500


async def test_the_bounded_wait_times_out_naming_the_holder(manager, tmp_path, monkeypatch, fake_session_lease):
    monkeypatch.setattr(lease_mod, "CHAT_LEASE_WAIT_S", 0.3)
    other_worker = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)
    await other_worker.set(
        lease_mod.CHAT_LEASE_KEY_PREFIX + "s8", "backend-2-4242:rename_session:ab12cd34", px=_HELD_FOR_MS
    )
    with pytest.raises(SessionLeaseTimeout) as err:
        async with session_lease("s8", "save_session"):
            pytest.fail("the lease was granted while another worker held it")
    assert "backend-2-4242:rename_session:ab12cd34" in str(err.value)
    assert err.value.holder == "backend-2-4242:rename_session:ab12cd34"


async def test_a_contended_writer_waits_for_the_holder_instead_of_failing(
    manager, tmp_path, monkeypatch, fake_session_lease
):
    other_worker = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)
    await other_worker.set(lease_mod.CHAT_LEASE_KEY_PREFIX + "s9", "backend-2-1:rename:aa", px=_SHORT_HOLD_MS)
    await manager.save_session("s9", messages=[_msg("after-wait", "t0")])
    assert _texts(tmp_path, "s9") == ["after-wait"]


async def test_save_session_raises_when_the_wait_times_out_and_writes_nothing(
    manager, tmp_path, monkeypatch, fake_session_lease
):
    monkeypatch.setattr(lease_mod, "CHAT_LEASE_WAIT_S", 0.2)
    other_worker = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)
    await other_worker.set(lease_mod.CHAT_LEASE_KEY_PREFIX + "s10", "backend-3-7:update_metadata:ff", px=_HELD_FOR_MS)
    with pytest.raises(SessionLeaseTimeout):
        await manager.save_session("s10", messages=[_msg("dropped?", "t0")])
    assert not (tmp_path / "s10_chat.json").exists()


async def test_the_lease_is_reentrant_within_one_task(manager):
    async with session_lease("s11", "outer") as outer:
        async with session_lease("s11", "inner") as inner:
            assert inner is outer


async def test_the_lease_is_released_after_the_block(manager, fake_session_lease):
    async with session_lease("s12", "op"):
        pass
    probe = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)
    assert await probe.get(lease_mod.CHAT_LEASE_KEY_PREFIX + "s12") is None


def test_merge_keeps_a_concurrent_tail_and_a_deliberate_replacement():
    a, b, c = _msg("a", "1"), _msg("b", "2"), _msg("c", "3")
    assert merge_concurrent_tail([a, b], [a, c]) == [a, c, b]
    assert merge_concurrent_tail([b], [c]) == [c]
    assert merge_concurrent_tail([], [c]) == [c]
