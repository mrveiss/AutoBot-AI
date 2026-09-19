# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-node GPU state and its published series, from heartbeat telemetry (#16281).

The SLM suite stubs ``config``, and the real metrics manager builds file log
handlers from it at import, so the manager cannot be imported here. These tests
drive ``_Metrics`` instead -- the manager's GPU interface with the same
signatures, keeping series in memory. The real recorder's series (node label,
unreadable values left unset, per-node removal) are covered by
``autobot_shared/monitoring/metrics/performance_gpu_node_test.py``.
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from models.gpu_schemas import GPUReportState
from services import node_gpu
from services.node_gpu import fleet_gpu_statuses, node_gpu_status, publish_node_gpu, retract_node_gpu
from status_enums import NodeStatus

MEASURED = {
    "device_type": "nvidia-gpu",
    "index": 0,
    "name": "NVIDIA GeForce RTX 4070 Laptop GPU",
    "monitored": True,
    "utilization_percent": 12.0,
    "memory_used_mb": 2047.0,
    "memory_total_mb": 8188.0,
    "temperature_celsius": 51.0,
    "power_watts": None,
}
UNMONITORED = {"device_type": "amd-gpu", "monitored": False}
GPU_NAME = "NVIDIA GeForce RTX 4070 Laptop GPU"


class _Metrics:
    """The metrics manager's GPU interface, keeping the series it would publish."""

    def __init__(self):
        self.series = {}
        self.available = {}

    def set_gpu_available(self, available, node=None):
        self.available[node] = available

    def update_gpu_metrics(
        self, gpu_id, gpu_name, utilization, memory_utilization, temperature, power_watts, node=None
    ):
        self.series[(node, gpu_id, gpu_name)] = {
            "utilization": utilization,
            "memory_utilization": memory_utilization,
            "temperature": temperature,
            "power_watts": power_watts,
        }

    def remove_gpu_node(self, node):
        self.available.pop(node, None)
        self.series = {key: value for key, value in self.series.items() if key[0] != node}


@pytest.fixture(autouse=True)
def _fresh_publications():
    node_gpu._published_as.clear()
    yield
    node_gpu._published_as.clear()


def _node(hostname="worker-1", status=NodeStatus.ONLINE.value, node_id=None, **extra):
    return SimpleNamespace(
        node_id=node_id or f"id-{hostname}",
        hostname=hostname,
        status=status,
        extra_data=extra,
        last_heartbeat=datetime(2026, 9, 11, tzinfo=timezone.utc),
    )


def _series(metrics, hostname):
    return metrics.series.get((hostname, "0", GPU_NAME))


class TestNodeGpuStatus:
    def test_an_agent_without_the_key_is_not_reported(self):
        assert node_gpu_status(_node()).state is GPUReportState.NOT_REPORTED

    def test_an_empty_probe_is_none_present(self):
        status = node_gpu_status(_node(gpu=[]))

        assert status.state is GPUReportState.NONE
        assert status.devices == []

    def test_reported_devices_are_present(self):
        status = node_gpu_status(_node(gpu=[MEASURED, UNMONITORED]))

        assert status.state is GPUReportState.PRESENT
        assert [d.monitored for d in status.devices] == [True, False]
        assert status.devices[0].memory_total_mb == 8188.0

    def test_malformed_and_non_gpu_entries_are_skipped(self):
        status = node_gpu_status(
            _node(gpu=[{"device_type": "nvidia-gpu"}, {"device_type": "intel-npu", "monitored": True}, MEASURED])
        )

        assert [d.name for d in status.devices] == [GPU_NAME]


class TestPublishNodeGpu:
    def test_a_measured_device_is_one_series_labelled_with_its_node(self):
        metrics = _Metrics()

        publish_node_gpu(metrics, _node(gpu=[MEASURED]))

        assert _series(metrics, "worker-1") == {
            "utilization": 12.0,
            "memory_utilization": 25.0,
            "temperature": 51.0,
            "power_watts": None,
        }
        assert metrics.available == {"worker-1": True}

    def test_an_unmonitored_device_is_available_without_metric_series(self):
        metrics = _Metrics()

        publish_node_gpu(metrics, _node(gpu=[UNMONITORED]))

        assert metrics.available == {"worker-1": True}
        assert metrics.series == {}

    def test_a_node_without_gpus_reports_unavailable(self):
        metrics = _Metrics()

        publish_node_gpu(metrics, _node(gpu=[]))

        assert metrics.available == {"worker-1": False}

    def test_going_offline_retracts_the_series(self):
        metrics = _Metrics()
        publish_node_gpu(metrics, _node(gpu=[MEASURED]))

        publish_node_gpu(metrics, _node(status=NodeStatus.OFFLINE.value, gpu=[MEASURED]))

        assert metrics.series == {}
        assert metrics.available == {}

    def test_decommissioned_and_unreported_nodes_publish_nothing(self):
        metrics = _Metrics()

        publish_node_gpu(metrics, _node("retired", NodeStatus.DECOMMISSIONED.value, gpu=[MEASURED]))
        publish_node_gpu(metrics, _node("old"))

        assert metrics.available == {}
        assert metrics.series == {}

    def test_a_renamed_node_leaves_no_series_under_its_old_name(self):
        metrics = _Metrics()
        publish_node_gpu(metrics, _node("before", node_id="n1", gpu=[MEASURED]))

        publish_node_gpu(metrics, _node("after", node_id="n1", gpu=[MEASURED]))

        assert _series(metrics, "before") is None
        assert _series(metrics, "after")["utilization"] == 12.0

    def test_other_nodes_keep_their_series(self):
        metrics = _Metrics()
        publish_node_gpu(metrics, _node("leaving", gpu=[MEASURED]))
        publish_node_gpu(metrics, _node("staying", gpu=[MEASURED]))

        retract_node_gpu(metrics, "id-leaving")

        assert _series(metrics, "leaving") is None
        assert _series(metrics, "staying")["utilization"] == 12.0


class TestMapperHooks:
    def test_a_write_publishes_through_the_process_manager(self, monkeypatch):
        metrics = _Metrics()
        monkeypatch.setattr(node_gpu, "_metrics_manager", lambda: metrics)

        node_gpu._on_node_written(None, None, _node(gpu=[MEASURED]))

        assert _series(metrics, "worker-1")["utilization"] == 12.0

    def test_a_delete_retracts(self, monkeypatch):
        metrics = _Metrics()
        monkeypatch.setattr(node_gpu, "_metrics_manager", lambda: metrics)
        node_gpu._on_node_written(None, None, _node(gpu=[MEASURED]))

        node_gpu._on_node_deleted(None, None, _node(gpu=[MEASURED]))

        assert metrics.available == {}

    def test_a_failing_publish_never_raises_into_the_flush(self, monkeypatch, caplog):
        def broken():
            raise RuntimeError("registry unavailable")

        monkeypatch.setattr(node_gpu, "_metrics_manager", broken)

        node_gpu._on_node_written(None, None, _node(gpu=[MEASURED]))

        assert "GPU series not published for node=id-worker-1" in caplog.text


class _Db:
    def __init__(self, nodes):
        self._nodes = nodes

    async def execute(self, _statement):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self._nodes))


def test_the_fleet_listing_reads_every_node():
    statuses = asyncio.run(fleet_gpu_statuses(_Db([_node("a", gpu=[]), _node("b")])))

    assert [(s.hostname, s.state) for s in statuses] == [("a", GPUReportState.NONE), ("b", GPUReportState.NOT_REPORTED)]
