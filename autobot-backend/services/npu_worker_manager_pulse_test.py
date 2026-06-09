# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for NPU pulse-probe correctness check (GH#6739).

Covers:
- Consecutive pulse failures → DEGRADED state
- Continued failures → OFFLINE (unhealthy)
- Recovery: clean pulse after DEGRADED → ONLINE
- MVA-1399: Heartbeat reachability — stale last_heartbeat → failure class
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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


# ---------------------------------------------------------------------------
# MVA-1399: Heartbeat reachability tests
# ---------------------------------------------------------------------------


def _status_with_heartbeat(age_seconds: float, worker_id: str = "test-worker-1") -> NPUWorkerStatus:
    """Build an ONLINE NPUWorkerStatus whose last_heartbeat is age_seconds old."""
    last_hb = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return NPUWorkerStatus(id=worker_id, status=WorkerStatus.ONLINE, last_heartbeat=last_hb)


def test_check_heartbeat_reachability_fresh(mgr):
    """A heartbeat within the silence window should return None (reachable)."""
    status = _status_with_heartbeat(age_seconds=60)  # 60 s old, threshold 600 s
    result = mgr._check_heartbeat_reachability("test-worker-1", status)
    assert result is None


def test_check_heartbeat_reachability_stale(mgr):
    """A heartbeat older than the threshold should return 'heartbeat_stale'."""
    status = _status_with_heartbeat(age_seconds=700)  # 700 s > 600 s threshold
    result = mgr._check_heartbeat_reachability("test-worker-1", status)
    assert result == "heartbeat_stale"


def test_check_heartbeat_reachability_no_baseline(mgr):
    """A worker with last_heartbeat=None has no baseline — check is skipped."""
    status = NPUWorkerStatus(id="test-worker-1", status=WorkerStatus.ONLINE, last_heartbeat=None)
    result = mgr._check_heartbeat_reachability("test-worker-1", status)
    assert result is None


def test_check_heartbeat_reachability_disabled(mgr):
    """Setting heartbeat_max_silence_seconds to 0 disables the check."""
    mgr._pulse_defaults["heartbeat_max_silence_seconds"] = 0
    status = _status_with_heartbeat(age_seconds=9999)
    result = mgr._check_heartbeat_reachability("test-worker-1", status)
    assert result is None


def test_check_heartbeat_reachability_naive_datetime(mgr):
    """A tz-naive last_heartbeat is normalised safely; stale naive dt → stale."""
    naive_old = datetime.utcnow() - timedelta(seconds=700)
    status = NPUWorkerStatus(id="test-worker-1", status=WorkerStatus.ONLINE, last_heartbeat=naive_old)
    result = mgr._check_heartbeat_reachability("test-worker-1", status)
    assert result == "heartbeat_stale"


@pytest.mark.asyncio
async def test_stale_heartbeat_accumulates_failures_toward_degraded(mgr, online_status):
    """K consecutive stale-heartbeat checks should mark the worker DEGRADED."""
    worker_id = "test-worker-1"
    degrade_k = int(mgr._pulse_defaults["degrade_after_failures"])
    mgr._pulse_defaults["heartbeat_max_silence_seconds"] = 600

    stale_status = _status_with_heartbeat(age_seconds=700)
    stored_statuses = []

    async def fake_get_status(wid):
        return stale_status

    async def fake_store_emit(wid, status, prev):
        stored_statuses.append(status)

    mgr._get_worker_status = fake_get_status
    mgr._store_and_emit_status = fake_store_emit

    for _ in range(degrade_k):
        await mgr._pulse_check_worker(worker_id)

    assert mgr._pulse_failure_counts[worker_id] == degrade_k
    assert stored_statuses[-1].status == WorkerStatus.DEGRADED


@pytest.mark.asyncio
async def test_stale_heartbeat_does_not_invoke_inference(mgr):
    """A stale-heartbeat short-circuit must not call get_available_models or run_inference."""
    worker_id = "test-worker-1"
    mgr._pulse_defaults["heartbeat_max_silence_seconds"] = 600

    stale_status = _status_with_heartbeat(age_seconds=700)
    client_mock = AsyncMock()
    mgr._worker_clients[worker_id] = client_mock

    async def fake_get_status(wid):
        return stale_status

    async def fake_store_emit(wid, status, prev):
        pass

    mgr._get_worker_status = fake_get_status
    mgr._store_and_emit_status = fake_store_emit

    await mgr._pulse_check_worker(worker_id)

    client_mock.get_available_models.assert_not_called()
    client_mock.run_inference.assert_not_called()


@pytest.mark.asyncio
async def test_fresh_heartbeat_proceeds_to_inference(mgr, online_status):
    """A fresh heartbeat should not short-circuit; inference must be attempted."""
    worker_id = "test-worker-1"
    mgr._pulse_defaults["heartbeat_max_silence_seconds"] = 600

    fresh_status = _status_with_heartbeat(age_seconds=60)
    client_mock = AsyncMock()
    client_mock.get_available_models = AsyncMock(return_value={"models": ["gemma-3-4b"]})
    client_mock.run_inference = AsyncMock(return_value={"output": "PULSE_OK"})
    mgr._worker_clients[worker_id] = client_mock

    async def fake_get_status(wid):
        return fresh_status

    async def fake_store_emit(wid, status, prev):
        pass

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

    client_mock.get_available_models.assert_called_once()
    client_mock.run_inference.assert_called_once()
