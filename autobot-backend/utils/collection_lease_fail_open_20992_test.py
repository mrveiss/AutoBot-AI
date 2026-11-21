# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Write-lease failure modes (#20992): writers fail open, the delete fails closed, a lapsed lease blocks the write."""

import asyncio
import logging
import threading
import time

import pytest

from autobot_shared.coordination import collection_lease as cl
from autobot_shared.coordination import work_claims_sync
from autobot_shared.coordination.work_claims import ClaimUnavailable
from utils.leased_chroma import delete_if_empty, lease_client

try:
    import fakeredis
except ImportError:  # pragma: no cover
    fakeredis = None

_NAME = "autobot_docs"


class _Raw:
    """A sync Chroma collection; the four write operations record the ids written."""

    def __init__(self, name):
        self.name, self.added = name, []

    def __getattr__(self, op):  # no hand-written session-shaped method (#18883)
        if op not in ("add", "upsert", "update", "delete"):
            raise AttributeError(op)
        return lambda **kwargs: self.added.append(kwargs["ids"])

    def count(self):
        return 0


class _Client:
    def __init__(self):
        self.collections = {_NAME: _Raw(_NAME)}
        self.deleted = []

    def get_collection(self, name, **_):
        return self.collections[name]

    def delete_collection(self, name):
        self.deleted.append(name)


@pytest.fixture
def redis(monkeypatch):
    if fakeredis is None:
        pytest.skip("fakeredis[lua] not installed")
    client = fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    monkeypatch.setattr(work_claims_sync, "get_redis_client", lambda **_: client)
    return client


@pytest.fixture
def redis_down(monkeypatch):
    monkeypatch.setattr(work_claims_sync, "get_redis_client", lambda **_: None)


def test_a_writer_proceeds_with_redis_down_and_warns_with_the_name_only(redis_down, caplog):
    client = _Client()
    with caplog.at_level(logging.WARNING):
        lease_client(client).get_collection(name=_NAME).add(ids=["secret-doc-id"], documents=["secret text"])
    assert client.collections[_NAME].added == [["secret-doc-id"]]
    warnings = " ".join(r.getMessage() for r in caplog.records)
    assert _NAME in warnings and "secret" not in warnings


def test_a_writer_proceeds_when_redis_raises_a_connection_error(monkeypatch):
    import redis.exceptions as rex

    def boom(*_a, **_k):
        raise rex.ConnectionError("down")

    monkeypatch.setattr(cl, "try_acquire_sync", boom)
    client = _Client()
    lease_client(client).get_collection(name=_NAME).add(ids=["a"])
    assert client.collections[_NAME].added == [["a"]]


def test_the_delete_refuses_with_redis_down(redis_down):
    client = _Client()
    with pytest.raises(ClaimUnavailable):
        delete_if_empty(client, _NAME)
    assert client.deleted == []


def test_a_lease_that_lapses_before_the_write_prevents_it(redis, monkeypatch):
    real_take = cl.Lease.try_take

    def take_then_expire(self):
        got = real_take(self)
        redis.delete(*redis.keys("work_claims:c:kb:*"))  # the claim's TTL ran out before the write
        return got

    monkeypatch.setattr(cl.Lease, "try_take", take_then_expire)
    client = _Client()
    with pytest.raises(cl.CollectionLeaseUnavailable, match="lapsed"):
        lease_client(client).get_collection(name=_NAME).add(ids=["a"])
    assert client.collections[_NAME].added == []


def test_a_lease_lost_mid_write_is_logged_as_an_error(redis, caplog):
    with caplog.at_level(logging.ERROR):
        with cl.write_lease(_NAME) as lease:
            redis.delete(*redis.keys("work_claims:c:kb:*"))
            assert lease.renew() is False
    assert any("lost" in r.getMessage() and _NAME in r.getMessage() for r in caplog.records)


def test_a_short_write_is_never_renewed(redis, monkeypatch):
    renewals = []
    monkeypatch.setattr(cl.Lease, "renew_due", lambda self: renewals.append(self))
    with cl.write_lease(_NAME):
        pass
    threading.Event().wait(0.1)
    assert renewals == [] and redis.keys("work_claims:c:kb:*") == []


def test_the_renewer_keeps_a_long_write_alive(redis, monkeypatch):
    monkeypatch.setattr(cl, "RENEW_DIVISOR", 1200)  # ttl 60s -> a renew every 0.05s
    renewals = []
    real = cl.Lease.renew
    monkeypatch.setattr(cl.Lease, "renew", lambda self: renewals.append(1) or real(self))
    with cl.write_lease(_NAME):
        threading.Event().wait(0.4)
    assert len(renewals) >= 2


def test_a_write_after_a_rename_leases_the_new_name(redis):
    client, seen = _Client(), []
    raw = client.collections[_NAME]
    leased = lease_client(client).get_collection(name=_NAME)
    raw.name = "renamed_docs"  # the lease is keyed by the name at write time
    raw.add = lambda **kw: seen.append(redis.keys("work_claims:c:kb:*"))
    leased.add(ids=["a"])
    assert len(seen[0]) == 1 and "renamed_docs" in seen[0][0] and _NAME not in seen[0][0]


