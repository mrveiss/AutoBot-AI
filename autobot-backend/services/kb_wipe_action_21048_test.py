# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The knowledge wipe is gated, knowledge-only, previewable, honestly audited and four-eyed (#21048, #17038).

Fakes only: no real Redis, Chroma or database is touched.
"""

import fnmatch
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
        return iter([k for k in list(self.data) if fnmatch.fnmatchcase(k, match)])

    def unlink(self, *keys):
        if self.fail_unlink_on and any(k.startswith(self.fail_unlink_on) for k in keys):
            raise ConnectionError("lost")
        self.unlink_calls = getattr(self, "unlink_calls", 0) + 1
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


#: Derived from KB content: the wipe removes these.
WIPED = {
    "fact:1": "x",
    "fact:origin:session:1": "x",
    "session:facts:s": "x",
    "content_hash:h": "x",
    "unique_key:man_page:m": "x",
    "user:kb:facts:u": "x",
    "group:kb:facts:g": "x",
    "org:kb:facts:o": "x",
    "user:facts:u": "x",
    "kb:stats": "x",
    "kb:ingest:d": "x",
    "kb:rel:out:1": "x",
    "tag:a": "x",
    "category:facts:c": "x",
    "collection:facts:k": "x",
    "connector:c1:ts:src": "x",
    "connector:notion:ts:c1:p": "x",
    "connector:gitlab:ts:c1:p": "x",
    "connector:notion:hash:c1:p": "x",
    "connector:c1:checkpoint": "x",
    "connector:c1:external_state": "x",
    "bm25:corpus_stats": "x",
    "context:summary:d": "x",
    "entity:1": "x",
    "entity:name:n": "x",
    "timeline:global": "x",
}
#: Settings, definitions, credentials, locks, templates and user activity: the wipe keeps these.
KEPT = {
    OVERRIDE_KEY: "model-b",
    "autobot:kb:embedding_switch": "x",
    "category:c1": "x",
    "category:path:a/b": "x",
    "category:children:c1": "x",
    "category:root": "x",
    "collection:k": "x",
    "collection:all": "x",
    "tag_style:red": "x",
    "metadata:template:all": "x",
    "connector:c1": "x",
    "connector:c1:auth": "x",
    "connector:oauth:state:s": "x",
    "connector:oauth:refresh:c1": "x",
    "connector:schedule:c1": "x",
    "connector:scheduler:leader": "x",
    "connector:sync:c1": "x",
    "rag:feedback:u:2026": "x",
}


def _knowledge_data():
    return {**WIPED, **KEPT}


@pytest.fixture(autouse=True)
def kb_index(monkeypatch):
    """The KB's own index name comes from ``knowledge.index_scope``; pin it so no real configuration is read."""
    monkeypatch.setattr(redis_mod, "kb_index_names", lambda: ("llama_index",))


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
    counts = {p["prefix"]: p["keys"] for p in store["prefixes"]}
    assert counts["fact:"] == 2 and counts["connector:*:ts:"] == 3 and counts["bm25:corpus_stats"] == 1
    assert store["keys"] == len(WIPED) and "Not atomic" in store["note"]
    assert plan["chroma_collections"] == [{"name": "autobot_memory", "vectors": 7}, {"name": "space_b", "vectors": 5}]
    assert (plan["total_keys"], plan["total_vectors"]) == (len(WIPED), 12)
    assert fleet["knowledge"].commands.count(("FT.DROPINDEX", "llama_index", "DD")) == 0
    assert set(fleet["knowledge"].data) == set(_knowledge_data())


def _scope(fleet):
    """The Redis scope an approver's plan freezes: what ``plan_redis`` lists, checked against the code's scope."""
    return redis_mod.frozen_redis_scope(redis_mod.plan_redis(_factory(fleet)))


def test_wipe_removes_kb_prefixes_and_keeps_the_embedding_override_and_every_other_database(fleet):
    record: list[dict] = []
    redis_mod.execute_redis(record, _scope(fleet), _factory(fleet))
    assert set(fleet["knowledge"].data) == set(KEPT)  # embedding choice, settings, credentials, locks survive
    assert fleet["knowledge"].data[OVERRIDE_KEY] == "model-b"
    assert fleet["knowledge"].indexes == {}
    assert {(s["kind"], s["name"]): s["count"] for s in record}[("prefix", "fact:")] == 2
    assert all(s.get("complete", True) for s in record)
    for survivor, keys in (("sessions", 1), ("settings", 1), ("celery_broker", 1)):
        assert fleet[survivor].commands == [] and len(fleet[survivor].data) == keys
    assert fleet["sessions"].indexes == {"session_idx": 3}


def test_scope_is_knowledge_only_and_has_no_full_wipe_option():
    assert redis_mod.KB_WIPE_DATABASES == ("knowledge",)
    assert not any(n in redis_mod.KB_WIPE_DATABASES for n in ("sessions", "main", "logs", "vectors", "agents"))
    for key in KEPT:  # no wiped pattern matches a kept key, and every wiped key matches one
        assert not any(fnmatch.fnmatchcase(key, f"{p}*") for p in redis_mod.KB_KEY_PREFIXES), key
    for key in WIPED:
        assert any(fnmatch.fnmatchcase(key, f"{p}*") for p in redis_mod.KB_KEY_PREFIXES), key


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


