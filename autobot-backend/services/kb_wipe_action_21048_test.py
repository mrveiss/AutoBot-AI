# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The knowledge wipe is gated, knowledge-only, previewable, honestly audited and four-eyed (#21048, #17038).

Fakes only: no real Redis, Chroma or database is touched.
"""

import types
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared.approval_four_eyes import FourEyesError
from services import kb_wipe_action as action
from services import kb_wipe_chroma as chroma_mod
from services import kb_wipe_redis as redis_mod
from services.approval_execution import _ADMIN_ONLY, _DECISION_REVIEWS, _REGISTRY, _SERVER_ONLY, set_verified_decider

OVERRIDE_KEY = "autobot:kb:embedding_model"


class FakeRedis:
    """One Redis database. It has no ``flushdb``: calling it is an AttributeError, so a flush fails a test."""

    def __init__(self, data: dict, indexes: dict[str, int], fail_unlink_on: str | None = None):
        self.data, self.indexes, self.commands, self.fail_unlink_on = dict(data), dict(indexes), [], fail_unlink_on

    def execute_command(self, *args):
        self.commands.append(args)
        if args[0] == "FT._LIST":
            return list(self.indexes)
        if args[0] == "FT.INFO":
            return ["index_name", args[1], "num_docs", str(self.indexes[args[1]])]
        if args[0] == "FT.DROPINDEX":
            self.indexes.pop(args[1])
        return "OK"

    def scan_iter(self, match, count=None):
        prefix = match.rstrip("*")
        return iter([k for k in list(self.data) if k.startswith(prefix)])

    def unlink(self, *keys):
        if self.fail_unlink_on and any(k.startswith(self.fail_unlink_on) for k in keys):
            raise ConnectionError("lost")
        for key in keys:
            self.data.pop(key, None)
        return len(keys)


class FakeCollection:
    def __init__(self, ids):
        self.ids = list(ids)

    async def count(self):
        return len(self.ids)

    async def get(self, include=None, limit=None):
        return {"ids": self.ids[:limit]}

    async def delete(self, ids):
        self.ids = [i for i in self.ids if i not in ids]


class FakeChroma:
    """The KB collection, the switched space's collection and a sibling that must survive."""

    def __init__(self, fail: bool = False):
        self.cols = {
            "autobot_memory": FakeCollection(range(7)),
            "space_b": FakeCollection(range(5)),
            "co": FakeCollection(range(4)),
        }
        self.fail = fail

    async def get_collection_or_none(self, name):
        if self.fail:
            raise ConnectionError("chroma down")
        return self.cols.get(name)


def _knowledge_data():
    return {"fact:1": "x", "fact:2": "x", "kb:stats": "x", "tag:a": "x", "category:root": "x", OVERRIDE_KEY: "model-b"}


@pytest.fixture
def fleet():
    return {
        "knowledge": FakeRedis(_knowledge_data(), {"llama_index": 12}),
        "sessions": FakeRedis({"session:1": "x"}, {"session_idx": 3}),
        "settings": FakeRedis({"setting:a": "x"}, {}),
        "celery_broker": FakeRedis({"queue:1": "x"}, {}),
    }


@pytest.fixture
def chroma(monkeypatch):
    client = FakeChroma()
    monkeypatch.setattr(chroma_mod, "kb_collection_names", lambda: ["autobot_memory", "space_b"])

    async def factory():
        return client

    monkeypatch.setattr(chroma_mod, "default_chroma_client", factory)
    monkeypatch.setattr(action, "kb_collection_names", chroma_mod.kb_collection_names)
    monkeypatch.setattr(chroma_mod, "CLEAR_BATCH", 3)
    return client


def _factory(fleet):
    return lambda database: fleet[database]


@pytest.mark.asyncio
async def test_plan_lists_indexes_prefixes_and_collections_with_counts_and_deletes_nothing(fleet, chroma):
    plan = await action.plan_kb_wipe(_factory(fleet), chroma_mod.default_chroma_client)
    store = plan["databases"][0]
    assert store["indexes"] == [{"name": "llama_index", "documents": 12}]
    assert {p["prefix"]: p["keys"] for p in store["prefixes"]} == {
        "fact:": 2,
        "kb:": 1,
        "tag:": 1,
        "tag_style:": 0,
        "category:": 1,
        "collection:": 0,
    }
    assert plan["chroma_collections"] == [{"name": "autobot_memory", "vectors": 7}, {"name": "space_b", "vectors": 5}]
    assert (plan["total_keys"], plan["total_vectors"]) == (5, 12)
    assert fleet["knowledge"].commands.count(("FT.DROPINDEX", "llama_index", "DD")) == 0
    assert set(fleet["knowledge"].data) == set(_knowledge_data())


