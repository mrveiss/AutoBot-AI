# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The knowledge wipe deletes only knowledge data, exactly what was approved, behind a durable entry (#21048, #17038).

Fakes only: no real Redis, Chroma or database is touched. The fakes and the plan are the ones in
``kb_wipe_action_21048_test``; this module adds a foreign index with its documents and foreign keys, and a shared
call log so the ORDER of paper trail and deletes is asserted, not assumed.
"""

import copy
import types
import uuid
from unittest.mock import AsyncMock

import pytest

from services import kb_wipe_action as action
from services import kb_wipe_chroma as chroma_mod
from services import kb_wipe_redis as redis_mod
from services.approval_execution import set_verified_decider, verified_decider
from services.kb_wipe_action_21048_test import (  # noqa: F401  (kb_index is an autouse fixture)
    KEPT,
    PLAN,
    WIPED,
    FakeChroma,
    FakeCollection,
    FakeRedis,
    _approval,
    _knowledge_data,
    _session,
    kb_index,
)

#: An index and documents that belong to another component: RediSearch lists them from every connection.
FOREIGN_INDEX = "idx:agent_memory"
FOREIGN_DOC = "agent_memory:doc:1"
FOREIGN_KEY = "pg:node:1"
KB_DOC = "llama_index/vector_1"


class LoggedRedis(FakeRedis):
    """Records every delete into the shared *log*; ``FT.DROPINDEX ... DD`` removes the index's own documents."""

    owned = {"llama_index": "llama_index/", FOREIGN_INDEX: "agent_memory:", "custom_kb_idx": "custom/"}

    def __init__(self, log, data, indexes):
        super().__init__(data, indexes)
        self.log = log

    def execute_command(self, *args):
        if args[0] == "FT.DROPINDEX":
            self.log.append(("redis", "dropindex", args[1]))
            if "DD" in args[2:]:
                for key in [k for k in self.data if k.startswith(self.owned[args[1]])]:
                    del self.data[key]
        return super().execute_command(*args)

    def unlink(self, *keys):
        self.log.append(("redis", "unlink"))
        return super().unlink(*keys)


class LoggedCollection(FakeCollection):
    def __init__(self, ids, log):
        super().__init__(ids)
        self.log = log

    async def delete(self, ids):
        self.log.append(("chroma", "delete"))
        await super().delete(ids)


@pytest.fixture
def world(monkeypatch):
    log: list[tuple] = []
    data = {**_knowledge_data(), KB_DOC: "x", FOREIGN_DOC: "x", FOREIGN_KEY: "x"}
    redis = LoggedRedis(log, data, {"llama_index": 12, FOREIGN_INDEX: 40})
    chroma = FakeChroma()
    chroma.cols = {
        "autobot_memory": LoggedCollection(range(7), log),
        "space_b": LoggedCollection(range(5), log),
        "co": FakeCollection(range(4)),
    }

    async def chroma_factory():
        log.append(("chroma", "client"))
        return chroma

    def factory(database):
        return {"knowledge": redis}[database]  # any other database name is a KeyError: it must never be asked for

    audit = AsyncMock(side_effect=lambda *a, **k: log.append(("audit", k["result"])) or True)
    real = redis_mod.execute_redis
    monkeypatch.setattr(chroma_mod, "default_chroma_client", chroma_factory)
    monkeypatch.setattr(chroma_mod, "CLEAR_BATCH", 3)
    monkeypatch.setattr(action, "kb_collection_names", lambda: ["autobot_memory", "space_b"])
    monkeypatch.setattr(action, "audit_log", audit)
    monkeypatch.setattr(action, "execute_redis", lambda record, scope, stop=None: real(record, scope, factory, stop))
    return types.SimpleNamespace(log=log, redis=redis, chroma=chroma, audit=audit, factory=factory)


async def _planned(world) -> dict:
    """The plan an approver sees. Planning is read only; its reads are then cleared so later asserts see the wipe."""
    plan = await action.plan_kb_wipe(world.factory)
    world.log.clear()
    world.redis.commands.clear()
    return plan


def _ready(plan, **kwargs):
    approval = _approval(plan=plan, **kwargs)
    set_verified_decider(approval, uuid.uuid4())
    return approval


def _snapshot(world):
    return dict(world.redis.data), dict(world.redis.indexes), list(world.chroma.cols["autobot_memory"].ids)


# -- scope: the KB's own index and keys, nothing else --------------------------------------------------------


