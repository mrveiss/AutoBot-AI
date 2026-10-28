# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The embedding switch cuts over only after a complete, zero-failure build (#19379)."""

from __future__ import annotations

import sys
import types

import pytest

from autobot_shared.coordination import work_claims
from autobot_shared.embedding_model import EmbeddingSpace
from knowledge import embedding_switch as sw
from knowledge import embedding_switch_lock as lock

pytestmark = pytest.mark.asyncio

MODEL = "bge-m3:latest"


class _Redis:
    def __init__(self):
        self.kv, self.hashes, self.sets, self.ttl = {}, {}, {}, {}

    async def get(self, key):
        return self.kv.get(key)

    async def set(self, key, value, nx=False, xx=False, ex=None):
        if (nx and key in self.kv) or (xx and key not in self.kv):
            return None
        self.kv[key] = value
        return True

    async def eval(self, script, numkeys, key, *args):
        """The Lua scripts the switch itself uses; the build claim lives in the work-claim registry."""
        if script == sw._CANCEL_IF_BUILDING_LUA:
            if self.hashes.get(key, {}).get("state") != "building":
                return 0
            self.hashes[key]["cancel"] = "1"
            return 1
        if script == sw._SETTLE_UNLESS_CANCELLED_LUA:
            if self.hashes.get(key, {}).get("cancel") == "1":
                return 0
            self.hashes.setdefault(key, {})["state"] = "settling"
            return 1
        raise AssertionError(f"unexpected script {script!r}")

    async def exists(self, key):
        return int(key in self.kv)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update(mapping)

    async def delete(self, *keys):
        for k in keys:
            for store in (self.kv, self.hashes, self.sets):
                store.pop(k, None)

    async def sadd(self, key, member):
        self.sets.setdefault(key, set()).add(member)

    async def spop(self, key):
        members = self.sets.get(key)
        return members.pop() if members else None

    async def scard(self, key):
        return len(self.sets.get(key, ()))


class _Claims:
    """The work-claim registry's four calls the switch uses, over one in-memory dict."""

    def __init__(self):
        self.held: dict = {}  # scope -> WorkClaim
        self.renewals: list = []

    def holder(self):
        claim = self.held.get(lock.SWITCH_SCOPE)
        return claim.agent_id if claim else None

    def hold(self, owner):
        self.held[lock.SWITCH_SCOPE] = work_claims.WorkClaim(
            lock.SWITCH_SCOPE, owner, lock.SWITCH_TASK_ID, "exclusive", "test", "t0", "t1"
        )

    async def try_acquire(self, scope, *, agent_id, task_id, intent, ttl_s=None, **_):
        current = self.held.get(scope)
        if current is not None and (current.agent_id, current.task_id) != (agent_id, task_id):
            return work_claims.ClaimConflict(requested=scope, holder=current)
        self.hold(agent_id)
        return self.held[scope]

    async def renew(self, scope, *, agent_id, task_id, ttl_s=None):
        current = self.held.get(scope)
        if current is None or (current.agent_id, current.task_id) != (agent_id, task_id):
            return False
        self.renewals.append(ttl_s)
        return True

    async def release_scope(self, scope, *, agent_id, task_id):
        current = self.held.get(scope)
        if current is None or (current.agent_id, current.task_id) != (agent_id, task_id):
            return False
        del self.held[scope]
        return True

    async def list_claims(self, kind=None):
        return list(self.held.values())


class _Collection:
    def __init__(self):
        self.ids: dict = {}

    def count(self):
        return len(self.ids)

    def delete(self, ids):
        for i in ids:
            self.ids.pop(i, None)


def _vector_store():
    """A LlamaIndex ChromaVectorStore stand-in: ``add(nodes)`` and the raw ``_collection``."""
    collection = _Collection()

    def add(nodes):
        for n in nodes:
            collection.ids[n.id_] = n

    return types.SimpleNamespace(add=add, _collection=collection)


def _async(fn):
    async def wrapper(*a, **kw):
        return fn(*a, **kw)

    return wrapper