#: The plan an approver saw: the KB's index, every KB prefix and the two KB collections, as ``plan_kb_wipe`` lists them.
PLAN = {
    "databases": [
        {
            "database": "knowledge",
            "indexes": [{"name": "llama_index", "documents": 12}],
            "prefixes": [{"prefix": p, "keys": 0} for p in redis_mod.KB_KEY_PREFIXES],
        }
    ],
    "chroma_collections": [{"name": "autobot_memory", "vectors": 7}, {"name": "space_b", "vectors": 5}],
}


def _approval(requester=None, channel=action.CHANNEL_OPERATOR, plan=PLAN, status="approved"):
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        status=status,
        decided_by_user="alice",
        decided_at=datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc),
        requested_by_agent=f"kb-wipe:{requester}" if requester else "kb-wipe:operator",
        context={"action": action.ACTION, "channel": channel, "plan": plan},
    )


def _session(order=None):
    session = MagicMock()
    session.commit = AsyncMock(side_effect=lambda: order.append("commit") if order is not None else None)
    return session


def _wire(monkeypatch, fleet, order=None):
    audit = AsyncMock(side_effect=lambda *a, **k: (order.append("audit") if order is not None else None) or True)
    monkeypatch.setattr(action, "audit_log", audit)
    real = redis_mod.execute_redis
    monkeypatch.setattr(action, "execute_redis", lambda record, scope: real(record, scope, _factory(fleet)))
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
    assert details["phase"] == "completion" and details["step"] == "chroma"
    assert order == ["audit", "audit", "commit"]  # the intent entry, the outcome entry, then the comment's commit
    assert set(fleet["knowledge"].data) == set(KEPT)
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
    steps = {(s["kind"], s["name"]): s for s in audit.await_args.kwargs["details"]["redis"]}
    assert ("index", "llama_index") in steps and steps[("prefix", "fact:")]["complete"] is True
    assert steps[("prefix", "tag:")]["complete"] is False  # started, then lost: the entry is still there


@pytest.mark.asyncio
async def test_a_lost_success_audit_is_raised_not_swallowed(monkeypatch, fleet, chroma):
    audit = _wire(monkeypatch, fleet)
    audit.side_effect = [True, False]  # the intent entry is written, the success entry is not
    approval = _approval()
    set_verified_decider(approval, uuid.uuid4())
    with pytest.raises(RuntimeError, match="ran but"):
        await action.execute_kb_wipe_action(approval, _session())
    assert fleet["knowledge"].indexes == {}  # the wipe did run: the loss is raised, not hidden


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
    operator = _approval()  # the script cannot authenticate: unflagged
    assert await action._review_kb_wipe(operator, _admins(me)) is False


@pytest.mark.asyncio
async def test_a_non_user_requester_on_the_api_channel_fails_closed():
    approval = _approval(channel=action.CHANNEL_API)  # requested_by_agent "kb-wipe:operator" names no user id
    set_verified_decider(approval, uuid.uuid4())
    with pytest.raises(ValueError):
        await action._review_kb_wipe(approval, _admins())
    fleet_untouched = _admins()
    fleet_untouched.execute.assert_not_awaited()


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
    got = await action.propose_kb_wipe(session, str(uuid.uuid4()), {"total_keys": 9})
    assert got is pending and "pg_advisory_xact_lock" in calls[0]
    assert pending.context["plan"] == {"total_keys": 9}
    session.commit.assert_awaited()


def test_a_failure_partway_through_a_prefix_keeps_the_count_so_far(monkeypatch):
    client = FakeRedis({f"fact:{i}": "x" for i in range(5)}, {})
    monkeypatch.setattr(redis_mod, "SCAN_BATCH", 2)
    original = client.unlink

    def flaky(*keys):
        if getattr(client, "unlink_calls", 0) >= 1:
            raise ConnectionError("lost")
        return original(*keys)

    client.unlink = flaky
    record: list[dict] = []
    scope = [{"database": "knowledge", "indexes": [], "prefixes": ["fact:"]}]
    with pytest.raises(ConnectionError):
        redis_mod.execute_redis(record, scope, lambda database: client)
    entry = next(s for s in record if s["name"] == "fact:")
    assert entry["count"] == 2 and entry["complete"] is False


def test_the_executor_scans_each_frozen_prefix_once_and_does_not_plan_again(fleet):
    scope = _scope(fleet)
    scans = []
    original = fleet["knowledge"].scan_iter
    fleet["knowledge"].scan_iter = lambda match, count=None: scans.append(match) or original(match, count)
    redis_mod.execute_redis([], scope, _factory(fleet))
    assert len(scans) == len(redis_mod.KB_KEY_PREFIXES)


@pytest.mark.asyncio
async def test_a_non_user_api_requester_is_refused_before_any_row_or_lock():
    session = MagicMock(execute=AsyncMock(), commit=AsyncMock())
    with pytest.raises(ValueError):
        await action.propose_kb_wipe(session, "alice", {"total_keys": 1})
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_route_answers_403_for_a_non_user_requester_and_creates_nothing():
    from fastapi import HTTPException

    from api import admin_kb_wipe

    session = MagicMock(execute=AsyncMock(), commit=AsyncMock())
    with pytest.raises(HTTPException) as caught:
        await admin_kb_wipe.propose_knowledge_wipe(current_user={"id": "alice", "role": "admin"}, session=session)
    assert caught.value.status_code == 403
    session.execute.assert_not_awaited()
