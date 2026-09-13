#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
AutoBot Phase 9 Monitoring System Validation Test
Comprehensive testing of GPU/NPU monitoring, performance optimization, and real-time dashboard.

Converted from a hand-driven script to collectable pytest tests (#14979). The
previous shape -- a class with ``__init__``, a ``run_full_test_suite`` driver
and methods that recorded a dict instead of asserting -- collected zero items,
so none of these ten checks had ever run under pytest.
"""

import asyncio

import pytest

from utils.gpu_acceleration_optimizer import (
    benchmark_gpu,
    get_gpu_capabilities,
    gpu_optimizer,
    monitor_gpu_efficiency,
    optimize_gpu_for_multimodal,
    update_gpu_config,
)
from utils.hardware_metrics import (
    add_phase9_alert_callback,
    collect_phase9_metrics,
    get_phase9_performance_dashboard,
    hardware_monitor,
    start_hardware_monitoring,
    stop_hardware_monitoring,
)

# `integration`: metric collection dials the running AutoBot services over HTTP
# through aiohttp, and the monitor reads real GPU/NPU/host telemetry.
# `slow`: the real-time monitoring test waits out a full collection cycle.
# Both markers are excluded from the PR unit gate and selected by marker-tests.yml.
pytestmark = [pytest.mark.integration, pytest.mark.slow]

# The monitoring loop collects every `collection_interval` (5.0 s) seconds. The
# sample window must clear one full cycle; env-var backed so a loaded fleet
# runner can widen it without a code change.
MONITORING_SAMPLE_WINDOW_SECONDS = 12.0

# Fields every alert emitted by `_store_and_notify_alerts` carries.
REQUIRED_ALERT_FIELDS = ("category", "severity", "message", "timestamp")

# Dashboard keys `get_current_performance_dashboard` always publishes, with or
# without a metric sample behind it.
REQUIRED_DASHBOARD_KEYS = (
    "monitoring_active",
    "hardware_acceleration",
    "performance_baselines",
    "trends",
    "recent_alerts",
    "services",
)

# `get_current_performance_dashboard` keeps only the last ten alerts.
DASHBOARD_ALERT_WINDOW = 10

NO_GPU_REASON = "no GPU is available on this host — the GPU optimizer has nothing to exercise"


@pytest.fixture
async def stopped_monitor():
    """Guarantee the shared monitor is idle before and after a test.

    `hardware_monitor` is a module-global singleton, so a test that leaves the
    monitoring loop running would feed metrics into the next one's buffers.
    """
    if hardware_monitor.monitoring_active:
        await stop_hardware_monitoring()
    yield hardware_monitor
    if hardware_monitor.monitoring_active:
        await stop_hardware_monitoring()


@pytest.fixture
def restored_gpu_config():
    """Restore the optimizer's mixed-precision setting after a test mutates it."""
    original = gpu_optimizer.get_optimization_config().mixed_precision_enabled
    yield original
    gpu_optimizer.get_optimization_config().mixed_precision_enabled = original


class TestHardwareMonitoring:
    """Validation of the Phase 9 GPU/NPU monitoring and optimization stack."""

    def setup_method(self) -> None:
        """Per-test state that the old `__init__` used to hold."""
        self.alerts_received: list[dict] = []

    def test_hardware_detection(self) -> None:
        """The monitor and the optimizer agree on what accelerators exist."""
        capabilities = get_gpu_capabilities()

        assert isinstance(
            hardware_monitor.gpu_available, bool
        ), f"hardware_monitor.gpu_available must be a bool, got {type(hardware_monitor.gpu_available).__name__}"
        assert isinstance(
            hardware_monitor.npu_available, bool
        ), f"hardware_monitor.npu_available must be a bool, got {type(hardware_monitor.npu_available).__name__}"
        assert (
            "capabilities" in capabilities
        ), f"get_gpu_capabilities() published no 'capabilities' key: {sorted(capabilities)}"
        assert capabilities["gpu_available"] == gpu_optimizer.gpu_available, (
            "get_gpu_capabilities() disagrees with gpu_optimizer.gpu_available: "
            f"{capabilities['gpu_available']} vs {gpu_optimizer.gpu_available}"
        )

    def test_performance_monitor_initialization(self) -> None:
        """The monitor starts idle, with its metric buffers and baselines in place."""
        buffers = {
            "gpu_metrics_buffer": hardware_monitor.gpu_metrics_buffer,
            "npu_metrics_buffer": hardware_monitor.npu_metrics_buffer,
            "system_metrics_buffer": hardware_monitor.system_metrics_buffer,
        }

        for name, buffer in buffers.items():
            assert buffer is not None, f"hardware_monitor.{name} was never initialised"
            assert buffer.maxlen, f"hardware_monitor.{name} is unbounded; it must be a bounded deque"

        assert (
            hardware_monitor.performance_baselines
        ), "hardware_monitor.performance_baselines is empty — alert analysis has nothing to compare against"
        assert isinstance(
            hardware_monitor.monitoring_active, bool
        ), f"monitoring_active must be a bool, got {type(hardware_monitor.monitoring_active).__name__}"

    def test_gpu_capabilities_and_optimization(self) -> None:
        """The optimizer exposes a capability map and a usable optimization config."""
        if not gpu_optimizer.gpu_available:
            pytest.skip(NO_GPU_REASON)

        capabilities = gpu_optimizer.gpu_capabilities
        config = gpu_optimizer.get_optimization_config()

        assert capabilities, "gpu_optimizer reports a GPU but published no capability map"
        assert capabilities.get("vendor"), f"gpu_optimizer capability map names no vendor: {sorted(capabilities)}"
        assert config is not None, "gpu_optimizer.get_optimization_config() returned None for an available GPU"
        for field in ("mixed_precision_enabled", "tensor_core_optimization", "auto_batch_sizing"):
            assert isinstance(getattr(config, field), bool), f"optimization config field {field} is not a bool"

    async def test_metrics_collection(self) -> None:
        """One collection pass yields a complete, self-consistent metric bundle."""
        metrics = await collect_phase9_metrics()

        assert metrics.get(
            "collection_successful"
        ), f"collect_phase9_metrics() reported a failed collection: {metrics.get('error', metrics)}"
        assert metrics.get("system"), "collection succeeded but carried no system metrics"
        assert metrics.get("timestamp"), "collection succeeded but carried no timestamp"
        assert isinstance(
            metrics.get("services"), list
        ), f"'services' must be a list of per-service metrics, got {type(metrics.get('services')).__name__}"

        individual = await hardware_monitor.collect_system_performance_metrics()
        assert individual is not None, "collect_system_performance_metrics() returned None on a host it just measured"

    async def test_realtime_monitoring(self, stopped_monitor) -> None:
        """The monitoring loop fills the metric buffers while it is active."""
        before = len(stopped_monitor.system_metrics_buffer)

        await start_hardware_monitoring()
        assert stopped_monitor.monitoring_active, "start_hardware_monitoring() left monitoring_active False"
        await asyncio.sleep(MONITORING_SAMPLE_WINDOW_SECONDS)
        after = len(stopped_monitor.system_metrics_buffer)

        await stop_hardware_monitoring()

        assert after > before, (
            f"the monitoring loop collected no system metrics in {MONITORING_SAMPLE_WINDOW_SECONDS}s "
            f"(buffer stayed at {before} entries)"
        )
        assert not stopped_monitor.monitoring_active, "stop_hardware_monitoring() left monitoring_active True"

    async def test_performance_dashboard(self) -> None:
        """The dashboard publishes every documented section once a sample exists."""
        await collect_phase9_metrics()
        dashboard = get_phase9_performance_dashboard()

        missing = [key for key in REQUIRED_DASHBOARD_KEYS if key not in dashboard]
        assert not missing, f"performance dashboard is missing required sections {missing}; it has {sorted(dashboard)}"
        assert dashboard["system"], "the dashboard published no system section after a successful collection"
        assert (
            dashboard["monitoring_active"] == hardware_monitor.monitoring_active
        ), "the dashboard's monitoring_active disagrees with the monitor's own state"
        assert isinstance(
            dashboard["recent_alerts"], list
        ), f"'recent_alerts' must be a list, got {type(dashboard['recent_alerts']).__name__}"

    async def test_alert_system(self) -> None:
        """Callbacks register, and every stored alert carries the documented fields."""

        async def record_alerts(alerts):
            self.alerts_received.extend(alerts)

        add_phase9_alert_callback(record_alerts)
        try:
            assert (
                record_alerts in hardware_monitor.alert_callbacks
            ), "add_phase9_alert_callback() did not register the callback on the monitor"

            stored = list(hardware_monitor.performance_alerts)
            for alert in stored:
                missing = [field for field in REQUIRED_ALERT_FIELDS if field not in alert]
                assert not missing, f"stored alert is missing fields {missing}: {sorted(alert)}"

            dashboard = get_phase9_performance_dashboard()
            assert (
                dashboard["recent_alerts"] == stored[-DASHBOARD_ALERT_WINDOW:]
            ), "the dashboard's recent_alerts window does not mirror the monitor's stored alerts"
        finally:
            hardware_monitor.alert_callbacks.remove(record_alerts)

    async def test_optimization_engine(self) -> None:
        """Efficiency monitoring, config updates and multi-modal optimization all run."""
        if not gpu_optimizer.gpu_available:
            pytest.skip(NO_GPU_REASON)

        efficiency = await monitor_gpu_efficiency()
        assert (
            "overall_efficiency" in efficiency
        ), f"monitor_gpu_efficiency() published no overall_efficiency: {sorted(efficiency)}"
        assert (
            0 <= efficiency["overall_efficiency"] <= 100
        ), f"overall_efficiency {efficiency['overall_efficiency']} is outside the 0-100 percent range"

        updated = await update_gpu_config({"mixed_precision_enabled": True, "tensor_core_optimization": True})
        assert updated, "update_gpu_config() rejected a valid mixed-precision/tensor-core update"

        result = await optimize_gpu_for_multimodal()
        assert result.success, f"optimize_gpu_for_multimodal() failed: {getattr(result, 'error', result)}"
        assert result.applied_optimizations is not None, "a successful optimization listed no applied optimizations"

    async def test_benchmark_suite(self) -> None:
        """The GPU benchmark returns a scored report with its test breakdown."""
        if not gpu_optimizer.gpu_available:
            pytest.skip(NO_GPU_REASON)

        results = await benchmark_gpu()

        missing = [
            key for key in ("gpu_info", "benchmark_tests", "overall_score", "recommendations") if key not in results
        ]
        assert not missing, f"benchmark_gpu() is missing report sections {missing}; it returned {sorted(results)}"
        assert (
            0 <= results["overall_score"] <= 100
        ), f"benchmark overall_score {results['overall_score']} is outside the 0-100 range"
        assert results["benchmark_tests"], "benchmark_gpu() reported a score but ran no benchmark tests"

    async def test_configuration_management(self, restored_gpu_config) -> None:
        """A config update is applied to the optimizer and is readable back."""
        config = gpu_optimizer.get_optimization_config()
        assert config is not None, "gpu_optimizer.get_optimization_config() returned None"
        assert (
            hardware_monitor.performance_baselines
        ), "the monitor carries no performance baselines to configure against"

        toggled = not restored_gpu_config
        assert await update_gpu_config(
            {"mixed_precision_enabled": toggled}
        ), f"update_gpu_config() rejected mixed_precision_enabled={toggled}"
        assert (
            gpu_optimizer.get_optimization_config().mixed_precision_enabled == toggled
        ), "update_gpu_config() reported success but the optimizer still reads the previous value"
