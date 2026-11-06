# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-session lease: owner writes and session saves no longer lose each other's changes (#20862).

Real session persistence on a pytest tmp_path, with the lease store bound to an in-memory Redis by
the autouse ``fake_session_lease`` fixture.
"""

import asyncio
import contextvars
import json
import threading
import time

import fakeredis.aioredis
import pytest

from chat_history import session_lease as lease_mod
from chat_history.file_io import FileIOMixin
from chat_history.messages import MessagesMixin
from chat_history.security import SecurityMixin
from chat_history.session import SessionMixin
from chat_history.session_lease import (
    ChatFileUnreadable,
    SessionLeaseTimeout,
    StaleGenerationError,
    session_lease,
)
from chat_history.session_listing import SessionListingMixin
from chat_history.session_merge import merge_snapshot
from testkit.async_bounds import bound_async_tests

_HELD_FOR_MS = 60_000  # a holder that outlives every test wait
_SHORT_HOLD_MS = 300  # a holder that finishes inside the wait bound


class _Manager(SessionMixin, SessionListingMixin, MessagesMixin, SecurityMixin, FileIOMixin):
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


def _plant(tmp_path, session_id: str, content: str) -> None:
    (tmp_path / f"{session_id}_chat.json").write_text(content, encoding="utf-8")


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


async def test_a_snapshot_sharing_no_message_does_not_replace_the_file(manager, tmp_path):
    await manager.save_session("s13", messages=[_msg("kept-1", "t0"), _msg("kept-2", "t1")])
    await manager.save_session("s13", messages=[_msg("stale-view", "t9")])
    assert sorted(_texts(tmp_path, "s13")) == ["kept-1", "kept-2", "stale-view"]


async def test_a_snapshot_merges_by_message_id_and_updates_in_place(manager, tmp_path):
    first = {"id": "a", "sender": "user", "text": "hello", "timestamp": "t0"}
    second = {"id": "b", "sender": "assistant", "text": "partial", "timestamp": "t1"}
    await manager.save_session("s14", messages=[first, second])
    await manager.save_session("s14", messages=[{**second, "text": "complete"}])
    assert _texts(tmp_path, "s14") == ["hello", "complete"]


async def test_an_empty_snapshot_does_not_wipe_a_session(manager, tmp_path):
    await manager.save_session("s15", messages=[_msg("keep", "t0")])
    await manager.save_session("s15", messages=[])
    assert _texts(tmp_path, "s15") == ["keep"]


async def test_replace_is_the_explicit_way_to_drop_messages(manager, tmp_path):
    await manager.save_session("s16", messages=[_msg("a", "t0"), _msg("b", "t1")])
    await manager.save_session("s16", messages=[_msg("a", "t0")], replace=True)
    assert _texts(tmp_path, "s16") == ["a"]


def test_combine_inserts_a_new_message_after_its_predecessor():
    a, b, c = {"id": "a"}, {"id": "b"}, {"id": "c"}
    assert merge_snapshot([a, c], [a, b]) == [a, b, c]


@pytest.mark.parametrize("damage", ["{not json", ""])
async def test_save_refuses_to_overwrite_an_unreadable_file(manager, tmp_path, damage):
    _plant(tmp_path, "s17", damage)
    with pytest.raises(ChatFileUnreadable) as err:
        await manager.save_session("s17", messages=[_msg("new", "t0")])
    assert "s17" in str(err.value)
    assert _raw(tmp_path, "s17") == damage


async def test_an_absent_file_is_an_empty_session_not_an_error(manager, tmp_path):
    await manager.save_session("s18", messages=[_msg("first", "t0")])
    assert _texts(tmp_path, "s18") == ["first"]


async def test_a_message_add_surfaces_an_unreadable_file(manager, tmp_path):
    _plant(tmp_path, "s19", "{broken")
    with pytest.raises(ChatFileUnreadable):
        await manager._add_message_to_session("s19", _msg("new", "t0"))
    assert _raw(tmp_path, "s19") == "{broken"


async def test_a_metadata_update_refuses_an_unreadable_file(manager, tmp_path):
    _plant(tmp_path, "s20", "{broken")
    with pytest.raises(ChatFileUnreadable):
        await manager.update_session_metadata("s20", {"owner": "bob"})
    assert _raw(tmp_path, "s20") == "{broken"


async def test_delete_waits_for_the_lease_holder(manager, tmp_path, fake_session_lease):
    await manager.save_session("s21", messages=[_msg("x", "t0")])
    other_worker = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)
    await other_worker.set(lease_mod.CHAT_LEASE_KEY_PREFIX + "s21", "backend-2-1:save_session:aa", px=_SHORT_HOLD_MS)
    assert await manager.delete_session("s21") is True
    assert not (tmp_path / "s21_chat.json").exists()


async def test_delete_leaves_the_file_when_the_wait_times_out(manager, tmp_path, monkeypatch, fake_session_lease):
    await manager.save_session("s22", messages=[_msg("x", "t0")])
    monkeypatch.setattr(lease_mod, "CHAT_LEASE_WAIT_S", 0.2)
    other_worker = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)
    await other_worker.set(lease_mod.CHAT_LEASE_KEY_PREFIX + "s22", "backend-2-1:save_session:aa", px=_HELD_FOR_MS)
    with pytest.raises(SessionLeaseTimeout):
        await manager.delete_session("s22")
    assert (tmp_path / "s22_chat.json").exists()


async def test_a_delete_with_a_stale_generation_removes_nothing(manager, tmp_path):
    await manager.save_session("s23", messages=[_msg("x", "t0")])
    calls = iter([0, 10**9])

    async def peek(*_args):
        return next(calls)

    manager._peek_generation = peek
    with pytest.raises(StaleGenerationError):
        await manager.delete_session("s23")
    assert (tmp_path / "s23_chat.json").exists()


async def test_a_delete_during_a_save_does_not_resurrect_the_session(manager, tmp_path):
    await manager.save_session("s24", messages=[_msg("x", "t0")])
    await asyncio.gather(
        manager.save_session("s24", messages=[_msg("x", "t0"), _msg("y", "t1")]),
        manager.delete_session("s24"),
    )
    exists = (tmp_path / "s24_chat.json").exists()
    assert not exists or _texts(tmp_path, "s24") == ["x", "y"]


async def test_a_lease_that_expires_mid_write_is_rejected_before_the_replace(manager, tmp_path, fake_session_lease):
    await manager.save_session("s30", messages=[_msg("first", "t0")])
    before = _raw(tmp_path, "s30")
    real_write = manager._atomic_write
    other_worker = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)

    async def expire_then_write(file_path, content, before_replace=None):
        await other_worker.delete(lease_mod.CHAT_LEASE_KEY_PREFIX + "s30")  # the TTL runs out mid-write
        await other_worker.set(lease_mod.CHAT_LEASE_KEY_PREFIX + "s30", "backend-9-1:save_session:ee", px=_HELD_FOR_MS)
        await real_write(file_path, content, before_replace)

    manager._atomic_write = expire_then_write
    with pytest.raises(lease_mod.SessionLeaseLost):
        await manager.save_session("s30", messages=[_msg("first", "t0"), _msg("late", "t9")])
    assert _raw(tmp_path, "s30") == before


async def test_a_lost_lease_stays_lost_and_is_logged(manager, fake_session_lease, caplog):
    other_worker = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)
    async with session_lease("s31", "op") as lease:
        await other_worker.delete(lease_mod.CHAT_LEASE_KEY_PREFIX + "s31")
        with pytest.raises(lease_mod.SessionLeaseLost):
            await lease.verify()
        with pytest.raises(lease_mod.SessionLeaseLost):  # not re-acquired by a later check
            await lease.verify()
    assert "Lost the lease on chat session s31" in caplog.text


async def test_the_whole_acquire_is_bounded_once_across_the_local_queue_and_redis(manager, monkeypatch):
    monkeypatch.setattr(lease_mod, "CHAT_LEASE_WAIT_S", 0.3)
    loop = asyncio.get_running_loop()

    async def second_writer():
        async with session_lease("s32", "second-writer"):
            pytest.fail("granted while the first writer held it")

    async with session_lease("s32", "first-writer"):
        started = loop.time()
        # a fresh context, as another request has: no inherited lease to re-enter
        task = loop.create_task(second_writer(), context=contextvars.Context())
        with pytest.raises(SessionLeaseTimeout) as err:
            await task
        assert loop.time() - started < 0.6
    assert "first-writer" in str(err.value)


async def test_identical_idless_messages_in_a_snapshot_are_both_kept(manager, tmp_path):
    twin = _msg("same", "t0")
    await manager.save_session("s33", messages=[twin, dict(twin)])
    await manager.save_session("s33", messages=[twin, dict(twin), _msg("next", "t1")])
    assert _texts(tmp_path, "s33") == ["same", "same", "next"]


async def test_an_append_of_a_message_already_stored_by_id_adds_nothing(manager, tmp_path):
    stored = {"id": "m1", "sender": "user", "text": "once", "timestamp": "t0"}
    await manager.save_session("s34", messages=[stored])
    await manager.save_session("s34", messages=[stored, _msg("fresh", "t1")], append=True)
    assert _texts(tmp_path, "s34") == ["once", "fresh"]


def test_merging_a_large_snapshot_is_linear():
    disk = [{"id": f"d{i}"} for i in range(10000)]
    snapshot = disk[::2] + [{"id": f"n{i}"} for i in range(2000)]
    start = time.perf_counter()
    merged = merge_snapshot(disk, snapshot)
    assert len(merged) == 12000
    assert time.perf_counter() - start < 2.0


async def test_the_orphan_import_does_not_truncate_a_file_a_save_created(manager, tmp_path):
    await manager.save_session("s35", messages=[_msg("real", "t0")])
    assert await manager._create_orphaned_session("s35", "s35_terminal.log", str(tmp_path)) is None
    assert _texts(tmp_path, "s35") == ["real"]


async def test_the_orphan_import_waits_for_the_lease_holder(manager, tmp_path, fake_session_lease):
    other_worker = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)
    await other_worker.set(lease_mod.CHAT_LEASE_KEY_PREFIX + "s36", "backend-2-1:save_session:aa", px=_SHORT_HOLD_MS)
    assert await manager._create_orphaned_session("s36", "s36_terminal.log", str(tmp_path)) is not None
    assert (tmp_path / "s36_chat.json").exists()


async def test_a_lease_timeout_is_raised_by_the_update_and_delete_methods_not_turned_into_false(
    manager, monkeypatch, fake_session_lease
):
    await manager.save_session("s37", messages=[_msg("x", "t0")])
    monkeypatch.setattr(lease_mod, "CHAT_LEASE_WAIT_S", 0.2)
    other_worker = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)
    await other_worker.set(lease_mod.CHAT_LEASE_KEY_PREFIX + "s37", "backend-2-1:save_session:aa", px=_HELD_FOR_MS)
    with pytest.raises(SessionLeaseTimeout):
        await manager.update_session_name("s37", "n")
    with pytest.raises(SessionLeaseTimeout):
        await manager.update_session_metadata("s37", {"owner": "bob"})
    with pytest.raises(SessionLeaseTimeout):
        await manager.delete_session("s37")


bound_async_tests(globals())  # no pytest-timeout in the repo: bound each test here
