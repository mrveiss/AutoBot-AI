# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GPU series carry the node they were measured on (#16281)."""

from prometheus_client import CollectorRegistry

from autobot_shared.monitoring.metrics.performance import LOCAL_NODE, PerformanceMetricsRecorder


def _recorder():
    registry = CollectorRegistry()
    return registry, PerformanceMetricsRecorder(registry)


def _labels(node: str) -> dict:
    return {"node": node, "gpu_id": "0", "gpu_name": "RTX 4070"}


def test_a_fleet_node_is_labelled_with_the_name_passed_in():
    registry, recorder = _recorder()

    recorder.update_gpu_metrics("0", "RTX 4070", 12.0, 40.0, 51.0, 1.9, node="worker-1")
    recorder.set_gpu_available(True, node="worker-1")

    assert registry.get_sample_value("autobot_gpu_utilization_percent", _labels("worker-1")) == 12.0
    assert registry.get_sample_value("autobot_gpu_available", {"node": "worker-1"}) == 1.0


def test_a_process_reporting_its_own_gpu_is_labelled_with_its_own_host():
    registry, recorder = _recorder()

    recorder.update_gpu_metrics("0", "RTX 4070", 12.0, 40.0, 51.0, 1.9)
    recorder.set_gpu_available(False)

    assert registry.get_sample_value("autobot_gpu_temperature_celsius", _labels(LOCAL_NODE)) == 51.0
    assert registry.get_sample_value("autobot_gpu_available", {"node": LOCAL_NODE}) == 0.0


def test_an_unreadable_value_leaves_its_series_unset_rather_than_zero():
    registry, recorder = _recorder()

    recorder.update_gpu_metrics("0", "RTX 4070", 12.0, 40.0, None, None, node="worker-1")

    assert registry.get_sample_value("autobot_gpu_temperature_celsius", _labels("worker-1")) is None
    assert registry.get_sample_value("autobot_gpu_power_watts", _labels("worker-1")) is None
    assert registry.get_sample_value("autobot_gpu_memory_utilization_percent", _labels("worker-1")) == 40.0


def test_removing_a_node_drops_only_its_series():
    registry, recorder = _recorder()
    for node in ("worker-1", "worker-2"):
        recorder.update_gpu_metrics("0", "RTX 4070", 12.0, 40.0, 51.0, 1.9, node=node)
        recorder.set_gpu_available(True, node=node)

    recorder.remove_gpu_node("worker-1")

    assert registry.get_sample_value("autobot_gpu_utilization_percent", _labels("worker-1")) is None
    assert registry.get_sample_value("autobot_gpu_available", {"node": "worker-1"}) is None
    assert registry.get_sample_value("autobot_gpu_utilization_percent", _labels("worker-2")) == 12.0
    assert registry.get_sample_value("autobot_gpu_available", {"node": "worker-2"}) == 1.0
