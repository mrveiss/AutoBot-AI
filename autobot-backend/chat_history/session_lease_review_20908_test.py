# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Review findings on the session lease (#20862, PR #20908), each pinned by a test that fails without its fix."""

import asyncio
import json

import pytest

from chat_history import session_lease as lease_mod
from chat_history.session_lease import (
    SessionLease,
    SessionLeaseError,
    SessionLeaseTimeout,
    StaleGenerationError,
    session_lease,
)
from chat_history.session_lease_20862_test import _Manager, _msg, _on_disk, _raw, _texts
from testkit.async_bounds import bound_async_tests

_REAL_LEASE_CLIENT = lease_mod._lease_client  # captured before the autouse fixture rebinds it
_HELD_FOR_MS = 60_000  # a holder that outlives the test
_NEWER = 10**6


@pytest.fixture()
def manager(tmp_path):
    return _Manager(str(tmp_path))


def _land_newer_write(tmp_path, session_id: str) -> None:
    """Another writer's newer-generation write, replacing the file outright."""
    newer = {"id": session_id, "messages": [_msg("newer writer content", "t9")], "write_generation": _NEWER}
    (tmp_path / f"{session_id}_chat.json").write_text(json.dumps(newer), encoding="utf-8")


async def test_an_unknown_lease_database_is_a_lease_error_not_a_bare_keyerror(monkeypatch):
    async def unknown(database):
        raise KeyError(database)

    monkeypatch.setattr(lease_mod, "get_async_redis_client", unknown)
    with pytest.raises(SessionLeaseError) as err:
        await _REAL_LEASE_CLIENT("nowhere")
    assert "nowhere" in str(err.value)


async def test_a_write_with_an_unknown_lease_database_is_raised_not_reported_as_false(manager, monkeypatch):
    async def unknown(database):
        raise SessionLeaseError("chat lease Redis database %r is not a known database" % database)

    monkeypatch.setattr(lease_mod, "_lease_client", unknown)
    with pytest.raises(SessionLeaseError):
        await manager._add_message_to_session("u1", _msg("hi", "t0"))


@pytest.mark.parametrize(
    ("name", "raw", "reader", "expected"),
    [
        ("AUTOBOT_CHAT_LEASE_WAIT_S", "0", lease_mod._seconds, 0.1),
        ("AUTOBOT_CHAT_LEASE_POLL_S", "-3", lease_mod._seconds, 0.001),
        ("AUTOBOT_CHAT_LEASE_WAIT_S", "soon", lease_mod._seconds, 30.0),
        ("AUTOBOT_CHAT_LEASE_TTL_MS", "5", lease_mod._ttl_ms, 1000),
        ("AUTOBOT_CHAT_LEASE_TTL_MS", "forever", lease_mod._ttl_ms, 30000),
    ],
)
def test_lease_settings_are_clamped_to_the_registered_range(monkeypatch, name, raw, reader, expected):
    monkeypatch.setenv(name, raw)
    assert (reader(name) if reader is lease_mod._seconds else reader()) == expected


async def test_a_generation_counter_key_can_never_be_another_sessions_lease_key():
    assert not lease_mod.CHAT_LEASE_GENERATION_PREFIX.startswith(lease_mod.CHAT_LEASE_KEY_PREFIX)
    assert not lease_mod.CHAT_LEASE_KEY_PREFIX.startswith(lease_mod.CHAT_LEASE_GENERATION_PREFIX)
    victim = SessionLease("a:generation", "op")  # ':' is a legal character in a session id here
    assert SessionLease("a", "op").generation_key != victim.key
    assert victim.generation_key != victim.key


async def test_a_child_task_does_not_silently_share_the_parents_lease(monkeypatch):
    monkeypatch.setattr(lease_mod, "CHAT_LEASE_WAIT_S", 0.3)

    async def child():
        async with session_lease("r1", "child"):
            pytest.fail("a child task was handed its parent's lease")

    async with session_lease("r1", "parent") as parent:
        async with session_lease("r1", "same-task") as again:
            assert again is parent  # still re-entrant inside the owning task
        with pytest.raises(SessionLeaseTimeout):
            await asyncio.create_task(child())