async def _batches(facts, size):
    ids = list(facts)
    for i in range(0, len(ids), size):
        yield [{"fact_id": f, **facts[f]} for f in ids[i : i + size]]


@pytest.fixture
def env(monkeypatch):
    redis, store, log, audits, claims = _Redis(), _vector_store(), [], [], _Claims()
    facts = {f"f{i}": {"content": f"fact {i}", "metadata": {"k": i}} for i in range(5)}
    env = types.SimpleNamespace(
        redis=redis, store=store, log=log, facts=facts, fail=set(), audits=audits, claims=claims
    )
    env.walk = None  # facts the build's walk sees; defaults to all of them
    fake_fs = types.SimpleNamespace(
        count_facts=_async(lambda *a: len(facts)),
        load_fact=_async(lambda fid: facts.get(fid)),
        iter_facts=lambda batch_size: _batches(env.walk if env.walk is not None else facts, batch_size),
    )

    async def _open(kb, collection, model, dim):
        log.append(("open", collection, dim))
        return store

    async def _rebind(kb, space):
        log.append(("rebind", space.collection, space.generation))

    def _override(model, collection):
        log.append(("override", model, collection, store._collection.count()))
        return EmbeddingSpace(model, collection, 7)

    async def _embed_batch(texts, model_name=None):
        assert model_name == MODEL, "the rebuild embeds with the TARGET model, never the active one"
        return [None if t in env.fail else [0.1, 0.2] for t in texts]

    import knowledge
    import knowledge.embedding_space_binding as binding
    import services.npu_client as npu

    monkeypatch.setattr(sw, "_redis", _async(lambda: redis))
    for name in ("try_acquire", "renew", "release_scope", "list_claims"):
        monkeypatch.setattr(work_claims, name, getattr(claims, name))
    monkeypatch.setattr(sw, "_open_collection", _open)
    monkeypatch.setattr(sw, "set_embedding_model_override", _override)
    monkeypatch.setattr(sw, "SWITCH_BATCH_SIZE", 2)
    monkeypatch.setattr(sw, "_settle_seconds", lambda: 0.0)
    monkeypatch.setattr(sw, "active_embedding_model", lambda: "nomic-embed-text:latest")
    monkeypatch.setattr(sw, "_audit", lambda actor, phase, model, coll: audits.append((actor, phase, model)))
    monkeypatch.setattr(knowledge, "fact_store", fake_fs, raising=False)
    monkeypatch.setitem(sys.modules, "knowledge.fact_store", fake_fs)
    monkeypatch.setattr(binding, "rebind", _rebind)
    monkeypatch.setattr(npu, "generate_embeddings_batch_with_fallback", _embed_batch)
    return env


def _kb():
    return types.SimpleNamespace(chromadb_collection="autobot_memory", chromadb_path="/tmp", vector_store=None)


async def _run(env, run=None):
    """Drive one build the way start_switch does, but awaited."""
    run = run or sw._Run("owner-1", MODEL, "autobot_memory__bge_m3_latest__abcd1234", sw.time.monotonic())
    env.claims.hold(run.owner)
    await sw._set_state(
        state="building", owner=run.owner, model=MODEL, collection=run.collection, done=0, total=0, failed=0
    )
    await sw.run_switch(_kb(), run)
    return await sw.switch_status()


def _overrides(env):
    return [e for e in env.log if e[0] == "override"]


async def test_a_complete_build_cuts_over_after_every_fact_is_in(env):
    status = await _run(env)
    assert status["state"] == "completed" and status["done"] == 5
    assert _overrides(env) == [("override", MODEL, "autobot_memory__bge_m3_latest__abcd1234", 5)]
    assert ("rebind", "autobot_memory__bge_m3_latest__abcd1234", 7) in env.log
    assert env.claims.holder() is None, "a finished build releases its lock"


async def test_the_active_space_is_untouched_until_the_build_completes(env):
    seen, original = [], env.store.add

    def _add(nodes):
        seen.append(bool(_overrides(env)))
        original(nodes)

    env.store.add = _add
    await _run(env)
    assert seen and not any(seen), "the override was written while vectors were still being added"