def test_a_sync_wait_on_the_event_loop_raises_instead_of_blocking(redis):
    async def go():
        with cl.delete_lease(_NAME):
            with pytest.raises(cl.CollectionLeaseUnavailable, match="event loop"):
                lease_client(_Client()).get_collection(name=_NAME).add(ids=["a"])

    asyncio.run(go())


def _verdicts(monkeypatch, verdicts):
    """Script Lease.renew with *verdicts* (then True forever); returns the call counter."""
    calls = []

    def fake(self):
        calls.append(1)
        v = verdicts[len(calls) - 1] if len(calls) <= len(verdicts) else True
        self.lost = self.lost or v is False
        return v

    monkeypatch.setattr(cl.Lease, "renew", fake)
    monkeypatch.setattr(cl, "RENEW_DIVISOR", 1200)  # ttl 60s -> due every 0.05s
    monkeypatch.setattr(cl, "LEASE_RENEW_RETRY_S", 0.01)
    return calls


def test_a_renew_that_hit_a_redis_blip_is_retried_not_dropped(redis, monkeypatch):
    calls = _verdicts(monkeypatch, [None])
    with cl.write_lease(_NAME) as lease:
        threading.Event().wait(0.4)
        assert len(calls) >= 3 and not lease.lost and not lease._lapsed
    assert not lease.lost and not lease._lapsed


def test_a_renew_that_found_the_claim_gone_sets_lost_and_drops_the_lease(redis, monkeypatch):
    calls = _verdicts(monkeypatch, [False])
    with cl.write_lease(_NAME) as lease:
        threading.Event().wait(0.3)
        assert lease.lost and lease._lapsed and lease not in cl._RENEWER._due
        assert len(calls) == 1


def test_add_restarts_a_dead_renewer_thread(redis, monkeypatch):
    renewer = cl._Renewer()
    renewer._thread = threading.Thread(target=lambda: None)
    renewer._thread.start()
    renewer._thread.join()
    dead = renewer._thread
    lease = cl.Lease(_NAME, cl.ClaimMode.SHARED, 60)
    try:
        renewer.add(lease)
        assert renewer._thread is not dead and renewer._thread.is_alive()
    finally:
        lease._stopped = True
        renewer.remove(lease)


def test_a_renew_that_raises_does_not_kill_the_renewer(redis, monkeypatch):
    monkeypatch.setattr(cl, "RENEW_DIVISOR", 1200)
    monkeypatch.setattr(cl, "LEASE_RENEW_RETRY_S", 0.01)
    calls = []

    def boom(self):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("boom")
        return True

    monkeypatch.setattr(cl.Lease, "renew_due", boom)
    with cl.write_lease(_NAME):
        threading.Event().wait(0.4)
    assert len(calls) >= 2


def test_stop_while_a_retry_is_pending_drops_the_lease_and_ends_the_renews(redis, monkeypatch):
    monkeypatch.setattr(cl, "RENEW_DIVISOR", 1200)  # ttl 60s -> due every 0.05s
    monkeypatch.setattr(cl, "LEASE_RENEW_RETRY_S", 0.01)
    calls, first = [], threading.Event()

    def blip(self):
        calls.append(1)
        first.set()
        return None  # registry unreachable: the lease is re-scheduled for a retry

    monkeypatch.setattr(cl.Lease, "renew_due", blip)
    with cl.write_lease(_NAME) as lease:
        assert first.wait(10), "the renewer never ran the scheduled renew"
        lease.stop()
        assert lease not in cl._RENEWER._due
        seen = len(calls)
        threading.Event().wait(0.5)  # 50x the retry interval and 10x the renew interval
        assert len(calls) <= seen + 1 and lease not in cl._RENEWER._due
        # at most one renew was already in flight when stop() ran; none is scheduled after it
        settled = len(calls)
        threading.Event().wait(0.3)
        assert len(calls) == settled


def test_the_retry_interval_is_honoured_after_a_redis_blip(monkeypatch):
    monkeypatch.setattr(cl, "RENEW_DIVISOR", 60)  # ttl 60s -> the normal interval (1s) is above the retry
    monkeypatch.setattr(cl, "LEASE_RENEW_RETRY_S", 0.2)
    calls = []
    monkeypatch.setattr(cl.Lease, "renew_due", lambda self: calls.append(time.monotonic()))  # returns None
    renewer, lease = cl._Renewer(), cl.Lease(_NAME, cl.ClaimMode.SHARED, 60)
    try:
        renewer.add(lease, delay_s=0)
        threading.Event().wait(0.5)
    finally:
        lease._stopped = True
        renewer.remove(lease)
    # retries at ~0, 0.2, 0.4: a renewer that ignored the interval would have called thousands of times
    assert 2 <= len(calls) <= 4
    assert all(b - a >= 0.15 for a, b in zip(calls, calls[1:]))
