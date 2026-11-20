# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``delete_collection_if_empty`` and the per-collection write lease (#20992, #17038).

Real ``EVAL`` via fakeredis[lua], as in ``tests/coordination/test_work_claims.py``: the registry's own Lua
decides every conflict here, so the lease semantics tested are the production ones.
"""

import asyncio
import threading

import pytest

from autobot_shared.coordination import collection_lease as cl
from autobot_shared.coordination import work_claims_sync
from autobot_shared.coordination.work_claims import ClaimUnavailable
from autobot_shared.eventually import eventually
from services import chroma_empty_collections as svc
from utils.async_chromadb_client import AsyncChromaClient
from utils.leased_chroma import LeasedChromaClient, delete_if_empty, lease_client

try:
    import fakeredis
except ImportError:  # pragma: no cover
    fakeredis = None

_NAME = "autobot_docs"
_CLAIM_KEYS = "work_claims:c:kb:*"


@pytest.fixture
def redis(monkeypatch):
    if fakeredis is None:
        pytest.skip("fakeredis[lua] not installed")
    client = fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    monkeypatch.setattr(work_claims_sync, "get_redis_client", lambda **_: client)
    return client


class _Raw:
    """A sync Chroma collection; ``on_count`` runs inside the count (where a concurrent actor would act)."""

    def __init__(self, owner, name, vectors=0):
        self.owner, self.name, self.vectors, self.on_count = owner, name, vectors, None

    def count(self):
        seen = self.vectors
        if self.on_count:
            self.on_count()
        return seen

    def __getattr__(self, op):  # the four write operations, without a hand-written session-shaped method
        if op not in ("add", "upsert", "update", "delete"):
            raise AttributeError(op)
        return lambda **kwargs: self._write(op, kwargs)

    def _write(self, op, kwargs):
        self.vectors = 0 if op == "delete" else self.vectors + len(kwargs["ids"])


class _Sync:
    def __init__(self, vectors=0):
        self.collections = {_NAME: _Raw(self, _NAME, vectors)}
        self.deleted = []
        self.delete_error = None

    def get_collection(self, name, embedding_function=None):
        return self.collections[name]

    def delete_collection(self, name):
        if self.delete_error:
            raise self.delete_error
        self.deleted.append(name)
        self.collections.pop(name)


def _held(redis):
    return redis.keys(_CLAIM_KEYS)


def test_an_empty_collection_is_deleted_and_the_lease_released(redis):
    sync = _Sync()
    assert delete_if_empty(sync, _NAME) == 0
    assert sync.deleted == [_NAME] and _held(redis) == []


def test_the_count_runs_while_the_delete_holds_the_lease(redis):
    sync, seen = _Sync(), []
    sync.collections[_NAME].on_count = lambda: seen.append(len(_held(redis)))
    delete_if_empty(sync, _NAME)
    assert seen == [1]


def test_a_non_empty_collection_returns_its_count_and_is_kept(redis):
    sync = _Sync(vectors=4)
    assert delete_if_empty(sync, _NAME) == 4
    assert sync.deleted == [] and _NAME in sync.collections and _held(redis) == []


def test_a_delete_while_a_write_holds_the_lease_does_not_run(redis):
    sync = _Sync()
    with cl.write_lease(_NAME):
        with pytest.raises(cl.CollectionLeaseUnavailable, match="write is in progress"):
            delete_if_empty(sync, _NAME)
    assert sync.deleted == [] and _NAME in sync.collections


def test_a_write_waits_for_a_running_delete_and_lands_after_it(redis):
    sync = _Sync()
    leased = lease_client(sync)
    landed = threading.Event()
    with cl.delete_lease(_NAME):
        writer = threading.Thread(
            target=lambda: (leased.get_collection(name=_NAME).add(ids=["a"]), landed.set()), daemon=True
        )
        writer.start()
        assert not landed.wait(0.4)  # blocked on the lease while the delete holds it
        assert sync.collections[_NAME].vectors == 0
    assert landed.wait(5)
    writer.join(5)
    assert sync.collections[_NAME].vectors == 1  # the write was held back, not lost


def test_a_write_that_outwaits_the_delete_raises_and_writes_nothing(redis, monkeypatch):
    monkeypatch.setattr(cl, "WRITE_LEASE_WAIT_S", 0.2)
    sync = _Sync()
    with cl.delete_lease(_NAME):
        with pytest.raises(cl.CollectionLeaseUnavailable, match="waited"):
            lease_client(sync).get_collection(name=_NAME).add(ids=["a"])
    assert sync.collections[_NAME].vectors == 0


def test_writers_share_the_lease(redis):
    with cl.write_lease(_NAME), cl.write_lease(_NAME):
        assert len(_held(redis)) == 2


def test_a_lease_that_lapsed_after_the_count_means_nothing_is_deleted(redis):
    sync = _Sync()
    sync.collections[_NAME].on_count = lambda: redis.delete(*_held(redis))  # the TTL ran out mid-delete
    with pytest.raises(cl.CollectionLeaseUnavailable, match="lapsed"):
        delete_if_empty(sync, _NAME)
    assert sync.deleted == [] and _NAME in sync.collections


def test_a_crashed_writer_frees_the_collection_when_its_lease_expires(redis):
    sync = _Sync()
    crashed = cl.Lease(_NAME, cl.ClaimMode.SHARED, cl.WRITE_LEASE_TTL_S)
    assert crashed.try_take() is None  # never released: the holder died
    with pytest.raises(cl.CollectionLeaseUnavailable):
        delete_if_empty(sync, _NAME)
    redis.delete(*_held(redis))  # what the claim's TTL does
    assert delete_if_empty(sync, _NAME) == 0


def test_a_failed_delete_leaves_the_collection_and_releases_the_lease(redis):
    sync = _Sync()
    sync.delete_error = OSError("chroma down")
    with pytest.raises(OSError):
        delete_if_empty(sync, _NAME)
    assert _NAME in sync.collections and _held(redis) == []


def test_an_unreachable_registry_means_neither_delete_nor_write(monkeypatch):
    monkeypatch.setattr(work_claims_sync, "get_redis_client", lambda **_: None)
    sync = _Sync()
    with pytest.raises(ClaimUnavailable):
        delete_if_empty(sync, _NAME)
    with pytest.raises(ClaimUnavailable):
        lease_client(sync).get_collection(name=_NAME).add(ids=["a"])
    assert sync.deleted == [] and sync.collections[_NAME].vectors == 0


def test_a_write_through_the_client_holds_the_shared_lease_only_for_the_write(redis):
    sync, during = _Sync(), []
    raw = sync.collections[_NAME]
    raw.upsert = lambda **kw: during.append(len(_held(redis)))
    client = lease_client(sync)
    assert isinstance(client, LeasedChromaClient) and lease_client(client) is client
    client.get_collection(name=_NAME).upsert(ids=["a"])
    assert during == [1] and _held(redis) == []
    assert client.get_collection(name=_NAME).count() == 0  # reads pass through, unleased


@pytest.mark.asyncio
async def test_the_async_client_deletes_an_empty_collection(redis):
    sync = _Sync()
    assert await AsyncChromaClient(sync).delete_collection_if_empty(_NAME) == 0
    assert sync.deleted == [_NAME] and _held(redis) == []


@pytest.mark.asyncio
async def test_a_cancelled_delete_finishes_or_does_nothing_and_releases_the_lease(redis):
    sync = _Sync()
    inside, go = threading.Event(), threading.Event()

    def _slow_count():
        inside.set()
        go.wait(5)

    sync.collections[_NAME].on_count = _slow_count
    task = asyncio.ensure_future(AsyncChromaClient(sync).delete_collection_if_empty(_NAME))
    await asyncio.get_running_loop().run_in_executor(None, inside.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(_held(redis)) == 1  # the worker still holds the lease: no write can slip in
    go.set()
    await eventually(lambda: _held(redis) == [])
    assert _held(redis) == []
    assert sync.deleted == [_NAME] or _NAME in sync.collections  # whole delete, or untouched


@pytest.mark.asyncio
async def test_the_service_reports_a_busy_collection_as_did_not_run(redis, monkeypatch):
    sync = _Sync()

    async def _get():
        return AsyncChromaClient(sync)

    async def _exists(self, name, embedding_function=None):
        return object()

    monkeypatch.setattr(svc, "get_async_chromadb_client", _get)
    monkeypatch.setattr(AsyncChromaClient, "get_collection_or_none", _exists)
    with cl.write_lease(_NAME):
        done, reason = await svc.delete_empty_collection(_NAME)
    assert done is False and "in progress" in reason and sync.deleted == []
    assert await svc.delete_empty_collection(_NAME) == (True, None)
