# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The knowledge wipe is gated, knowledge-only, previewable and audited (#21048, #17038). Fakes only."""

import types
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services import kb_wipe_action as action
from services import kb_wipe_chroma as chroma_mod
from services.approval_execution import _ADMIN_ONLY, _REGISTRY, _SERVER_ONLY, set_verified_decider


class FakeRedis:
    """One Redis database: records every command so a test can see what was (not) issued."""

    def __init__(self, keys: int, indexes: dict[str, int]):
        self.keys, self.indexes, self.commands, self.flushed = keys, dict(indexes), [], False

    def dbsize(self):
        return self.keys

    def execute_command(self, *args):
        self.commands.append(args)
        if args[0] == "FT._LIST":
            return list(self.indexes)
        if args[0] == "FT.INFO":
            return ["index_name", args[1], "num_docs", str(self.indexes[args[1]])]
        if args[0] == "FT.DROPINDEX":
            self.indexes.pop(args[1])
        return "OK"

    def flushdb(self):
        self.flushed, self.keys = True, 0


class FakeCollection:
    def __init__(self, ids):
        self.ids, self.deleted = list(ids), []

    async def count(self):
        return len(self.ids)

    async def get(self, include=None, limit=None):
        return {"ids": self.ids[:limit]}

    async def delete(self, ids):
        self.deleted.append(list(ids))
        self.ids = [i for i in self.ids if i not in ids]


class FakeChroma:
    """A Chroma client holding the KB collection and a sibling that must survive."""

    def __init__(self):
        self.cols = {"autobot_memory": FakeCollection(range(7)), "company_kb": FakeCollection(range(4))}
        self.dropped = []

    async def get_collection_or_none(self, name):
        return self.cols.get(name)

    async def delete_collection(self, name):
        self.dropped.append(name)


@pytest.fixture
def chroma(monkeypatch):
    client = FakeChroma()
    monkeypatch.setattr(chroma_mod, "kb_collection_names", lambda: ["autobot_memory"])

    async def factory():
        return client

    monkeypatch.setattr(chroma_mod, "default_chroma_client", factory)
    monkeypatch.setattr(chroma_mod, "CLEAR_BATCH", 3)
    return client


@pytest.fixture
def fleet():
    return {
        "knowledge": FakeRedis(40, {"llama_index": 12}),
        "sessions": FakeRedis(7, {"session_idx": 3}),
        "settings": FakeRedis(5, {}),
        "celery_broker": FakeRedis(9, {}),
    }


def _factory(fleet):
    return lambda database: fleet[database]


def _destructive(client):
    return [c for c in client.commands if c[0] == "FT.DROPINDEX"] + ([("flushdb",)] if client.flushed else [])


@pytest.mark.asyncio
async def test_plan_lists_kb_stores_with_counts_and_deletes_nothing(fleet, chroma):
    plan = await action.plan_kb_wipe(_factory(fleet), chroma_mod.default_chroma_client)
    assert plan == {
        "databases": [{"database": "knowledge", "keys": 40, "indexes": [{"name": "llama_index", "documents": 12}]}],
        "chroma_collections": [{"name": "autobot_memory", "vectors": 7}],
        "total_keys": 40,
        "total_vectors": 7,
    }
    assert all(_destructive(client) == [] for client in fleet.values())
    assert chroma.cols["autobot_memory"].deleted == [] and chroma.dropped == []


@pytest.mark.asyncio
async def test_chroma_clear_empties_only_the_named_kb_collection_and_never_drops_one(chroma):
    cleared = await chroma_mod.clear_chroma(chroma_mod.default_chroma_client)
    assert cleared == [{"name": "autobot_memory", "vectors": 7}]
    assert chroma.cols["autobot_memory"].ids == [] and len(chroma.cols["autobot_memory"].deleted) == 3
    assert len(chroma.cols["company_kb"].ids) == 4 and chroma.dropped == []


def test_wipe_touches_only_the_knowledge_database_and_reports_counts(fleet):
    deleted = action.execute_wipe(_factory(fleet))
    assert deleted[0]["keys"] == 40 and deleted[0]["indexes"] == [{"name": "llama_index", "documents": 12}]
    assert fleet["knowledge"].flushed and fleet["knowledge"].indexes == {}
    for survivor in ("sessions", "settings", "celery_broker"):
        assert fleet[survivor].commands == [] and not fleet[survivor].flushed
    assert (fleet["sessions"].keys, fleet["settings"].keys, fleet["celery_broker"].keys) == (7, 5, 9)
    assert fleet["sessions"].indexes == {"session_idx": 3}


def test_scope_is_knowledge_only_and_has_no_full_wipe_option():
    assert action.KB_WIPE_DATABASES == ("knowledge",)
    assert not any(name in action.KB_WIPE_DATABASES for name in ("sessions", "main", "logs", "vectors", "agents"))


@pytest.mark.asyncio
async def test_an_unavailable_database_refuses_instead_of_pretending(fleet, chroma):
    with pytest.raises(RuntimeError):
        await action.plan_kb_wipe(lambda database: None, chroma_mod.default_chroma_client)


def test_registration_is_server_only_admin_only_and_proposed_in_this_module():
    action.register_kb_wipe_action()
    assert action.ACTION in _REGISTRY and action.ACTION in _SERVER_ONLY and action.ACTION in _ADMIN_ONLY


def _approval(decided: bool = True):
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        decided_by_user="alice" if decided else None,
        decided_at=datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc),
        context={"action": action.ACTION},
    )


@pytest.mark.asyncio
async def test_approved_wipe_runs_and_writes_an_audit_record_with_approver_time_and_counts(monkeypatch, fleet, chroma):
    audit = AsyncMock()
    monkeypatch.setattr(action, "audit_log", audit)
    real = action.execute_wipe
    monkeypatch.setattr(action, "execute_wipe", lambda: real(_factory(fleet)))
    approval, session = _approval(), MagicMock(commit=AsyncMock())
    set_verified_decider(approval, uuid.uuid4())

    await action.execute_kb_wipe_action(approval, session)

    (operation,), kwargs = audit.await_args
    assert operation == "knowledge.wipe" and kwargs["result"] == "success"
    assert kwargs["details"]["approved_by"] == "alice"
    assert kwargs["details"]["approved_at"].startswith("2026-11-08T09:00")
    assert kwargs["details"]["stores"][0]["keys"] == 40
    assert kwargs["details"]["chroma_collections"] == [{"name": "autobot_memory", "vectors": 7}]
    assert chroma.cols["autobot_memory"].ids == [] and len(chroma.cols["company_kb"].ids) == 4
    assert fleet["sessions"].commands == []
    session.add.assert_called_once()


@pytest.mark.asyncio
async def test_a_wipe_without_a_verified_decider_deletes_nothing(monkeypatch, fleet):
    wiped = MagicMock()
    monkeypatch.setattr(action, "execute_wipe", wiped)
    with pytest.raises(ValueError):
        await action.execute_kb_wipe_action(_approval(), MagicMock())
    wiped.assert_not_called()


@pytest.mark.asyncio
async def test_a_failed_wipe_is_audited_as_failed_and_reraised(monkeypatch, chroma):
    audit = AsyncMock()
    monkeypatch.setattr(action, "audit_log", audit)
    monkeypatch.setattr(action, "execute_wipe", MagicMock(side_effect=RuntimeError("down")))
    approval = _approval()
    set_verified_decider(approval, uuid.uuid4())
    with pytest.raises(RuntimeError):
        await action.execute_kb_wipe_action(approval, MagicMock())
    assert audit.await_args.kwargs["result"] == "failed"
