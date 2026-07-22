# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Tests for lifespan shutdown ordering (#11679).

Covers the fast-shutdown race between phase-2 background initialization and
cleanup_services(), and the executor-drain-before-Redis-close ordering.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import initialization.lifespan as lifespan_module
from initialization.lifespan import cleanup_services


@pytest.mark.asyncio
async def test_cleanup_cancels_background_init_task_first():
    """Fast-shutdown race (#11679): the phase-2 task must be cancelled and
    awaited before any other cleanup step, and must not leak as an orphan
    task once cleanup_services() returns."""
    still_running = asyncio.Event()

    async def _slow_phase2() -> None:
        still_running.set()
        await asyncio.sleep(30)

    task = asyncio.create_task(_slow_phase2(), name="phase2_background_init")
    await still_running.wait()

    app = SimpleNamespace(state=SimpleNamespace(background_init_task=task))

    with (
        patch("autobot_shared.redis_client.close_all_redis_connections", new=AsyncMock()),
        patch.object(lifespan_module, "shutdown_tracing", new=AsyncMock()),
    ):
        await cleanup_services(app)

    assert task.done()
    assert task.cancelled()
    # No orphan phase-2 task left running after cleanup completes.
    remaining = [t for t in asyncio.all_tasks() if t.get_name() == "phase2_background_init"]
    assert remaining == []


@pytest.mark.asyncio
async def test_cleanup_drains_executor_before_redis_close():
    """Ordering decision (#11679): the bounded thread-pool executor must be
    drained BEFORE Redis pools close, so queued sync jobs (e.g.
    chat_history/cache.py's setex offload) cannot touch Redis after the
    pools are gone."""
    call_order: list[str] = []

    executor = ThreadPoolExecutor(max_workers=1)
    lifespan_module._executor = executor

    async def _fake_redis_close() -> None:
        call_order.append("redis_close")

    def _fake_shutdown(*_args, **_kwargs) -> None:
        call_order.append("executor_shutdown")

    app = SimpleNamespace(state=SimpleNamespace())

    with (
        patch("autobot_shared.redis_client.close_all_redis_connections", new=_fake_redis_close),
        patch.object(executor, "shutdown", side_effect=_fake_shutdown),
        patch.object(lifespan_module, "shutdown_tracing", new=AsyncMock()),
    ):
        await cleanup_services(app)

    assert call_order == ["executor_shutdown", "redis_close"]

    lifespan_module._executor = None
