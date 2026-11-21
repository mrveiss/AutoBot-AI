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
from autobot_shared.logging_once import reset_log_once

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


def test_fallback_on_the_main_loop_thread_warns_once_per_call_site(monkeypatch):
    """The residue is visible: a fixed message plus the caller, once per site, and the work still runs."""
    logged: list[tuple] = []
    monkeypatch.setattr(async_compat, "_log_threadsafe", lambda level, msg, *a: logged.append((level, msg, a)))
    reset_log_once()

    def sync_caller():
        async def inner():
            return 7

        return async_compat.run_or_schedule(inner())

    async def go():
        async_compat.register_main_loop(asyncio.get_running_loop())
        return [sync_caller(), sync_caller()]

    assert asyncio.run(asyncio.wait_for(go(), 10)) == [7, 7]
    assert len(logged) == 1
    level, msg, args = logged[0]
    assert level == "warning" and "falling back" in msg
    assert args == (__name__, "sync_caller")


def test_child_reset_replaces_a_lock_held_at_fork_time():
    held = worker_loop._STATE_LOCK
    assert held.acquire(blocking=False)
    try:
        worker_loop._reset_state_in_child()
        fresh = worker_loop._STATE_LOCK
        assert fresh is not held
        assert fresh.acquire(blocking=False)
        fresh.release()
    finally:
        held.release()


def test_run_on_loop_times_out_cancels_and_names_the_coroutine(monkeypatch):
    cancelled = threading.Event()

    async def never_finishes():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(worker_loop, "WORKER_LOOP_RUN_TIMEOUT", 0.2)
    loop = worker_loop.start_worker_loop()
    with pytest.raises(TimeoutError, match="never_finishes"):
        worker_loop.run_on_loop(never_finishes(), loop)
    assert cancelled.wait(5)


def test_run_on_loop_surfaces_the_coroutines_own_timeout_unchanged():
    async def raises_inner():
        raise TimeoutError("inner")

    loop = worker_loop.start_worker_loop()
    with pytest.raises(TimeoutError) as info:
        worker_loop.run_on_loop(raises_inner(), loop)
    assert str(info.value) == "inner"


def test_run_in_worker_loop_defaults_to_the_bounded_run_timeout(monkeypatch):
    cancelled = threading.Event()

    async def never_finishes():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(worker_loop, "WORKER_LOOP_RUN_TIMEOUT", 0.2)
    with pytest.raises(Exception):
        worker_loop.run_in_worker_loop(never_finishes())
    assert cancelled.wait(5)


@pytest.mark.parametrize(
    "bad,expected",
    [("-1", 3600.0), ("0", 3600.0), ("nan", 3600.0), ("inf", 3600.0), ("0.01", 0.1), ("999999", 86400.0)],
)
def test_run_timeout_env_rejects_values_that_would_expire_tasks(monkeypatch, bad, expected):
    import importlib

    monkeypatch.setenv("AUTOBOT_WORKER_LOOP_RUN_TIMEOUT", bad)
    try:
        reloaded = importlib.reload(worker_loop)
        assert 0.1 <= reloaded.WORKER_LOOP_RUN_TIMEOUT <= 86400.0
        assert reloaded.WORKER_LOOP_RUN_TIMEOUT == expected
    finally:
        monkeypatch.delenv("AUTOBOT_WORKER_LOOP_RUN_TIMEOUT")
        importlib.reload(worker_loop)


def test_late_starting_loop_thread_is_stopped_and_tracked(monkeypatch):
    """A thread that starts only after the startup timeout must exit, not serve forever."""
    gate = threading.Event()
    real_main = worker_loop._loop_main
    real_abandon = worker_loop._abandon_slow_loop
    tracked: list[threading.Thread] = []

    def track_abandoned(loop, thread):
        tracked.append(thread)
        real_abandon(loop, thread)

    monkeypatch.setattr(worker_loop, "WORKER_LOOP_START_TIMEOUT", 0.05)
    monkeypatch.setattr(worker_loop, "_loop_main", lambda loop, ready: (gate.wait(10), real_main(loop, ready)))
    monkeypatch.setattr(worker_loop, "_abandon_slow_loop", track_abandoned)
    try:
        with pytest.raises(RuntimeError, match="did not start in time"):
            worker_loop._spawn_loop()
        assert len(tracked) == 1
        assert tracked[0] in worker_loop._ABANDONED_THREADS
    finally:
        gate.set()
        for thread in tracked:
            thread.join(10)
    assert not tracked[0].is_alive()


def test_abandoned_threads_that_exited_are_pruned(monkeypatch):
    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()
    live_gate = threading.Event()
    live = threading.Thread(target=live_gate.wait, args=(10,), daemon=True)
    live.start()
    loop = asyncio.new_event_loop()
    monkeypatch.setattr(worker_loop, "_ABANDONED_THREADS", [dead, live])
    try:
        worker_loop._abandon_slow_loop(loop, live)
        assert dead not in worker_loop._ABANDONED_THREADS
        assert live in worker_loop._ABANDONED_THREADS
    finally:
        live_gate.set()
        live.join(10)
        loop.close()


def test_stalled_first_disposer_does_not_skip_the_others(monkeypatch):
    ran: list[str] = []

    async def hang():
        await asyncio.sleep(60)

    async def ok_t():
        ran.append("transcriber")

    async def ok_r():
        ran.append("redis")

    import importlib

    monkeypatch.setattr(
        worker_loop, "_DISPOSERS", (("database", "m", "a"), ("transcriber", "m", "b"), ("redis", "m", "c"))
    )
    attrs = {"a": hang, "b": ok_t, "c": ok_r}
    monkeypatch.setattr(importlib, "import_module", lambda m: type("M", (), attrs))
    asyncio.run(asyncio.wait_for(worker_loop._dispose_shared_resources(0.6), 10))
    assert ran == ["transcriber", "redis"]


def _patch_disposers(monkeypatch, attrs):
    import importlib

    monkeypatch.setattr(worker_loop, "_DISPOSERS", tuple((f"d{i}", "m", k) for i, k in enumerate(attrs)))
    monkeypatch.setattr(importlib, "import_module", lambda m: type("M", (), attrs))


def test_fast_disposer_passes_its_leftover_to_the_next(monkeypatch):
    shares: list[float] = []
    real = worker_loop._run_disposer

    async def spy(name, step, share):
        shares.append(share)
        await real(name, step, share)

    async def fast():
        return None

    monkeypatch.setattr(worker_loop, "_run_disposer", spy)
    _patch_disposers(monkeypatch, {"a": fast, "b": fast, "c": fast})
    asyncio.run(worker_loop._dispose_shared_resources(30.0))
    assert shares[0] == pytest.approx(10.0, abs=0.1)
    assert shares[1] == pytest.approx(15.0, abs=0.1)
    assert shares[2] == pytest.approx(30.0, abs=0.2)


def test_disposer_swallowing_cancellation_cannot_overrun_the_budget(monkeypatch):
    release = threading.Event()

    async def stubborn():
        while not release.is_set():
            try:
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                continue

    async def ok():
        return None

    _patch_disposers(monkeypatch, {"a": stubborn, "b": stubborn, "c": ok})

    async def run():
        loop = asyncio.get_running_loop()
        start = loop.time()
        await worker_loop._dispose_shared_resources(0.6)
        elapsed = loop.time() - start
        release.set()  # let the abandoned tasks finish so asyncio.run can close
        return elapsed

    assert asyncio.run(asyncio.wait_for(run(), 10)) < 1.0
