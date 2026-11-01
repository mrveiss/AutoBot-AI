# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The approval expiry sweep is scheduled, and a failed sweep does not stop it (#18412)."""

import asyncio
from types import SimpleNamespace

import pytest

from services import approval_expiry_scheduler as mod
from services.approval_gate_service import ApprovalGateService


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def sweeps(monkeypatch):
    calls = []
    import user_management.database as db

    monkeypatch.setattr(db, "get_async_session_factory", lambda: lambda: _Session())

    async def expire_stale(self):
        calls.append(1)
        return 0

    monkeypatch.setattr(ApprovalGateService, "expire_stale", expire_stale)
    return calls


@pytest.mark.asyncio
async def test_a_tick_runs_one_sweep(sweeps):
    await mod.ApprovalExpiryScheduler(poll_interval=60)._tick()
    assert sweeps == [1]


@pytest.mark.asyncio
async def test_a_failing_sweep_is_survived_and_the_next_tick_runs(monkeypatch, sweeps):
    outcomes = [RuntimeError("db down"), 1]

    async def expire_stale(self):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(ApprovalGateService, "expire_stale", expire_stale)
    scheduler = mod.ApprovalExpiryScheduler(poll_interval=60)
    await scheduler._tick()  # must not raise
    await scheduler._tick()
    assert outcomes == []


@pytest.mark.asyncio
async def test_the_started_loop_keeps_sweeping_after_an_error(monkeypatch):
    import user_management.database as db

    monkeypatch.setattr(db, "get_async_session_factory", lambda: lambda: _Session())
    ran = asyncio.Event()
    count = {"n": 0}

    async def expire_stale(self):
        count["n"] += 1
        if count["n"] == 1:
            raise RuntimeError("first sweep fails")
        ran.set()
        return 0

    monkeypatch.setattr(ApprovalGateService, "expire_stale", expire_stale)
    app = SimpleNamespace(state=SimpleNamespace())
    monkeypatch.setattr(mod, "APPROVAL_EXPIRY_SWEEP_INTERVAL_S", 0.01)
    scheduler = mod.ApprovalExpiryScheduler(poll_interval=0.01)
    app.state.approval_expiry_scheduler = scheduler
    scheduler.start()
    await asyncio.wait_for(ran.wait(), timeout=5)
    await mod.stop_approval_expiry_scheduler(app)
    assert count["n"] >= 2 and not scheduler.is_running


@pytest.mark.asyncio
async def test_startup_stores_the_scheduler_and_shutdown_drains_it(monkeypatch, sweeps):
    app = SimpleNamespace(state=SimpleNamespace())
    await mod.start_approval_expiry_scheduler(app)
    assert app.state.approval_expiry_scheduler.is_running
    await mod.stop_approval_expiry_scheduler(app)
    assert not app.state.approval_expiry_scheduler.is_running


@pytest.mark.asyncio
async def test_background_workers_starts_it(monkeypatch):
    from initialization import background_workers as bw

    started = []
    for name in (
        "start_doc_sync_queue_worker",
        "start_vector_reconciler",
        "start_telegram_poller",
        "start_schedule_reconciler",
    ):
        monkeypatch.setattr(bw, name, lambda app: asyncio.sleep(0))
    monkeypatch.setattr(bw, "wire_llm_service", lambda app: None)

    async def start(app):
        started.append(app)

    monkeypatch.setattr(mod, "start_approval_expiry_scheduler", start)
    await bw.start_background_workers("app")
    assert started == ["app"]


def test_the_interval_is_an_env_backed_registered_constant():
    from autobot_shared.env_registry import REGISTRY as ENV_REGISTRY

    assert "AUTOBOT_APPROVAL_EXPIRY_SWEEP_INTERVAL_S" in ENV_REGISTRY
    assert mod.APPROVAL_EXPIRY_SWEEP_INTERVAL_S >= 1.0
