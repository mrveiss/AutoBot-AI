# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20887: one persistent loop per worker process.

The reproducer uses a file-backed, pooled ``sqlite+aiosqlite`` engine. aiosqlite
itself is loop-agnostic, so pool events record the loop that opened each
connection and refuse reuse once it is closed -- the behaviour of asyncpg, whose
transports belong to the creating loop (``RuntimeError('Event loop is closed')``).
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from pathlib import Path

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from autobot_shared import async_compat, worker_loop

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "autobot-backend"))


@pytest.fixture
def pooled_engine(tmp_path, monkeypatch):
    """A pooled engine installed as the process-wide ``database._async_engine``."""
    from user_management import database

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'w.db'}", poolclass=AsyncAdaptedQueuePool, pool_size=2
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _bind(dbapi_conn, record):
        record.info["loop"] = asyncio.get_running_loop()

    @event.listens_for(engine.sync_engine, "checkout")
    def _guard(dbapi_conn, record, proxy):
        if record.info["loop"].is_closed():
            raise RuntimeError("Event loop is closed")

    monkeypatch.setattr(database, "_async_engine", engine)
    monkeypatch.setattr(database, "_async_session_factory", None)
    yield engine
    worker_loop.stop_worker_loop()


@pytest.fixture(autouse=True)
def _fresh_worker_state():
    worker_loop.stop_worker_loop()
    async_compat.register_main_loop(None)
    yield
    worker_loop.stop_worker_loop()
    async_compat.register_main_loop(None)


async def _use_engine() -> int:
    from user_management.database import get_async_engine

    async with get_async_engine().connect() as conn:
        await conn.execute(text("select 1"))
    return id(asyncio.get_running_loop())


def test_two_asyncio_run_calls_fail_on_a_pooled_engine(pooled_engine):
    """Documents the failure mode: the second private loop meets the first one's connection."""
    asyncio.run(_use_engine())
    with pytest.raises(Exception) as excinfo:
        asyncio.run(_use_engine())
    assert "closed" in str(excinfo.value).lower()


def test_two_run_in_worker_loop_calls_share_one_loop(pooled_engine):
    first = worker_loop.run_in_worker_loop(_use_engine())
    second = worker_loop.run_in_worker_loop(_use_engine())
    assert first == second


def test_loop_runs_on_its_own_thread_and_survives_between_calls():
    async def tid():
        return threading.get_ident()

    a = worker_loop.run_in_worker_loop(tid())
    b = worker_loop.run_in_worker_loop(tid())
    assert a == b != threading.get_ident()


def test_exception_in_coroutine_propagates():
    async def boom():
        raise ValueError("x")

    with pytest.raises(ValueError):
        worker_loop.run_in_worker_loop(boom())
    # loop still usable afterwards
    assert worker_loop.run_in_worker_loop(asyncio.sleep(0, "ok")) == "ok"


def test_timeout_cancels_the_pending_future():
    cancelled = threading.Event()

    async def slow():
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with pytest.raises(Exception):
        worker_loop.run_in_worker_loop(slow(), timeout=0.2)
    assert cancelled.wait(5)


def test_calling_from_the_worker_loop_itself_is_refused():
    async def inner():
        coro = asyncio.sleep(0)
        with pytest.raises(RuntimeError, match="worker loop itself"):
            worker_loop.run_in_worker_loop(coro)

    worker_loop.run_in_worker_loop(inner())


# --- fork reset -----------------------------------------------------------


def test_reset_after_fork_drops_engine_without_touching_connections(monkeypatch):
    from user_management import database

    class FakeSync:
        calls: list = []

        def dispose(self, close=True):
            self.calls.append(close)

    class FakeEngine:
        sync_engine = FakeSync()

    monkeypatch.setattr(database, "_async_engine", FakeEngine())
    monkeypatch.setattr(database, "_async_session_factory", object())
    database.reset_after_fork()
    assert database._async_engine is None and database._async_session_factory is None
    assert FakeSync.calls == [False]


def test_forked_child_does_not_inherit_the_parents_loop():
    worker_loop.start_worker_loop()
    assert worker_loop.in_worker_process()
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:  # child
        os.close(r)
        os.write(w, b"1" if worker_loop.get_worker_loop() is None and not worker_loop.in_worker_process() else b"0")
        os._exit(0)
    os.close(w)
    flag = os.read(r, 1)
    os.close(r)
    os.waitpid(pid, 0)
    assert flag == b"1"


# --- run_or_schedule -------------------------------------------------------


def test_run_or_schedule_without_loop_or_worker_is_plain_asyncio_run():
    """A non-Celery caller with no running loop keeps today's behaviour."""

    async def which():
        return id(asyncio.get_running_loop())

    first = async_compat.run_or_schedule(which())
    second = async_compat.run_or_schedule(which())
    assert first is not None and worker_loop.get_worker_loop() is None
    assert isinstance(second, int)


def test_run_or_schedule_inside_a_worker_uses_the_worker_loop():
    loop = worker_loop.start_worker_loop()

    async def which():
        return asyncio.get_running_loop()

    assert async_compat.run_or_schedule(which()) is loop
    assert async_compat.run_or_schedule(which()) is loop


def test_run_or_schedule_under_a_running_loop_delegates_to_the_main_loop():
    seen = {}

    async def which():
        return asyncio.get_running_loop()

    def other_thread_with_busy_loop(main):
        async def busy():
            seen["got"] = async_compat.run_or_schedule(which())

        asyncio.run(busy())

    ready = threading.Event()
    holder = {}

    def serve():
        loop = asyncio.new_event_loop()
        holder["loop"] = loop
        loop.call_soon(ready.set)
        loop.run_forever()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    ready.wait(5)
    main = holder["loop"]
    async_compat.register_main_loop(main)
    try:
        worker = threading.Thread(target=other_thread_with_busy_loop, args=(main,))
        worker.start()
        worker.join(10)
        assert seen["got"] is main
    finally:
        main.call_soon_threadsafe(main.stop)
        t.join(5)


def test_run_or_schedule_on_the_main_loop_thread_does_not_deadlock():
    async def go():
        async def inner():
            return 7

        async_compat.register_main_loop(asyncio.get_running_loop())
        return async_compat.run_or_schedule(inner())

    assert asyncio.run(asyncio.wait_for(go(), 10)) == 7


# --- redis reuse -----------------------------------------------------------


def test_async_resource_created_in_call_one_is_reused_in_call_two():
    cache: dict = {}

    async def get_client():
        if "c" not in cache:
            cache["c"] = (asyncio.get_running_loop(), asyncio.Lock())
        loop, _ = cache["c"]
        assert loop is asyncio.get_running_loop()
        return id(cache["c"])

    assert worker_loop.run_in_worker_loop(get_client()) == worker_loop.run_in_worker_loop(get_client())


def test_startup_main_loop_registration_feeds_run_or_schedule():
    """The lifespan's main-loop registration feeds both the audit middleware and the loop for run_or_schedule."""
    from initialization.main_loop import register_main_loops
    from middleware import audit_middleware

    loop = asyncio.new_event_loop()
    try:
        register_main_loops(loop)
        assert async_compat._MAIN_LOOP is loop and audit_middleware._main_event_loop is loop
    finally:
        audit_middleware._main_event_loop = None
        loop.close()