async def test_one_failed_fact_blocks_the_cutover(env):
    env.fail.add("fact 3")
    status = await _run(env)
    assert status["state"] == "failed" and status["failed"] == 1 and status["failed_ids"] == ["f3"]
    assert "failed to embed" in status["reason"], "the operator is told it was a failure, not a count"
    assert not _overrides(env)


async def test_a_cancel_stops_before_cutover(env):
    await sw._set_state(cancel="1")
    status = await _run(env)
    assert status["state"] == "cancelled" and not _overrides(env)


async def test_writes_that_keep_arriving_are_replayed_until_the_counts_match(env):
    """code review on PR #19641: a write after the first replay must not fail the build."""
    env.walk = dict(env.facts)
    env.facts["late"] = {"content": "written during the build", "metadata": {}}
    await sw._set_state(state="building")
    await sw.note_write("late")
    env.facts.pop("f0")
    await sw.note_write("f0")  # deleted during the build
    status = await _run(env)
    assert status["state"] == "completed"
    assert "late" in env.store._collection.ids and "f0" not in env.store._collection.ids


async def test_counts_that_never_match_fail_after_the_replay_rounds(env, monkeypatch):
    monkeypatch.setattr(sw, "SWITCH_REPLAY_ROUNDS", 2)
    env.walk = dict(env.facts)
    env.facts["unnoted"] = {"content": "never embedded", "metadata": {}}  # counted, never noted
    status = await _run(env)
    assert status["state"] == "failed" and "6 facts" in status["reason"]
    assert not _overrides(env)


async def test_a_failure_after_the_record_is_written_reports_a_warning_not_a_failure(env, monkeypatch):
    import knowledge.embedding_space_binding as binding

    async def _boom(kb, space):
        raise RuntimeError("rebind blew up")

    monkeypatch.setattr(binding, "rebind", _boom)
    status = await _run(env)
    assert len(_overrides(env)) == 1
    assert status["state"] == "completed_with_warnings" and "rebind blew up" in status["reason"]


async def test_a_build_past_its_deadline_fails_without_switching(env, monkeypatch):
    monkeypatch.setattr(sw, "SWITCH_DEADLINE_S", 60.0)
    run = sw._Run("owner-1", MODEL, "autobot_memory__bge_m3_latest__abcd1234", sw.time.monotonic() - 120)
    status = await _run(env, run)
    assert status["state"] == "failed" and "deadline" in status["reason"]
    assert not _overrides(env)


async def test_a_build_whose_lock_expired_reads_stale_and_can_be_force_closed(env):
    await sw._set_state(state="building", model=MODEL, collection="c")  # no lock: the owner is gone
    assert (await sw.switch_status())["state"] == "stale"
    assert await sw.request_switch_cancel(actor="admin") == "force_closed"
    status = await sw.switch_status()
    assert status["state"] == "failed" and "force-closed" in status["reason"]
    assert ("admin", "switch_force_close", MODEL) in env.audits


async def test_a_running_build_holds_the_lock_so_a_second_start_is_refused(env, monkeypatch):
    monkeypatch.setattr(sw, "fire_and_forget", lambda coro, name: coro.close())
    first = await sw.start_switch(_kb(), MODEL, actor="admin")
    assert first["state"] == "building"
    with pytest.raises(sw.SwitchRefused, match="already running"):
        await sw.start_switch(_kb(), "mxbai-embed-large:latest", actor="admin")
    assert ("admin", "switch_start", MODEL) in env.audits


async def test_a_stale_build_does_not_block_a_new_start(env, monkeypatch):
    monkeypatch.setattr(sw, "fire_and_forget", lambda coro, name: coro.close())
    await sw._set_state(state="building", model="old", collection="c")  # stale: no lock
    assert (await sw.start_switch(_kb(), MODEL))["state"] == "building"


