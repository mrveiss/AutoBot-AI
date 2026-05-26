# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for NPU pulse-probe correctness check (GH#6739).

Covers:
- Consecutive pulse failures → DEGRADED state
- Continued failures → OFFLINE (unhealthy)
- Recovery: clean pulse after DEGRADED → ONLINE
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.npu_models import NPUWorkerConfig, NPUWorkerStatus, WorkerStatus
from services.npu_worker_manager import NPUWorkerManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_worker_config(worker_id: str = "test-worker-1") -> NPUWorkerConfig:
    return NPUWorkerConfig(
        id=worker_id,
        name="Test Worker",
        url="http://127.0.0.1:8099",
        enabled=True,
        priority=5,
    )


def _make_manager(redis_client=None) -> NPUWorkerManager:
    """Construct an NPUWorkerManager with __init__ bypassed for heavy I/O."""
    mgr = NPUWorkerManager.__new__(NPUWorkerManager)
    mgr._workers = {}
    mgr._worker_clients = {}
    mgr._health_check_task = None
    mgr._failover_monitor_task = None
    mgr._pulse_task = None
    mgr._running = False
    mgr._load_balancing_config = MagicMock()
    mgr._load_balancing_config.health_check_interval = 30
    mgr._load_balancing_config.timeout_seconds = 10
    mgr._worker_failure_counts = {}
    mgr._worker_next_check = {}
    mgr._pulse_failure_counts = {}
    mgr._pulse_canaries = {
        "default": {
            "match_prefixes": [],
            "canary_prompt": "Reply with exactly: PULSE_OK",
            "expected_token": "PULSE_OK",
        }
    }
    mgr._pulse_defaults = {
        "pulse_interval_seconds": 300,
        "pulse_timeout_seconds": 30,
        "degrade_after_failures": 3,
        "unhealthy_after_failures": 5,
        "latency_window": 20,
        "latency_throttle_multiplier": 3.0,
    }
    mgr.redis_client = redis_client
    mgr.config_file = Path("config/npu_workers.yaml")
    return mgr


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mgr():
    m = _make_manager()
    cfg = _make_worker_config()
    m._workers[cfg.id] = cfg
    return m


@pytest.fixture
def online_status():
    return NPUWorkerStatus(id="test-worker-1", status=WorkerStatus.ONLINE)


