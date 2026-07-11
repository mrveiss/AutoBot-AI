# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Integration tests for Celery reliability helpers (#11586).

Covers the three acceptance criteria:
  (a) re-delivering an already-executed task_id is a no-op (idempotency guard)
  (b) transient errors engage the retry path; validation errors fail fast
  (c) retry-exhausted tasks land in the queryable Redis dead-letter list

Uses fakeredis for isolation (same pattern as test_task_claim_race.py) and an
in-process eager Celery app so no broker is required.
"""

import json

import pytest

# ---------------------------------------------------------------------------
# Redis fixture: fakeredis for isolation (skip when not installed).
# ---------------------------------------------------------------------------

try:
    import fakeredis
    import fakeredis.aioredis as fakeredis_async

    _FAKEREDIS_AVAILABLE = True
except ImportError:
    _FAKEREDIS_AVAILABLE = False

from celery import Celery
from celery.exceptions import Retry

import utils.celery_reliability as cr
from utils.celery_reliability import (
    CELERY_TRANSIENT_ERRORS,
    DEAD_LETTER_KEY,
    DEDUP_KEY_PREFIX,
    DeadLetterTask,
    idempotent_task,
)

pytestmark = pytest.mark.skipif(not _FAKEREDIS_AVAILABLE, reason="fakeredis not installed")


@pytest.fixture
def fake_sync_redis(monkeypatch):
    """Patch the sync Redis seam in celery_reliability with fakeredis."""
    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.setattr(cr, "get_redis_client", lambda *_a, **_k: client)
    return client


@pytest.fixture
def eager_app():
    """In-process Celery app: eager execution, exceptions propagate."""
    app = Celery("reliability-test", broker="memory://", backend="cache+memory://")
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    return app


# ---------------------------------------------------------------------------
# (a) Idempotency guard — duplicate delivery of the same task_id is a no-op
# ---------------------------------------------------------------------------


def test_duplicate_task_id_is_noop(fake_sync_redis, eager_app):
    """Second delivery of an already-claimed task_id must not re-execute."""
    calls = []

    @eager_app.task(bind=True, name="test.reliability.side_effect")
    @idempotent_task
    def side_effect(self):
        calls.append(1)
        return {"status": "ok"}

    first = side_effect.apply(task_id="dup-1").get()
    second = side_effect.apply(task_id="dup-1").get()

    assert first == {"status": "ok"}
    assert len(calls) == 1, "duplicate delivery must not re-execute the task body"
    assert second == {"task_id": "dup-1", "status": "skipped", "reason": "duplicate_delivery"}


def test_dedup_claim_written_with_ttl(fake_sync_redis, eager_app):
    """The dedup key must exist with a TTL after first execution."""

    @eager_app.task(bind=True, name="test.reliability.claims")
    @idempotent_task
    def claims(self):
        return {"status": "ok"}

    claims.apply(task_id="ttl-1")

    key = f"{DEDUP_KEY_PREFIX}ttl-1"
    assert fake_sync_redis.get(key) == "1"
    assert 0 < fake_sync_redis.ttl(key) <= cr.CELERY_DEDUP_TTL


def test_distinct_task_ids_both_execute(fake_sync_redis, eager_app):
    """Different task_ids are independent — no cross-task blocking."""
    calls = []

    @eager_app.task(bind=True, name="test.reliability.independent")
    @idempotent_task
    def independent(self):
        calls.append(1)
        return {"status": "ok"}

    independent.apply(task_id="ind-1")
    independent.apply(task_id="ind-2")

    assert len(calls) == 2


def test_retry_attempt_bypasses_dedup_guard(fake_sync_redis, eager_app):
    """A retry (retries > 0) of a claimed task_id is a legitimate re-execution."""
    calls = []

    @eager_app.task(bind=True, name="test.reliability.retry_pass")
    @idempotent_task
    def retry_pass(self):
        calls.append(1)
        return {"status": "ok"}

    retry_pass.apply(task_id="retry-1")  # first attempt claims the key
    result = retry_pass.apply(task_id="retry-1", retries=1).get()

    assert len(calls) == 2, "retries must bypass the dedup guard"
    assert result == {"status": "ok"}


def test_redis_unavailable_fails_open(monkeypatch, eager_app):
    """Without Redis the guard must not block execution (fail-open)."""
    monkeypatch.setattr(cr, "get_redis_client", lambda *_a, **_k: None)
    calls = []

    @eager_app.task(bind=True, name="test.reliability.failopen")
    @idempotent_task
    def failopen(self):
        calls.append(1)
        return {"status": "ok"}

    failopen.apply(task_id="open-1")
    failopen.apply(task_id="open-1")

    assert len(calls) == 2, "Redis outage must not turn into a task outage"


# ---------------------------------------------------------------------------
# (b) Retry classification — transient retries, validation fails fast
# ---------------------------------------------------------------------------


def test_transient_error_engages_retry(fake_sync_redis, eager_app):
    """ConnectionError must be converted into a Celery retry, not a failure."""

    @eager_app.task(
        bind=True,
        base=DeadLetterTask,
        name="test.reliability.transient",
        autoretry_for=CELERY_TRANSIENT_ERRORS,
        retry_backoff=True,
        retry_jitter=True,
        max_retries=3,
    )
    def transient(self):
        raise ConnectionError("redis briefly unavailable")

    with pytest.raises(Retry):
        transient.apply(task_id="transient-1", throw=True)


def test_validation_error_fails_fast(fake_sync_redis, eager_app):
    """ValueError must propagate immediately without entering the retry path."""

    @eager_app.task(
        bind=True,
        base=DeadLetterTask,
        name="test.reliability.validation",
        autoretry_for=CELERY_TRANSIENT_ERRORS,
        retry_backoff=True,
        retry_jitter=True,
        max_retries=3,
    )
    def validation(self):
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        validation.apply(task_id="validation-1", throw=True)


# ---------------------------------------------------------------------------
# (c) Dead-letter parking — exhausted retries land in a queryable parked list
# ---------------------------------------------------------------------------


def test_exhausted_retries_park_dead_letter_entry(fake_sync_redis, eager_app):
    """When retries are exhausted, the task must be parked with error detail."""

    @eager_app.task(
        bind=True,
        base=DeadLetterTask,
        name="test.reliability.exhaust",
        autoretry_for=CELERY_TRANSIENT_ERRORS,
        retry_backoff=True,
        retry_jitter=True,
        max_retries=2,
    )
    def exhaust(self, target: str):
        raise ConnectionError("still down")

    # retries == max_retries → autoretry re-raises the original exception and
    # Celery invokes on_failure (throw=False mirrors worker-side handling).
    result = exhaust.apply(args=("host-1",), task_id="exhaust-1", retries=2, throw=False)

    assert result.state == "FAILURE"
    entries = fake_sync_redis.lrange(DEAD_LETTER_KEY, 0, -1)
    assert len(entries) == 1
    entry = json.loads(entries[0])
    assert entry["task_name"] == "test.reliability.exhaust"
    assert entry["task_id"] == "exhaust-1"
    assert entry["status"] == "parked"
    assert "ConnectionError" in entry["error"]
    assert "host-1" in entry["args_summary"]
    assert entry["timestamp"]


def test_dead_letter_list_is_bounded(fake_sync_redis, monkeypatch):
    """The parked list must never exceed CELERY_DEAD_LETTER_MAX entries."""
    monkeypatch.setattr(cr, "CELERY_DEAD_LETTER_MAX", 3)

    for i in range(5):
        cr.park_dead_letter("test.reliability.bound", f"bound-{i}", "args=() kwargs={}", "boom")

    entries = fake_sync_redis.lrange(DEAD_LETTER_KEY, 0, -1)
    assert len(entries) == 3
    # LPUSH ordering: newest first — oldest entries were trimmed.
    assert json.loads(entries[0])["task_id"] == "bound-4"
    assert json.loads(entries[-1])["task_id"] == "bound-2"


async def test_dead_letter_status_queryable(monkeypatch):
    """get_dead_letter_status must expose count + recent entries (health API)."""
    server = fakeredis_async.FakeServer()
    aclient = fakeredis_async.FakeRedis(server=server, decode_responses=True)

    async def _fake_async_client(*_a, **_k):
        return aclient

    monkeypatch.setattr(cr, "get_async_redis_client", _fake_async_client)

    for i in range(3):
        await aclient.lpush(
            DEAD_LETTER_KEY,
            json.dumps({"task_name": "test.t", "task_id": f"q-{i}", "status": "parked"}),
        )

    status = await cr.get_dead_letter_status(limit=2)

    assert status["available"] is True
    assert status["parked"] == 3
    assert len(status["recent"]) == 2
    assert status["recent"][0]["task_id"] == "q-2"
    await aclient.aclose()


async def test_dead_letter_status_without_redis(monkeypatch):
    """Health accessor degrades gracefully when Redis is unavailable."""

    async def _no_client(*_a, **_k):
        return None

    monkeypatch.setattr(cr, "get_async_redis_client", _no_client)

    status = await cr.get_dead_letter_status()

    assert status == {"available": False, "parked": 0, "recent": []}