async def test_each_attempt_writes_a_new_collection(env, monkeypatch):
    """A→B→A must not reopen the abandoned A collection."""
    monkeypatch.setattr(sw, "fire_and_forget", lambda coro, name: coro.close())
    first = (await sw.start_switch(_kb(), MODEL))["collection"]
    env.claims.held.clear()
    second = (await sw.start_switch(_kb(), MODEL))["collection"]
    assert first != second and first.startswith("autobot_memory__bge_m3_latest__")


async def test_a_quarantined_or_private_fact_keeps_its_filter_fields(env):
    """The search filters read metadata.collection (quarantine) and the ownership fields."""
    env.facts["q"] = {
        "content": "research finding",
        "metadata": {"collection": "research_quarantine", "owner_id": "u1"},
    }
    await _run(env)
    meta = env.store._collection.ids["q"].metadata
    assert meta["collection"] == "research_quarantine" and meta["owner_id"] == "u1"


async def test_a_heartbeat_after_the_lock_was_retaken_fails_without_extending_it(env):
    """code review on PR #19641: the owner check and the TTL reset are one atomic step."""
    run = sw._Run("owner-1", MODEL, "c", sw.time.monotonic())
    env.claims.hold("owner-2")
    with pytest.raises(RuntimeError, match="lost its lock"):
        await sw._heartbeat(run)
    assert env.claims.holder() == "owner-2" and not env.claims.renewals


async def test_a_finished_build_leaves_a_newer_owners_lock_alone(env):
    env.claims.hold("owner-2")
    await sw._finish(sw._Run("owner-1", MODEL, "c", sw.time.monotonic()), "failed", reason="x")
    assert env.claims.holder() == "owner-2"


async def test_a_worker_that_lost_ownership_does_not_overwrite_a_newer_switchs_state(env):
    """code review on PR #19641 (Major): A's late failure must not mark B's running build failed."""
    env.claims.hold("owner-B")
    await sw._set_state(state="building", owner="owner-B", model=MODEL, collection="c")
    await sw._finish(sw._Run("owner-A", MODEL, "c", sw.time.monotonic()), "failed", reason="lost its lock")
    status = await sw.switch_status()
    assert status["state"] == "building" and status["owner"] == "owner-B"
    assert env.claims.holder() == "owner-B"


async def test_a_cancel_during_settling_is_refused_as_too_late(env):
    env.claims.hold("owner-1")
    await sw._set_state(state="settling", owner="owner-1", model=MODEL, collection="c")
    assert await sw.request_switch_cancel(actor="admin") == "too_late"
    assert (await sw.switch_status()).get("cancel") is None


async def test_a_cancel_accepted_during_convergence_stops_before_the_record_is_written(env, monkeypatch):
    real_converge = sw._converge

    async def _cancel_then_converge(store, run, failed_ids):
        await sw._set_state(cancel="1")  # accepted while state was still "building"
        return await real_converge(store, run, failed_ids)

    monkeypatch.setattr(sw, "_converge", _cancel_then_converge)
    status = await _run(env)
    assert status["state"] == "cancelled" and not _overrides(env)


async def test_a_start_without_a_knowledge_base_is_refused_before_the_lock(env):
    with pytest.raises(sw.SwitchRefused, match="not available"):
        await sw.start_switch(None, MODEL)
    assert env.claims.holder() is None


async def test_a_start_that_fails_after_the_lock_releases_it(env, monkeypatch):
    def _boom(coro, name):
        coro.close()
        raise RuntimeError("no event loop to schedule on")

    monkeypatch.setattr(sw, "fire_and_forget", _boom)
    with pytest.raises(RuntimeError):
        await sw.start_switch(_kb(), MODEL)
    assert env.claims.holder() is None, "a failed start must not block the next one"