def test_wipe_removes_kb_prefixes_and_keeps_the_embedding_override_and_every_other_database(fleet):
    record: list[dict] = []
    redis_mod.execute_redis(record, _factory(fleet))
    assert set(fleet["knowledge"].data) == {OVERRIDE_KEY}  # the user's embedding-model choice survives
    assert fleet["knowledge"].indexes == {}
    assert {(s["kind"], s["name"]): s["count"] for s in record}[("prefix", "fact:")] == 2
    for survivor, keys in (("sessions", 1), ("settings", 1), ("celery_broker", 1)):
        assert fleet[survivor].commands == [] and len(fleet[survivor].data) == keys
    assert fleet["sessions"].indexes == {"session_idx": 3}


def test_scope_is_knowledge_only_and_has_no_full_wipe_option():
    assert redis_mod.KB_WIPE_DATABASES == ("knowledge",)
    assert not any(n in redis_mod.KB_WIPE_DATABASES for n in ("sessions", "main", "logs", "vectors", "agents"))
    assert OVERRIDE_KEY not in redis_mod.KB_KEY_PREFIXES and not any(
        OVERRIDE_KEY.startswith(p) for p in redis_mod.KB_KEY_PREFIXES
    )


@pytest.mark.asyncio
async def test_chroma_clear_empties_only_the_named_collections_and_marks_each_complete(chroma):
    record: list[dict] = []
    await chroma_mod.clear_chroma(["autobot_memory", "space_b"], record, chroma_mod.default_chroma_client)
    assert record == [
        {"name": "autobot_memory", "vectors": 7, "complete": True},
        {"name": "space_b", "vectors": 5, "complete": True},
    ]
    assert len(chroma.cols["co"].ids) == 4


@pytest.mark.asyncio
async def test_an_unavailable_database_refuses_instead_of_pretending(chroma):
    with pytest.raises(RuntimeError):
        await action.plan_kb_wipe(lambda database: None, chroma_mod.default_chroma_client)


def test_registration_is_server_only_admin_only_reviewed_and_proposed_in_this_module():
    action.register_kb_wipe_action()
    assert action.ACTION in _REGISTRY and action.ACTION in _SERVER_ONLY and action.ACTION in _ADMIN_ONLY
    assert _DECISION_REVIEWS[action.ACTION] is action._review_kb_wipe


def _approval(requester=None):
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        decided_by_user="alice",
        decided_at=datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc),
        requested_by_agent=f"kb-wipe:{requester}" if requester else "kb-wipe:operator",
        context={"action": action.ACTION},
    )


def _session(order=None):
    session = MagicMock()
    session.commit = AsyncMock(side_effect=lambda: order.append("commit") if order is not None else None)
    return session


def _wire(monkeypatch, fleet, order=None):
    audit = AsyncMock(side_effect=lambda *a, **k: (order.append("audit") if order is not None else None) or True)
    monkeypatch.setattr(action, "audit_log", audit)
    real = redis_mod.execute_redis
    monkeypatch.setattr(action, "execute_redis", lambda record: real(record, _factory(fleet)))
    return audit


@pytest.mark.asyncio
async def test_approved_wipe_audits_durably_before_the_commit_with_the_verified_decider(monkeypatch, fleet, chroma):
    order: list[str] = []
    audit = _wire(monkeypatch, fleet, order)
    approval, decider = _approval(), uuid.uuid4()
    set_verified_decider(approval, decider)

    await action.execute_kb_wipe_action(approval, _session(order))

    (operation,), kwargs = audit.await_args
    details = kwargs["details"]
    assert operation == "knowledge.wipe" and kwargs["result"] == "success" and kwargs["durable"] is True
    assert details["approved_by"] == "alice" and details["approver_id"] == str(decider)
    assert details["approved_at"].startswith("2026-11-08T09:00") and details["self_approval"] is False
    assert details["collections"] == ["autobot_memory", "space_b"]
    assert [c["vectors"] for c in details["chroma"]] == [7, 5]
    assert order == ["audit", "commit"]
    assert set(fleet["knowledge"].data) == {OVERRIDE_KEY}
    assert len(chroma.cols["co"].ids) == 4


@pytest.mark.asyncio
async def test_collection_names_are_resolved_before_anything_is_deleted(monkeypatch, fleet, chroma):
    _wire(monkeypatch, fleet)
    seen = {}

    def names():
        seen["untouched"] = set(fleet["knowledge"].data) == set(_knowledge_data()) and bool(fleet["knowledge"].indexes)
        return ["autobot_memory", "space_b"]

    monkeypatch.setattr(action, "kb_collection_names", names)
    approval = _approval()
    set_verified_decider(approval, uuid.uuid4())
    await action.execute_kb_wipe_action(approval, _session())
    assert seen["untouched"]


