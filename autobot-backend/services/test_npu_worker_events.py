# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for NPU worker event publishing and avg_response_time_ms aggregation.

Covers (#10602 subtask 6.4, #10698):
- npu.worker.added emitted at add_worker() mutation site
- npu.worker.status.changed emitted at _store_and_emit_status() mutation site
- npu.worker.metrics.updated emitted at update_worker_status_from_heartbeat()
  mutation site, with metrics payload present in data["metrics"]
- _build_worker_metrics returns non-zero avg_response_time_ms when pulse data exists
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.npu_models import (
    NPUWorkerConfig,
    NPUWorkerDetails,
    NPUWorkerMetrics,
    NPUWorkerStatus,
    WorkerStatus,
)
from services.npu_worker_manager import NPUWorkerManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WORKER_ID = "test-worker-1"


def _make_worker_config(worker_id: str = _WORKER_ID) -> NPUWorkerConfig:
    return NPUWorkerConfig(
        id=worker_id,
        name="Test Worker",
        url="http://127.0.0.1:8099",  # canonical: ignore py-hardcoded-url — test fixture/mock URL
        enabled=True,
        priority=5,
    )


def _make_status(
    worker_id: str = _WORKER_ID,
    ws: WorkerStatus = WorkerStatus.ONLINE,
) -> NPUWorkerStatus:
    return NPUWorkerStatus(
        id=worker_id,
        status=ws,
        total_tasks_completed=100,
        total_tasks_failed=2,
        uptime_seconds=3600.0,
        current_load=1,
    )


def _make_metrics(worker_id: str = _WORKER_ID) -> NPUWorkerMetrics:
    return NPUWorkerMetrics(
        id=worker_id,
        success_rate=98.0,
        requests_per_minute=1.65,
        peak_load=1,
        avg_response_time_ms=123.4,
    )


def _make_manager(redis_client=None) -> NPUWorkerManager:
    """Construct NPUWorkerManager with __init__ bypassed for heavy I/O."""
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
    mgr._pulse_canaries = {}
    mgr._pulse_defaults = {"latency_window": 20}
    mgr.redis_client = redis_client
    mgr.config_file = Path("config/npu_workers.yaml")
    return mgr


def _make_worker_details(
    worker_id: str = _WORKER_ID,
    ws: WorkerStatus = WorkerStatus.ONLINE,
    metrics: NPUWorkerMetrics | None = None,
) -> NPUWorkerDetails:
    return NPUWorkerDetails(
        config=_make_worker_config(worker_id),
        status=_make_status(worker_id, ws),
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# Part A — npu.worker.added
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_added_event_published_at_add_worker():
    """add_worker() must publish npu.worker.added with the correct payload."""
    mgr = _make_manager()
    cfg = _make_worker_config()
    worker_details = _make_worker_details()

    published_calls = []

    async def fake_publish(channel, event_type, payload, *, persist):
        published_calls.append((channel, event_type, payload))

    # Stub collaborators so add_worker() reaches _emit_worker_event
    mgr.test_worker_connection = AsyncMock(
        return_value=MagicMock(success=True, error_message=None)
    )
    mgr._check_worker_health = AsyncMock()
    mgr._save_workers_to_config = AsyncMock()
    mgr.get_worker = AsyncMock(return_value=worker_details)

    with patch("services.npu_worker_manager.publish_event", side_effect=fake_publish):
        await mgr.add_worker(cfg)

    event_types = [et for _, et, _ in published_calls]
    assert "npu.worker.added" in event_types, f"npu.worker.added not published; got {event_types}"

    added_payload = next(p for _, et, p in published_calls if et == "npu.worker.added")
    assert added_payload["event"] == "worker.added"
    assert added_payload["worker_id"] == _WORKER_ID
    # Full worker dict is included (worker.added in _WORKER_FULL_DATA_EVENTS)
    assert "worker" in added_payload, "Full worker dict must be present in npu.worker.added payload"


# ---------------------------------------------------------------------------
# Part A — npu.worker.status.changed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_status_changed_event_published_at_store_and_emit_status():
    """_store_and_emit_status() must publish npu.worker.status.changed when status changes."""
    mgr = _make_manager()
    cfg = _make_worker_config()
    mgr._workers[_WORKER_ID] = cfg

    new_status = _make_status(ws=WorkerStatus.OFFLINE)
    worker_details = _make_worker_details(ws=WorkerStatus.OFFLINE)

    published_calls = []

    async def fake_publish(channel, event_type, payload, *, persist):
        published_calls.append((channel, event_type, payload))

    mgr._store_worker_status = AsyncMock()
    mgr.get_worker = AsyncMock(return_value=worker_details)

    with patch("services.npu_worker_manager.publish_event", side_effect=fake_publish):
        await mgr._store_and_emit_status(
            _WORKER_ID,
            new_status,
            WorkerStatus.ONLINE,  # prev != new → should emit
        )

    event_types = [et for _, et, _ in published_calls]
    assert "npu.worker.status.changed" in event_types, (
        f"npu.worker.status.changed not published; got {event_types}"
    )

    status_payload = next(p for _, et, p in published_calls if et == "npu.worker.status.changed")
    assert status_payload["event"] == "worker.status.changed"
    assert status_payload["worker_id"] == _WORKER_ID
    # worker.status.changed is now in _WORKER_FULL_DATA_EVENTS (#10602 6.4)
    assert "worker" in status_payload, (
        "Full worker dict must be present in npu.worker.status.changed payload"
    )


@pytest.mark.asyncio
async def test_worker_status_unchanged_does_not_publish_status_changed():
    """_store_and_emit_status() must NOT publish when status is unchanged."""
    mgr = _make_manager()
    mgr._store_worker_status = AsyncMock()

    published_calls = []

    async def fake_publish(channel, event_type, payload, *, persist):
        published_calls.append(event_type)

    with patch("services.npu_worker_manager.publish_event", side_effect=fake_publish):
        await mgr._store_and_emit_status(
            _WORKER_ID,
            _make_status(ws=WorkerStatus.ONLINE),
            WorkerStatus.ONLINE,  # same status → no emit
        )

    assert "npu.worker.status.changed" not in published_calls


# ---------------------------------------------------------------------------
# Part A — npu.worker.metrics.updated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_metrics_updated_event_published_at_heartbeat():
    """update_worker_status_from_heartbeat() must publish npu.worker.metrics.updated."""
    mgr = _make_manager()
    cfg = _make_worker_config()
    mgr._workers[_WORKER_ID] = cfg

    metrics = _make_metrics()
    worker_details = _make_worker_details(metrics=metrics)

    published_calls = []

    async def fake_publish(channel, event_type, payload, *, persist):
        published_calls.append((channel, event_type, payload))

    heartbeat = MagicMock()
    heartbeat.worker_id = _WORKER_ID
    heartbeat.status = "online"
    heartbeat.current_load = 1
    heartbeat.total_tasks_completed = 100
    heartbeat.total_tasks_failed = 2
    heartbeat.uptime_seconds = 3600.0

    mgr._store_worker_status = AsyncMock()
    mgr._store_worker_metrics = AsyncMock()
    mgr._build_worker_metrics = AsyncMock(return_value=metrics)
    mgr.get_worker = AsyncMock(return_value=worker_details)

    with patch("services.npu_worker_manager.publish_event", side_effect=fake_publish):
        await mgr.update_worker_status_from_heartbeat(heartbeat)

    event_types = [et for _, et, _ in published_calls]
    assert "npu.worker.metrics.updated" in event_types, (
        f"npu.worker.metrics.updated not published; got {event_types}"
    )

    metrics_payload = next(
        p for _, et, p in published_calls if et == "npu.worker.metrics.updated"
    )
    assert metrics_payload["event"] == "worker.metrics.updated"
    assert metrics_payload["worker_id"] == _WORKER_ID
    # The WS subscriber reads data["metrics"] (#10602 6.4)
    assert "metrics" in metrics_payload["data"], (
        "metrics key must be present in data payload of npu.worker.metrics.updated"
    )
    assert metrics_payload["data"]["metrics"]["avg_response_time_ms"] == 123.4


# ---------------------------------------------------------------------------
# Part B — avg_response_time_ms aggregation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_worker_metrics_nonzero_avg_response_time_when_pulse_data_exists():
    """_build_worker_metrics returns non-zero avg_response_time_ms when pulse data exists."""
    mgr = _make_manager()
    status = _make_status()

    # Simulate two models with known p95 latencies (seconds)
    async def fake_aggregate(worker_id: str) -> float:
        return 250.0  # ms

    mgr._aggregate_avg_response_time_ms = fake_aggregate

    result = await mgr._build_worker_metrics(_WORKER_ID, status)

    assert result.avg_response_time_ms == 250.0, (
        f"Expected 250.0 ms, got {result.avg_response_time_ms}"
    )
    assert result.id == _WORKER_ID
    assert result.success_rate > 0.0


@pytest.mark.asyncio
async def test_aggregate_avg_response_time_ms_computes_mean_of_model_p95s():
    """_aggregate_avg_response_time_ms returns mean of per-model p95 in ms."""
    redis_mock = AsyncMock()
    # Two model keys
    redis_mock.keys = AsyncMock(
        return_value=[
            b"npu:worker:test-worker-1:pulse_latency:model-a",
            b"npu:worker:test-worker-1:pulse_latency:model-b",
        ]
    )

    mgr = _make_manager(redis_client=redis_mock)

    # model-a p95 = 1.0s, model-b p95 = 3.0s → mean = 2.0s = 2000.0ms
    async def fake_p95(worker_id, model_id):
        return 1.0 if model_id == "model-a" else 3.0

    mgr._get_pulse_p95_latency = fake_p95

    result = await mgr._aggregate_avg_response_time_ms(_WORKER_ID)

    assert result == 2000.0, f"Expected 2000.0 ms (mean of 1s+3s), got {result}"


@pytest.mark.asyncio
async def test_aggregate_avg_response_time_ms_returns_zero_when_no_pulse_keys():
    """_aggregate_avg_response_time_ms returns 0.0 when no pulse latency keys exist."""
    redis_mock = AsyncMock()
    redis_mock.keys = AsyncMock(return_value=[])

    mgr = _make_manager(redis_client=redis_mock)

    result = await mgr._aggregate_avg_response_time_ms(_WORKER_ID)
    assert result == 0.0


@pytest.mark.asyncio
async def test_aggregate_avg_response_time_ms_returns_zero_without_redis():
    """_aggregate_avg_response_time_ms returns 0.0 when no Redis client is set."""
    mgr = _make_manager(redis_client=None)
    result = await mgr._aggregate_avg_response_time_ms(_WORKER_ID)
    assert result == 0.0