async def test_a_long_replay_heartbeats(env, monkeypatch):
    beats = []
    real = sw._heartbeat

    async def _counting(run, **fields):
        beats.append(fields)
        await real(run, **fields)

    run = sw._Run("owner-1", MODEL, "c", sw.time.monotonic())
    env.claims.hold(run.owner)
    await sw._set_state(state="building", owner=run.owner)
    for fid in ("f0", "f1", "f2", "f3"):
        await sw.note_write(fid)
    monkeypatch.setattr(sw, "_heartbeat", _counting)
    await sw._replay_pending(env.store, run)
    assert len(beats) == 2, "one heartbeat per SWITCH_BATCH_SIZE (2) replayed facts"


async def test_the_kb_stays_on_its_old_collection_while_the_build_runs(env):
    """#19379 AC: search and writes use the old collection until cutover."""
    kb, seen, original = _kb(), [], env.store.add

    def _add(nodes):
        seen.append((kb.chromadb_collection, any(e[0] == "rebind" for e in env.log)))
        original(nodes)

    env.store.add = _add
    run = sw._Run("owner-1", MODEL, "autobot_memory__bge_m3_latest__abcd1234", sw.time.monotonic())
    env.claims.hold(run.owner)
    await sw._set_state(state="building", owner=run.owner, model=MODEL, collection=run.collection)
    await sw.run_switch(kb, run)
    assert seen and all(entry == ("autobot_memory", False) for entry in seen), seen


async def test_a_worker_whose_state_record_expired_still_releases_its_lock(env):
    """code review on PR #19641: the ownership early-return must not strand the lock."""
    env.claims.hold("owner-1")  # no state hash at all
    await sw._finish(sw._Run("owner-1", MODEL, "c", sw.time.monotonic()), "failed", reason="x")
    assert env.claims.holder() is None
    assert await sw.switch_status() == {"failed_ids": [], "state": "idle"}


async def test_cancel_and_cutover_cannot_both_win(env):
    """code review on PR #19641: the flag and the transition are one step each, so one side refuses."""
    env.claims.hold("owner-1")  # a live build, not a stale one
    await sw._set_state(state="building", owner="owner-1")
    assert await env.redis.eval(sw._SETTLE_UNLESS_CANCELLED_LUA, 1, sw.STATE_KEY) == 1
    assert await sw.request_switch_cancel(actor="admin") == "too_late"
    await sw._set_state(state="building", cancel="")
    assert await env.redis.eval(sw._CANCEL_IF_BUILDING_LUA, 1, sw.STATE_KEY) == 1
    assert await env.redis.eval(sw._SETTLE_UNLESS_CANCELLED_LUA, 1, sw.STATE_KEY) == 0


async def test_the_cancel_and_settle_scripts_on_a_real_lua_engine():
    import fakeredis

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await redis.hset("s", mapping={"state": "building"})
    assert await redis.eval(sw._CANCEL_IF_BUILDING_LUA, 1, "s") == 1
    assert await redis.eval(sw._SETTLE_UNLESS_CANCELLED_LUA, 1, "s") == 0, "an accepted cancel blocks cutover"
    assert await redis.hget("s", "state") == "building"
    await redis.hset("s", mapping={"cancel": ""})
    assert await redis.eval(sw._SETTLE_UNLESS_CANCELLED_LUA, 1, "s") == 1
    assert await redis.eval(sw._CANCEL_IF_BUILDING_LUA, 1, "s") == 0, "once settling, a cancel is refused"
    assert await redis.hget("s", "cancel") == ""


async def test_a_write_is_not_noted_when_no_switch_runs(env):
    await sw.note_write("f1")
    assert env.redis.sets == {}


@pytest.mark.parametrize(
    "model, message", [("phi3:mini", "not an embedding model"), ("nomic-embed-text:latest", "already the active")]
)
async def test_start_refuses(env, model, message):
    with pytest.raises(sw.SwitchRefused, match=message):
        await sw.start_switch(_kb(), model)


def test_the_target_collection_name_fits_chromadb():
    name = sw.target_collection("autobot_memory", "BAAI/bge-small-en-v1.5:latest", "0123456789abcdef")
    assert name == "autobot_memory__baai_bge_small_en_v1_5_lates__01234567"
    assert 3 <= len(name) <= 63 and name[0].isalnum() and name[-1].isalnum()
