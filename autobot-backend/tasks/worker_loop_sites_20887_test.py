# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20887: every migrated Celery task runs its coroutine on ONE persistent loop.

Each case replaces the task's async body with a coroutine that records the running
loop and touches a loop-bound resource (a connection that refuses reuse once its
loop is closed). The task is called twice: with a private loop per call the second
call fails; on the worker loop both succeed on the same loop.
"""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

import pytest

from autobot_shared import worker_loop

# (module, task attribute, async-body attribute, task kwargs)
SITES: list[tuple[str, str, str, dict[str, Any]]] = [
    ("llc.scheduler.workspace_lease_sweep", "run_workspace_lease_sweep", "_async_sweep", {}),
    ("llc.scheduler.stalled_run_sweep", "run_stalled_run_sweep", "_async_sweep", {}),
    ("llc.scheduler.trigger_secret_audit", "run_trigger_secret_audit", "_async_audit", {}),
    ("llc.scheduler.project_disposal_sweep", "run_disposal_sweep", "_async_sweep", {}),
    ("llc.scheduler.sprint_autoclose", "run_daily_check", "_async_check", {}),
    ("tasks.credential_reconcile", "reconcile_credentials", "_run", {}),
    ("tasks.mobile_device_tasks", "cleanup_stale_mobile_devices", "_cleanup_stale_devices_async", {}),
    ("tasks.transcriber_tasks", "transcribe_recording", "_run_pipeline", {"recording_id": 1}),
    ("tasks.audit_log_retention", "cleanup_expired_audit_logs", "_async_cleanup_expired_audit_logs", {}),
    ("tasks.chat_retention", "cleanup_expired_chats", "_async_cleanup_expired_chats", {}),
    ("tasks.knowledge_retention", "cleanup_expired_kb_entries", "_async_cleanup_expired_kb_entries", {}),
    ("workers.consolidate_tasks", "consolidate_trajectories", "_run_consolidation", {}),
    ("workers.consolidate_tasks", "consolidate_facts", "_run_facts_consolidation", {}),
    ("llc.scheduler.attachment_file_sweep", "run_attachment_file_sweep", "_async_sweep", {}),
    ("tasks.snapshot_cleanup", "cleanup_expired_snapshots", "_async_cleanup_expired_snapshots", {}),
]


class LoopBoundResource:
    """Stands in for a pooled connection: usable only while its opening loop is open."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.seen: list[int] = []

    def use(self) -> int:
        running = asyncio.get_running_loop()
        if self.loop is None:
            self.loop = running
        if self.loop.is_closed():
            raise RuntimeError("Event loop is closed")
        self.seen.append(id(running))
        return id(running)


@pytest.fixture(autouse=True)
def _clean_worker_loop():
    worker_loop.stop_worker_loop()
    yield
    worker_loop.stop_worker_loop()


def _task_and_body(modname: str, task_attr: str, body_attr: str, monkeypatch, resource):
    module = importlib.import_module(modname)

    async def fake_body(*args, **kwargs):
        return {"loop": resource.use(), "ok": True}

    monkeypatch.setattr(module, body_attr, fake_body)
    return getattr(module, task_attr)


@pytest.mark.parametrize("modname,task_attr,body_attr,kwargs", SITES, ids=[f"{s[0]}:{s[1]}" for s in SITES])
def test_task_runs_twice_on_the_same_worker_loop(modname, task_attr, body_attr, kwargs, monkeypatch):
    resource = LoopBoundResource()
    task = _task_and_body(modname, task_attr, body_attr, monkeypatch, resource)
    task.run(**kwargs)
    task.run(**kwargs)
    assert resource.seen == [id(worker_loop.get_worker_loop())] * 2


def test_analytics_run_async_uses_the_worker_loop_and_drains_spawned_tasks():
    from tasks.analytics_tasks import _run_async

    drained: list[str] = []

    async def work():
        async def side():
            await asyncio.sleep(0.05)
            drained.append("done")

        asyncio.get_running_loop().create_task(side())
        return id(asyncio.get_running_loop())

    first = _run_async(work())
    second = _run_async(work())
    assert first == second == id(worker_loop.get_worker_loop())
    assert drained == ["done", "done"]


def test_knowledge_helper_does_not_reset_the_redis_pools_per_call(monkeypatch):
    from autobot_shared import redis_client
    from tasks.knowledge_tasks import _run_async_in_loop

    resets: list[int] = []
    monkeypatch.setattr(redis_client, "reset_async_redis_pools", lambda: resets.append(1))

    async def body():
        return id(asyncio.get_running_loop())

    assert _run_async_in_loop(body()) == _run_async_in_loop(body())
    assert resets == []


def test_memory_tasks_use_the_worker_loop(monkeypatch):
    from tasks import memory_tasks

    seen: list[int] = []

    async def fake_write(*args, **kwargs):
        seen.append(id(asyncio.get_running_loop()))
        return "chunk"

    monkeypatch.setattr(memory_tasks, "_async_write_verbatim", fake_write)
    task = memory_tasks.write_verbatim_task
    task.run("s", 1, "user", "t", "2026-01-01T00:00:00Z", None)
    task.run("s", 2, "user", "t", "2026-01-01T00:00:00Z", None)
    assert len(set(seen)) == 1 and seen[0] == id(worker_loop.get_worker_loop())


def test_push_notification_dispatch_runs_on_the_worker_loop(monkeypatch):
    import threading

    from services import push_notification_service as svc

    seen: list[int] = []
    done = threading.Event()

    async def fake_send(**kwargs):
        seen.append(id(asyncio.get_running_loop()))
        done.set()

    monkeypatch.setattr(svc, "send_push_notification", fake_send)
    handlers = []
    from celery import signals

    monkeypatch.setattr(signals.task_success, "connect", lambda fn: handlers.append(fn) or fn)
    svc.register_celery_task_success_hook()
    handlers[0](sender=type("T", (), {"name": "t"})(), result=None, kwargs={"user_id": "u1"})
    assert done.wait(5)
    assert seen == [id(worker_loop.get_worker_loop())]