@pytest.mark.asyncio
async def test_the_plan_names_only_kb_objects_and_the_wipe_leaves_a_foreign_index_and_its_documents(world):
    plan = await _planned(world)
    store = plan["databases"][0]
    assert store["indexes"] == [{"name": "llama_index", "documents": 12}]
    assert store["keys"] == len(WIPED)  # the foreign keys are not counted
    assert FOREIGN_INDEX not in str(plan) and FOREIGN_DOC not in str(plan) and FOREIGN_KEY not in str(plan)

    await action.execute_kb_wipe_action(_ready(plan), _session())

    assert world.redis.indexes == {FOREIGN_INDEX: 40}  # the KB index is gone, the foreign one is not
    assert FOREIGN_DOC in world.redis.data and FOREIGN_KEY in world.redis.data  # its documents and keys survive
    assert KB_DOC not in world.redis.data  # the KB index's own documents went with it
    assert set(world.redis.data) == set(KEPT) | {FOREIGN_DOC, FOREIGN_KEY}
    assert not any(c[:2] == ("FT.DROPINDEX", FOREIGN_INDEX) for c in world.redis.commands)


@pytest.mark.asyncio
async def test_the_scope_follows_the_configured_index_name_not_a_literal(world, monkeypatch):
    monkeypatch.setattr(redis_mod, "kb_index_names", lambda: ("custom_kb_idx",))
    world.redis.indexes["custom_kb_idx"] = 3
    world.redis.data["custom/doc"] = "x"
    plan = await _planned(world)
    assert [i["name"] for i in plan["databases"][0]["indexes"]] == ["custom_kb_idx"]

    await action.execute_kb_wipe_action(_ready(plan), _session())

    assert set(world.redis.indexes) == {"llama_index", FOREIGN_INDEX}  # neither is the configured KB index now
    assert "custom/doc" not in world.redis.data and KB_DOC in world.redis.data


@pytest.mark.asyncio
async def test_an_index_that_vanished_since_the_plan_is_recorded_absent_and_nothing_else_is_dropped(world):
    plan = await _planned(world)
    world.redis.indexes.pop("llama_index")

    await action.execute_kb_wipe_action(_ready(plan), _session())

    first = world.audit.await_args.kwargs["details"]["redis"][0]
    assert first == {
        "database": "knowledge",
        "kind": "index",
        "name": "llama_index",
        "count": 0,
        "complete": True,
        "absent": True,
    }
    assert not any(c[0] == "FT.DROPINDEX" for c in world.redis.commands)
    assert world.redis.indexes == {FOREIGN_INDEX: 40}


def _tampered(kind):
    plan = copy.deepcopy(PLAN)
    store = plan["databases"][0]
    if kind == "foreign_index":
        store["indexes"].append({"name": FOREIGN_INDEX, "documents": 1})
    elif kind == "foreign_prefix":
        store["prefixes"].append({"prefix": "pg:", "keys": 1})
    elif kind == "foreign_database":
        store["database"] = "main"
    elif kind == "foreign_collection":
        plan["chroma_collections"].append({"name": "co", "vectors": 4})
    elif kind == "no_plan":
        return None
    elif kind == "malformed":
        return {"databases": "not a list of databases"}
    return plan


@pytest.mark.parametrize(
    "kind", ["foreign_index", "foreign_prefix", "foreign_database", "foreign_collection", "no_plan", "malformed"]
)
@pytest.mark.asyncio
async def test_a_plan_that_exceeds_the_kb_scope_is_refused_before_any_entry_or_delete(world, kind):
    before = _snapshot(world)
    with pytest.raises(ValueError):
        await action.execute_kb_wipe_action(_ready(_tampered(kind)), _session())
    assert world.log == [] and world.redis.commands == []  # no audit entry, no store call of any kind
    assert _snapshot(world) == before


@pytest.mark.asyncio
async def test_the_executor_refuses_an_approval_that_is_not_an_approved_wipe(world):
    plan = await _planned(world)
    pending = _ready(plan, status="pending")
    other = _ready(plan)
    other.context = {**other.context, "action": "something_else"}
    for approval in (pending, other):
        with pytest.raises(ValueError, match="not an approved"):
            await action.execute_kb_wipe_action(approval, _session())
    assert world.log == [] and world.redis.commands == []


# -- paper trail: the entry before the first delete ---------------------------------------------------------


