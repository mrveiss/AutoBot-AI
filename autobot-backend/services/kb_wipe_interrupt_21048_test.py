# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A knowledge wipe that is interrupted, or planned from an unreadable store, says exactly what happened (#21048).

Fakes only: no Redis, ChromaDB or database is touched.
"""

import asyncio
import threading
import types
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from services import kb_wipe_action as action
from services import kb_wipe_chroma as chroma_mod
from services import kb_wipe_redis as redis_mod
from services.approval_execution import set_verified_decider


def _approval():
    approval = types.SimpleNamespace(
        id=uuid.uuid4(),
        status="approved",
        decided_by_user="alice",
        decided_at=datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc),
        requested_by_agent="kb-wipe:operator",
        context={"action": action.ACTION, "channel": action.CHANNEL_OPERATOR, "plan": {}},
    )
    set_verified_decider(approval, uuid.uuid4())
    return approval


# -- a cancelled wipe is audited and its worker told to stop -----------------------------------------------------


@pytest.mark.asyncio
async def test_a_cancelled_wipe_writes_the_failed_outcome_stops_the_worker_and_reraises(monkeypatch):
    audit = AsyncMock(return_value=True)
    monkeypatch.setattr(action, "audit_log", audit)
    started, observed = threading.Event(), {}

    def worker(record, scope, stop=None):
        record.append({"database": "knowledge", "kind": "prefix", "name": "fact:", "count": 3, "complete": False})
        started.set()
        observed["stopped"] = stop.wait(5)

    monkeypatch.setattr(action, "execute_redis", worker)
    task = asyncio.create_task(action._wipe(_approval(), {"redis": [], "collections": ["c"]}, False))
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    kwargs = audit.await_args.kwargs
    assert kwargs["result"] == "failed" and kwargs["details"]["error"] == "CancelledError"
    assert "cancelled, in progress" in kwargs["details"]["note"]
    assert kwargs["details"]["redis"][0]["count"] == 3 and kwargs["details"]["step"] == "redis"
    for _ in range(100):
        if observed.get("stopped"):
            break
        await asyncio.sleep(0.01)
    assert observed["stopped"] is True


class _Redis:
    def __init__(self, keys):
        self.keys, self.unlinked = list(keys), 0

    def execute_command(self, *args):
        return []

    def scan_iter(self, match, count=None):
        return iter(self.keys)

    def unlink(self, *keys):
        self.unlinked += len(keys)
        return len(keys)


def test_a_stop_flag_ends_the_prefix_unlink_before_the_next_batch(monkeypatch):
    monkeypatch.setattr(redis_mod, "SCAN_BATCH", 2)
    client, stop, entry = _Redis(f"fact:{i}" for i in range(6)), threading.Event(), {"count": 0}
    original = client.unlink

    def unlink_then_stop(*keys):
        stop.set()
        return original(*keys)

    client.unlink = unlink_then_stop
    with pytest.raises(redis_mod.WipeStopped):
        redis_mod._unlink_prefix(client, "fact:", entry, stop)
    assert client.unlinked == 2 and entry["count"] == 2


# -- the index step exists before the drop runs -------------------------------------------------------------------


def test_a_connection_lost_during_the_index_drop_still_leaves_its_step_incomplete():
    class Lost(_Redis):
        def execute_command(self, *args):
            if args[0] == "FT._LIST":
                return ["llama_index"]
            if args[0] == "FT.INFO":
                return ["num_docs", "4"]
            raise ConnectionError("lost after the server ran it")

    record: list[dict] = []
    with pytest.raises(ConnectionError):
        redis_mod._drop_indexes(Lost([]), "knowledge", ["llama_index"], record)
    assert record == [{"database": "knowledge", "kind": "index", "name": "llama_index", "count": 4, "complete": False}]


# -- a Chroma failure mid-collection keeps the count so far -------------------------------------------------------


class _Collection:
    def __init__(self, n, fail_on_delete=None):
        self.ids, self.deletes, self.fail_on_delete = list(range(n)), 0, fail_on_delete

    async def count(self):
        return len(self.ids)

    async def get(self, include=None, limit=None):
        return {"ids": self.ids[:limit]}

    async def delete(self, ids):
        self.deletes += 1
        if self.deletes == self.fail_on_delete:
            raise ConnectionError("chroma down")
        self.ids = self.ids[len(ids) :]


@pytest.mark.asyncio
async def test_a_failure_after_some_batches_records_how_many_vectors_were_deleted(monkeypatch):
    monkeypatch.setattr(chroma_mod, "CLEAR_BATCH", 2)
    collection = _Collection(7, fail_on_delete=3)

    async def factory():
        return types.SimpleNamespace(get_collection_or_none=AsyncMock(return_value=collection))

    record: list[dict] = []
    with pytest.raises(ConnectionError):
        await chroma_mod.clear_chroma(["c"], record, factory)
    assert record == [{"name": "c", "vectors": 7, "deleted": 4, "complete": False}]


# -- an unreadable override store never narrows the plan ---------------------------------------------------------


def _unreadable():
    raise RuntimeError("the embedding-model override could not be read (ConnectionError)")


@pytest.fixture
def configured(monkeypatch):
    manager = types.SimpleNamespace(get=lambda key, default=None: default)
    monkeypatch.setattr("config.manager.get_config_manager", lambda: manager)


def test_the_collection_names_include_the_active_space_read_strictly(monkeypatch, configured):
    space = types.SimpleNamespace(collection="space_b")
    monkeypatch.setattr(chroma_mod, "read_embedding_space_strict", lambda: space)
    assert chroma_mod.kb_collection_names() == ["autobot_memory", "space_b"]


def test_the_collection_names_raise_when_the_override_store_is_unreadable(monkeypatch, configured):
    monkeypatch.setattr(chroma_mod, "read_embedding_space_strict", _unreadable)
    with pytest.raises(RuntimeError, match="could not be read"):
        chroma_mod.kb_collection_names()


@pytest.mark.asyncio
async def test_the_plan_is_refused_when_the_override_store_is_unreadable(monkeypatch, configured):
    monkeypatch.setattr(chroma_mod, "read_embedding_space_strict", _unreadable)
    monkeypatch.setattr(action, "kb_collection_names", chroma_mod.kb_collection_names)
    monkeypatch.setattr(action, "plan_redis", lambda *a, **k: [])
    with pytest.raises(RuntimeError, match="could not be read"):
        await action.plan_kb_wipe()


@pytest.mark.asyncio
async def test_the_frozen_scope_is_refused_before_any_delete_when_the_override_store_is_unreadable(
    monkeypatch, configured
):
    monkeypatch.setattr(chroma_mod, "read_embedding_space_strict", _unreadable)
    monkeypatch.setattr(action, "kb_collection_names", chroma_mod.kb_collection_names)
    approval = _approval()
    approval.context["plan"] = {"databases": [], "chroma_collections": [{"name": "space_b", "vectors": 1}]}
    with pytest.raises(RuntimeError, match="could not be read"):
        await action._frozen_scope(approval)


def test_frozen_collections_refuses_a_space_that_is_no_longer_active():
    with pytest.raises(ValueError, match="no longer owns"):
        chroma_mod.frozen_collections([{"name": "space_b"}], ["autobot_memory"])