@pytest.mark.asyncio
async def test_a_wipe_without_a_verified_decider_deletes_nothing(monkeypatch, fleet):
    audit = _wire(monkeypatch, fleet)
    with pytest.raises(ValueError):
        await action.execute_kb_wipe_action(_approval(), _session())
    audit.assert_not_awaited()
    assert set(fleet["knowledge"].data) == set(_knowledge_data())


@pytest.mark.asyncio
async def test_a_failure_in_the_second_step_audits_the_first_as_done_then_reraises(monkeypatch, fleet, chroma):
    audit = _wire(monkeypatch, fleet)
    chroma.fail = True
    approval = _approval()
    set_verified_decider(approval, uuid.uuid4())
    with pytest.raises(ConnectionError):
        await action.execute_kb_wipe_action(approval, _session())
    kwargs = audit.await_args.kwargs
    assert kwargs["result"] == "failed" and kwargs["details"]["error"] == "ConnectionError"
    assert any(s["kind"] == "index" and s["name"] == "llama_index" for s in kwargs["details"]["redis"])
    assert kwargs["details"]["chroma"] == []


@pytest.mark.asyncio
async def test_a_failure_midway_through_redis_keeps_the_steps_already_taken(monkeypatch, fleet, chroma):
    fleet["knowledge"].fail_unlink_on = "tag:"
    audit = _wire(monkeypatch, fleet)
    approval = _approval()
    set_verified_decider(approval, uuid.uuid4())
    with pytest.raises(ConnectionError):
        await action.execute_kb_wipe_action(approval, _session())
    done = {(s["kind"], s["name"]) for s in audit.await_args.kwargs["details"]["redis"]}
    assert ("index", "llama_index") in done and ("prefix", "fact:") in done and ("prefix", "tag:") not in done


@pytest.mark.asyncio
async def test_a_lost_success_audit_is_raised_not_swallowed(monkeypatch, fleet, chroma):
    audit = _wire(monkeypatch, fleet)
    audit.side_effect = None
    audit.return_value = False
    approval = _approval()
    set_verified_decider(approval, uuid.uuid4())
    with pytest.raises(RuntimeError):
        await action.execute_kb_wipe_action(approval, _session())


def _admins(*ids):
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(ids)
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_the_only_admin_may_approve_their_own_request_flagged():
    me = uuid.uuid4()
    approval = _approval(requester=me)
    set_verified_decider(approval, me)
    assert await action._review_kb_wipe(approval, _admins(me)) is True


@pytest.mark.asyncio
async def test_self_approval_is_refused_when_a_second_admin_exists():
    me = uuid.uuid4()
    approval = _approval(requester=me)
    set_verified_decider(approval, me)
    with pytest.raises(FourEyesError):
        await action._review_kb_wipe(approval, _admins(me, uuid.uuid4()))


@pytest.mark.asyncio
async def test_another_admin_deciding_is_not_a_self_approval_and_an_unnamed_requester_passes():
    me, other = uuid.uuid4(), uuid.uuid4()
    approval = _approval(requester=me)
    set_verified_decider(approval, other)
    assert await action._review_kb_wipe(approval, _admins(me, other)) is False
    assert await action._review_kb_wipe(_approval(), _admins(me)) is False


@pytest.mark.asyncio
async def test_a_self_approved_wipe_is_flagged_in_the_audit(monkeypatch, fleet, chroma):
    audit = _wire(monkeypatch, fleet)
    me = uuid.uuid4()
    approval = _approval(requester=me)
    set_verified_decider(approval, me)
    monkeypatch.setattr(action, "is_self_approval", AsyncMock(return_value=True))
    await action.execute_kb_wipe_action(approval, _session())
    assert audit.await_args.kwargs["details"]["self_approval"] is True


@pytest.mark.asyncio
async def test_propose_takes_the_advisory_lock_first_and_refreshes_a_reused_proposal(monkeypatch):
    calls: list[str] = []
    pending = types.SimpleNamespace(context={"action": action.ACTION, "plan": {"total_keys": 1}})
    session = MagicMock()
    found = MagicMock()
    found.scalars.return_value.first.return_value = pending
    session.execute = AsyncMock(side_effect=lambda stmt, *a: calls.append(str(stmt)[:30]) or found)
    session.commit = AsyncMock()
    got = await action.propose_kb_wipe(session, "u", {"total_keys": 9})
    assert got is pending and "pg_advisory_xact_lock" in calls[0]
    assert pending.context["plan"] == {"total_keys": 9}
    session.commit.assert_awaited()