@pytest.mark.asyncio
async def test_the_intent_entry_is_committed_before_the_first_delete_and_the_outcome_after_the_last(world):
    approval = _ready(await _planned(world))

    await action.execute_kb_wipe_action(approval, _session())

    assert world.log[0] == ("audit", "attempted") and world.log[-1] == ("audit", "success")
    middle = world.log[1:-1]
    assert middle and {entry[0] for entry in middle} <= {"redis", "chroma"}  # no entry between the deletes
    assert ("redis", "dropindex", "llama_index") in middle and ("chroma", "delete") in middle
    intent = world.audit.await_args_list[0].kwargs
    details = intent["details"]
    assert intent["durable"] is True and details["phase"] == "intent"
    assert details["approval_id"] == str(approval.id) and details["proposed_by"] == "kb-wipe:operator"
    assert details["approved_by"] == "alice" and details["approver_id"] == str(verified_decider(approval))
    assert details["scope"]["collections"] == ["autobot_memory", "space_b"]
    assert [e["indexes"] for e in details["scope"]["redis"]] == [["llama_index"]]


@pytest.mark.parametrize("failure", ["not_written", "raises"])
@pytest.mark.asyncio
async def test_when_the_intent_entry_cannot_be_committed_nothing_is_deleted(world, failure):
    approval = _ready(await _planned(world))
    before = _snapshot(world)

    def intent(*args, **kwargs):
        world.log.append(("audit", kwargs["result"]))
        if failure == "raises":
            raise ConnectionError("audit store down")
        return False

    world.audit.side_effect = intent
    with pytest.raises((RuntimeError, ConnectionError)):
        await action.execute_kb_wipe_action(approval, _session())

    assert world.log == [("audit", "attempted")]  # the attempt to write the entry, then nothing: no store was touched
    assert world.redis.commands == [] and _snapshot(world) == before


@pytest.mark.asyncio
async def test_a_crash_mid_wipe_leaves_the_started_entry_and_a_failed_outcome_at_the_step_reached(world):
    world.redis.fail_unlink_on = "tag:"
    approval = _ready(await _planned(world))

    with pytest.raises(ConnectionError, match="lost"):
        await action.execute_kb_wipe_action(approval, _session())

    assert world.log[0] == ("audit", "attempted") and world.log[-1] == ("audit", "failed")
    assert ("audit", "success") not in world.log
    details = world.audit.await_args.kwargs["details"]
    last = details["redis"][-1]
    assert details["phase"] == "failure" and details["step"] == "redis" and details["error"] == "ConnectionError"
    assert (last["name"], last["complete"]) == ("tag:", False)
    assert details["steps_started"] == len(details["redis"]) and details["chroma"] == []


# -- the failure entry never masks the error ------------------------------------------------------------------


def _fail_the_failure_entry(world, how):
    def audit(*args, **kwargs):
        if kwargs["result"] == "attempted":
            return True
        if how == "raises":
            raise RuntimeError("audit store down")
        return how == "written"

    world.audit.side_effect = audit


@pytest.mark.parametrize(("how", "reason"), [("not_written", "returned False"), ("raises", "RuntimeError")])
@pytest.mark.asyncio
async def test_a_lost_failure_entry_is_logged_with_the_approval_id_and_never_replaces_the_original_error(
    world, caplog, how, reason
):
    world.redis.fail_unlink_on = "tag:"
    approval = _ready(await _planned(world))
    _fail_the_failure_entry(world, how)

    with caplog.at_level("ERROR", logger=action.logger.name):
        with pytest.raises(ConnectionError, match="lost"):  # the wipe's own error, not the audit's
            await action.execute_kb_wipe_action(approval, _session())

    errors = [r.getMessage() for r in caplog.records if r.name == action.logger.name and r.levelname == "ERROR"]
    assert len(errors) == 1 and str(approval.id) in errors[0] and reason in errors[0]
    assert "audit store down" not in errors[0]  # the type only, never the message or any content


@pytest.mark.asyncio
async def test_a_written_failure_entry_logs_nothing(world, caplog):
    world.redis.fail_unlink_on = "tag:"
    approval = _ready(await _planned(world))
    _fail_the_failure_entry(world, "written")

    with caplog.at_level("ERROR", logger=action.logger.name):
        with pytest.raises(ConnectionError, match="lost"):
            await action.execute_kb_wipe_action(approval, _session())

    assert [r for r in caplog.records if r.name == action.logger.name and r.levelname == "ERROR"] == []
