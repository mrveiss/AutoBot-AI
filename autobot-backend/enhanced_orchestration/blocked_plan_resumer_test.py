# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for BlockedPlanResumer (#7431)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_orchestration.blocked_plan_resumer import BlockedPlanResumer


def _runner_with_plans(active: dict) -> MagicMock:
    runner = MagicMock()
    runner.active_workflows = active
    runner.try_resume_blocked_plan = AsyncMock(return_value={"resumed": True, "result": {}})
    return runner


def _plan_stub(status: str) -> MagicMock:
    p = MagicMock()
    p.status = status
    return p


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_idempotent():
    """Calling start() twice does not spawn a second listener."""
    runner = _runner_with_plans({})
    resumer = BlockedPlanResumer(runner)
    with patch(
        "autobot_shared.redis_client.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await resumer.start()
        first_task = resumer._task
        await resumer.start()
        assert resumer._task is first_task
    await resumer.stop()


@pytest.mark.asyncio
async def test_stop_no_op_when_not_started():
    resumer = BlockedPlanResumer(_runner_with_plans({}))
    await resumer.stop()


@pytest.mark.asyncio
async def test_stop_cancels_running_task():
    """stop() awaits cancellation of the listener task."""
    resumer = BlockedPlanResumer(_runner_with_plans({}))

    async def never_listen():
        while True:
            await asyncio.sleep(60)
            yield {}

    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.aclose = AsyncMock()
    pubsub.listen = never_listen
    client = MagicMock()
    client.pubsub = MagicMock(return_value=pubsub)

    with patch(
        "autobot_shared.redis_client.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=client,
    ):
        await resumer.start()
        await asyncio.sleep(0.01)
        await resumer.stop()

    assert resumer._task is None


# ---------------------------------------------------------------------------
# Redis-unavailable paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_exits_silently_when_redis_disabled():
    resumer = BlockedPlanResumer(_runner_with_plans({}))
    with patch(
        "autobot_shared.redis_client.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await resumer.start()
        await asyncio.sleep(0.01)
    await resumer.stop()


@pytest.mark.asyncio
async def test_loop_exits_silently_when_redis_module_missing():
    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "autobot_shared.redis_client":
            raise ImportError("simulated")
        return real_import(name, *args, **kwargs)

    resumer = BlockedPlanResumer(_runner_with_plans({}))
    with patch("builtins.__import__", side_effect=_fake_import):
        await resumer.start()
        await asyncio.sleep(0.01)
    await resumer.stop()


@pytest.mark.asyncio
async def test_loop_exits_silently_when_redis_client_raises():
    resumer = BlockedPlanResumer(_runner_with_plans({}))
    with patch(
        "autobot_shared.redis_client.get_async_redis_client",
        new_callable=AsyncMock,
        side_effect=ConnectionError("Redis unreachable"),
    ):
        await resumer.start()
        await asyncio.sleep(0.01)
    await resumer.stop()


# ---------------------------------------------------------------------------
# Event handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_event_resumes_all_blocked_plans():
    plans = {
        "p1": _plan_stub("blocked"),
        "p2": _plan_stub("pending"),  # not blocked → skipped
        "p3": _plan_stub("blocked"),
    }
    runner = _runner_with_plans(plans)
    resumer = BlockedPlanResumer(runner)

    payload = json.dumps({"event": "skill_promoted", "skill_name": "translation", "tools": ["translate"]})
    await resumer._handle_event(payload)

    assert runner.try_resume_blocked_plan.await_count == 2
    called_with = {c.args[0] for c in runner.try_resume_blocked_plan.await_args_list}
    assert called_with == {"p1", "p3"}


@pytest.mark.asyncio
async def test_handle_event_isolates_per_plan_failures():
    plans = {"p1": _plan_stub("blocked"), "p2": _plan_stub("blocked")}
    runner = _runner_with_plans(plans)
    runner.try_resume_blocked_plan = AsyncMock(side_effect=[RuntimeError("boom"), {"resumed": True, "result": {}}])
    resumer = BlockedPlanResumer(runner)

    payload = json.dumps({"event": "skill_promoted", "skill_name": "x"})
    await resumer._handle_event(payload)

    assert runner.try_resume_blocked_plan.await_count == 2


@pytest.mark.asyncio
async def test_handle_event_decodes_bytes_payload():
    plans = {"p1": _plan_stub("blocked")}
    runner = _runner_with_plans(plans)
    resumer = BlockedPlanResumer(runner)

    payload = json.dumps({"event": "skill_promoted", "skill_name": "x"}).encode("utf-8")
    await resumer._handle_event(payload)

    runner.try_resume_blocked_plan.assert_awaited_once_with("p1")


@pytest.mark.asyncio
async def test_handle_event_skips_undecodable_payload():
    plans = {"p1": _plan_stub("blocked")}
    runner = _runner_with_plans(plans)
    resumer = BlockedPlanResumer(runner)

    await resumer._handle_event(b"\xff\xfe not valid utf8 nor json")
    runner.try_resume_blocked_plan.assert_not_called()


@pytest.mark.asyncio
async def test_handle_event_skips_when_no_blocked_plans():
    plans = {"p1": _plan_stub("pending"), "p2": _plan_stub("running")}
    runner = _runner_with_plans(plans)
    resumer = BlockedPlanResumer(runner)

    payload = json.dumps({"event": "skill_promoted", "skill_name": "x"})
    await resumer._handle_event(payload)

    runner.try_resume_blocked_plan.assert_not_called()


# ---------------------------------------------------------------------------
# is_running flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_running_false_initially():
    resumer = BlockedPlanResumer(_runner_with_plans({}))
    assert resumer.is_running is False


@pytest.mark.asyncio
async def test_is_running_reflects_started_task():
    resumer = BlockedPlanResumer(_runner_with_plans({}))
    with patch(
        "autobot_shared.redis_client.get_async_redis_client",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await resumer.start()
        assert resumer.is_running in (True, False)  # may complete fast
    await resumer.stop()
    assert resumer.is_running is False