@pytest.fixture
def degraded_status():
    return NPUWorkerStatus(
        id="test-worker-1",
        status=WorkerStatus.DEGRADED,
        error_message="Pulse-probe: 3 consecutive failures (last: timeout)",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pulse_failure_leads_to_degraded(mgr, online_status):
    """K consecutive failures should mark the worker DEGRADED."""
    worker_id = "test-worker-1"
    degrade_k = int(mgr._pulse_defaults["degrade_after_failures"])

    client_mock = AsyncMock()
    client_mock.get_available_models = AsyncMock(return_value={"models": ["gemma-3-4b"]})
    client_mock.run_inference = AsyncMock(return_value={"error": "model load failed"})
    mgr._worker_clients[worker_id] = client_mock

    stored_statuses = []

    async def fake_get_status(wid):
        if stored_statuses:
            return stored_statuses[-1]
        return online_status

    async def fake_store_emit(wid, status, prev):
        stored_statuses.append(status)

    mgr._get_worker_status = fake_get_status
    mgr._store_and_emit_status = fake_store_emit

    # Accumulate degrade_k failures
    for _ in range(degrade_k):
        await mgr._pulse_check_worker(worker_id)

    assert mgr._pulse_failure_counts[worker_id] == degrade_k
    last = stored_statuses[-1]
    assert last.status == WorkerStatus.DEGRADED


@pytest.mark.asyncio
async def test_pulse_failure_leads_to_unhealthy(mgr, online_status):
    """M consecutive failures should mark the worker OFFLINE."""
    worker_id = "test-worker-1"
    unhealthy_m = int(mgr._pulse_defaults["unhealthy_after_failures"])

    client_mock = AsyncMock()
    client_mock.get_available_models = AsyncMock(return_value={"models": ["gemma-3-4b"]})
    client_mock.run_inference = AsyncMock(return_value={"error": "inference failed"})
    mgr._worker_clients[worker_id] = client_mock

    stored_statuses = []

    async def fake_get_status(wid):
        if stored_statuses:
            return stored_statuses[-1]
        return online_status

    async def fake_store_emit(wid, status, prev):
        stored_statuses.append(status)

    mgr._get_worker_status = fake_get_status
    mgr._store_and_emit_status = fake_store_emit

    for _ in range(unhealthy_m):
        await mgr._pulse_check_worker(worker_id)

    assert mgr._pulse_failure_counts[worker_id] == unhealthy_m
    last = stored_statuses[-1]
    assert last.status == WorkerStatus.OFFLINE


@pytest.mark.asyncio
async def test_pulse_recovery_from_degraded(mgr, degraded_status):
    """A successful pulse after DEGRADED should restore the worker to ONLINE."""
    worker_id = "test-worker-1"

    client_mock = AsyncMock()
    client_mock.get_available_models = AsyncMock(return_value={"models": ["gemma-3-4b"]})
    client_mock.run_inference = AsyncMock(return_value={"output": "PULSE_OK"})
    mgr._worker_clients[worker_id] = client_mock

    # Seed pre-existing failure count at degrade threshold
    mgr._pulse_failure_counts[worker_id] = int(mgr._pulse_defaults["degrade_after_failures"])

    stored_statuses = []

    async def fake_get_status(wid):
        return degraded_status

    async def fake_store_emit(wid, status, prev):
        stored_statuses.append(status)

    async def fake_store_latency(wid, mid, lat):
        pass

    async def fake_pool_median(mid):
        return None

    async def fake_p95(wid, mid):
        return None

    mgr._get_worker_status = fake_get_status
    mgr._store_and_emit_status = fake_store_emit
    mgr._store_pulse_latency = fake_store_latency
    mgr._get_pool_median_latency = fake_pool_median
    mgr._get_pulse_p95_latency = fake_p95

    await mgr._pulse_check_worker(worker_id)

    # Failure counter cleared
    assert worker_id not in mgr._pulse_failure_counts
    # Status restored to ONLINE
    assert stored_statuses[-1].status == WorkerStatus.ONLINE


@pytest.mark.asyncio
async def test_pulse_skips_offline_worker(mgr):
    """Workers that are already OFFLINE should not be probed."""
    worker_id = "test-worker-1"
    offline_status = NPUWorkerStatus(id=worker_id, status=WorkerStatus.OFFLINE)

    client_mock = AsyncMock()
    mgr._worker_clients[worker_id] = client_mock

    async def fake_get_status(wid):
        return offline_status

    mgr._get_worker_status = fake_get_status

    await mgr._pulse_check_worker(worker_id)

    # No inference should be attempted
    client_mock.run_inference.assert_not_called()
    client_mock.get_available_models.assert_not_called()


@pytest.mark.asyncio
async def test_get_healthy_workers_sorted_puts_degraded_last(mgr):
    """get_healthy_workers_sorted should return ONLINE workers before DEGRADED."""
    from models.npu_models import NPUWorkerDetails

    worker_a = NPUWorkerDetails(
        config=_make_worker_config("worker-a"),
        status=NPUWorkerStatus(id="worker-a", status=WorkerStatus.ONLINE),
    )
    worker_b = NPUWorkerDetails(
        config=_make_worker_config("worker-b"),
        status=NPUWorkerStatus(id="worker-b", status=WorkerStatus.DEGRADED),
    )
    worker_c = NPUWorkerDetails(
        config=_make_worker_config("worker-c"),
        status=NPUWorkerStatus(id="worker-c", status=WorkerStatus.OFFLINE),
    )

    async def fake_list_workers():
        return [worker_a, worker_b, worker_c]

    mgr.list_workers = fake_list_workers

    result = await mgr.get_healthy_workers_sorted()
    assert len(result) == 2  # OFFLINE excluded
    assert result[0].config.id == "worker-a"
    assert result[1].config.id == "worker-b"
