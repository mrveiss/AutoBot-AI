# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A state record that vanished is never recreated ownerless by the switch's own writes (#20023)."""

from __future__ import annotations

import pytest

from knowledge import embedding_switch as sw
from knowledge import embedding_switch_test as shared

pytestmark = pytest.mark.asyncio

MODEL, _overrides, _run = shared.MODEL, shared._overrides, shared._run
env = shared.env  # the one fixture, reused so the fake Redis and claims are not copied


async def test_a_heartbeat_on_a_vanished_record_writes_nothing_and_fails_the_run(env):
    """#20023: the heartbeat used to HSET a vanished hash back as an ownerless record that read idle."""
    env.claims.hold("owner-1")
    run = sw._Run("owner-1", MODEL, "c", sw.time.monotonic())
    with pytest.raises(RuntimeError, match="lost its state record"):
        await sw._heartbeat(run, total=5, done=2, failed=1)
    assert sw.STATE_KEY not in env.redis.hashes, "an ownerless record was recreated"
    assert await sw.switch_status() == {"failed_ids": [], "state": "idle"}
    assert await sw.request_switch_cancel(actor="admin") == "none"
    await sw.note_write("f1")
    assert not env.redis.sets.get(sw.PENDING_KEY), "a write was noted against a record nobody owns"


async def test_a_heartbeat_with_a_foreign_owner_writes_nothing(env):
    env.claims.hold("owner-1")
    await sw._set_state(state="building", owner="owner-2", model=MODEL, collection="c")
    before = dict(env.redis.hashes[sw.STATE_KEY])
    with pytest.raises(RuntimeError, match="lost its state record"):
        await sw._heartbeat(sw._Run("owner-1", MODEL, "c", sw.time.monotonic()), done=9)
    assert env.redis.hashes[sw.STATE_KEY] == before, "a newer run's record was written by the old one"


async def test_a_heartbeat_with_the_matching_owner_records_progress(env):
    env.claims.hold("owner-1")
    await sw._set_state(state="building", owner="owner-1")
    await sw._heartbeat(sw._Run("owner-1", MODEL, "c", sw.time.monotonic()), done=3)
    record = env.redis.hashes[sw.STATE_KEY]
    assert record["owner"] == "owner-1" and record["done"] == "3" and "heartbeat" in record


async def test_a_build_whose_record_vanishes_mid_build_leaves_no_record_and_frees_the_claim(env, monkeypatch):
    real_converge = sw._converge

    async def _vanish_then_converge(store, run, failed_ids):
        env.redis.hashes.pop(sw.STATE_KEY)
        return await real_converge(store, run, failed_ids)

    monkeypatch.setattr(sw, "_converge", _vanish_then_converge)
    await _run(env)
    assert sw.STATE_KEY not in env.redis.hashes, "a heartbeat or finish recreated the vanished record"
    assert not _overrides(env) and env.claims.holder() is None


async def test_a_force_close_of_a_record_that_vanished_writes_nothing(env):
    env.claims.hold("owner-1")
    await sw._finish(None, "failed", reason="force-closed")
    assert sw.STATE_KEY not in env.redis.hashes
    assert env.claims.holder() is None


async def test_the_owner_guard_script_on_a_real_lua_engine():
    import fakeredis

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    assert await redis.eval(sw._SET_IF_OWNER_LUA, 1, "s", "me", "heartbeat", "t", "done", "4") == 0
    assert await redis.exists("s") == 0, "the vanished record came back"
    await redis.hset("s", mapping={"state": "building", "owner": "newer"})
    assert await redis.eval(sw._SET_IF_OWNER_LUA, 1, "s", "me", "state", "failed") == 0
    assert await redis.hgetall("s") == {"state": "building", "owner": "newer"}
    assert await redis.eval(sw._SET_IF_OWNER_LUA, 1, "s", "newer", "done", "4", "state", "settling") == 1
    assert await redis.hgetall("s") == {"state": "settling", "owner": "newer", "done": "4"}


async def test_the_force_close_script_reaches_an_ownerless_legacy_record_but_never_creates_one():
    import fakeredis

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    assert await redis.eval(sw._SET_IF_OWNER_LUA, 1, "s", "", "state", "failed") == 0
    assert await redis.exists("s") == 0
    await redis.hset("s", mapping={"state": "building", "heartbeat": "t"})  # left by the pre-#20023 heartbeat
    assert await redis.eval(sw._SET_IF_OWNER_LUA, 1, "s", "", "state", "failed") == 1
    assert await redis.hget("s", "state") == "failed"