async def test_a_lost_lease_and_a_newer_file_refuses_the_replace_and_keeps_the_newer_content(
    manager, tmp_path, fake_session_lease
):
    import fakeredis.aioredis

    await manager.save_session("f1", messages=[_msg("first", "t0")])
    real_write = manager._atomic_write
    other = fakeredis.aioredis.FakeRedis(server=fake_session_lease, decode_responses=True)

    async def lose_lease_then_newer_writer_lands(file_path, content, before_replace=None):
        await other.set(lease_mod.CHAT_LEASE_KEY_PREFIX + "f1", "backend-9-1:save_session:ee", px=_HELD_FOR_MS)
        _land_newer_write(tmp_path, "f1")
        await real_write(file_path, content, before_replace)

    manager._atomic_write = lose_lease_then_newer_writer_lands
    with pytest.raises(SessionLeaseError):
        await manager.save_session("f1", messages=[_msg("first", "t0"), _msg("late", "t9")])
    assert _texts(tmp_path, "f1") == ["newer writer content"]
    assert _on_disk(tmp_path, "f1")["write_generation"] == _NEWER


async def test_a_newer_generation_landing_after_the_fence_is_refused_at_the_file(manager, tmp_path):
    await manager.save_session("f2", messages=[_msg("first", "t0")])
    real_write = manager._atomic_write

    async def newer_writer_lands(file_path, content, before_replace=None):
        _land_newer_write(tmp_path, "f2")  # after the fence passed, before our rename
        await real_write(file_path, content, before_replace)

    manager._atomic_write = newer_writer_lands
    with pytest.raises(StaleGenerationError) as err:
        await manager.save_session("f2", messages=[_msg("first", "t0"), _msg("late", "t9")])
    assert err.value.file_generation == _NEWER
    assert _texts(tmp_path, "f2") == ["newer writer content"]
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".tmp_chat_")]


async def test_a_file_rewritten_between_allocate_and_fence_is_rejected(manager, tmp_path, monkeypatch):
    await manager.save_session("f3", messages=[_msg("first", "t0")])
    real_begin = SessionLease.begin

    async def begin_then_rewrite(self, current_file_generation):
        await real_begin(self, current_file_generation)
        _land_newer_write(tmp_path, "f3")

    monkeypatch.setattr(SessionLease, "begin", begin_then_rewrite)
    before = None
    with pytest.raises(StaleGenerationError):
        await manager.save_session("f3", messages=[_msg("first", "t0"), _msg("late", "t9")])
    before = _raw(tmp_path, "f3")
    assert json.loads(before)["write_generation"] == _NEWER
    assert _texts(tmp_path, "f3") == ["newer writer content"]


async def test_concurrent_edits_to_different_keys_of_one_message_both_survive(manager, tmp_path):
    message = {**_msg("approve?", "t0"), "id": "m1", "metadata": {"tag": "x"}}
    await manager.save_session("m1s", messages=[message])
    results = await asyncio.gather(
        manager.update_message_metadata("m1s", {"tag": "x"}, {"approval_status": "approved"}),
        manager.update_message_metadata("m1s", {"tag": "x"}, {"approval_comment": "ok"}),
    )
    assert results == [True, True]
    stored = _on_disk(tmp_path, "m1s")["messages"][0]["metadata"]
    assert stored == {"tag": "x", "approval_status": "approved", "approval_comment": "ok"}


async def test_update_message_metadata_reports_false_for_a_missing_session_or_message(manager):
    assert await manager.update_message_metadata("absent", {"tag": "x"}, {"a": 1}) is False
    await manager.save_session("m2s", messages=[_msg("hi", "t0")])
    assert await manager.update_message_metadata("m2s", {"tag": "nope"}, {"a": 1}) is False


async def test_an_append_cleans_stored_duplicates_under_the_lease(manager, tmp_path):
    duplicate = [_msg("same words", "2026-01-01 10:00:00"), _msg("same words", "2026-01-01 10:00:05")]
    await manager.save_session("d1", messages=duplicate, replace=True)
    await manager._add_message_to_session("d1", _msg("next", "2026-01-01 10:05:00"))
    assert _texts(tmp_path, "d1") == ["same words", "next"]
    assert [m["text"] for m in await manager.load_session("d1")] == ["same words", "next"]


async def test_an_append_batch_carrying_one_id_twice_adds_it_once(manager, tmp_path):
    await manager.save_session("d2", messages=[_msg("first", "t0")])
    same = {**_msg("echo", "t1"), "id": "dup-1"}
    await manager.add_messages_batch("d2", [same, dict(same)])
    assert _texts(tmp_path, "d2") == ["first", "echo"]


bound_async_tests(globals())  # no pytest-timeout in the repo: bound each test here
