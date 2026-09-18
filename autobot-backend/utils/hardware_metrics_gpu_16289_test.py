# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""HardwarePerformanceMonitor sees any NVIDIA GPU, not only an RTX 4070 (#16289)."""

import asyncio
from unittest.mock import patch

from autobot_shared.gpu_telemetry import METRICS_QUERY_FIELDS
from utils.hardware_metrics import HardwarePerformanceMonitor


def _available(rows) -> bool:
    monitor = HardwarePerformanceMonitor.__new__(HardwarePerformanceMonitor)
    with patch("utils.hardware_metrics.query_nvidia_gpus", return_value=rows):
        return monitor._check_gpu_availability()


def test_a_gpu_other_than_an_rtx_4070_is_available():
    assert _available([{"name": "NVIDIA Test GPU B"}]) is True


def test_no_nvidia_smi_is_unavailable():
    assert _available(None) is False


def test_nvidia_smi_reporting_no_gpu_is_unavailable():
    assert _available([]) is False


FIRST = dict(
    zip(
        METRICS_QUERY_FIELDS,
        [
            "NVIDIA Test GPU A",
            "2047",
            "8188",
            "12",
            "51",
            "20.5",
            "1500",
            "7000",
            "30",
            "1",
            "2",
            "P2",
            "Not Active",
            "Not Active",
            "Not Active",
            "Not Active",
            "Active",
            "Not Active",
        ],
    )
)
# Different in every field, so a value read from the wrong row shows.
SECOND = dict(
    zip(
        METRICS_QUERY_FIELDS,
        [
            "NVIDIA Test GPU B",
            "10",
            "6138",
            "99",
            "80",
            "70.0",
            "900",
            "6000",
            "55",
            "7",
            "8",
            "P0",
            "Active",
            "Active",
            "Active",
            "Active",
            "Not Active",
            "Active",
        ],
    )
)
FIRST_METRICS = {
    "name": "NVIDIA Test GPU A",
    "utilization_percent": 12.0,
    "memory_used_mb": 2047,
    "memory_total_mb": 8188,
    "memory_free_mb": 6141,
    "memory_utilization_percent": 25.0,
    "temperature_celsius": 51,
    "power_draw_watts": 20.5,
    "gpu_clock_mhz": 1500,
    "memory_clock_mhz": 7000,
    "fan_speed_percent": 30,
    "encoder_utilization": 1,
    "decoder_utilization": 2,
    "performance_state": "P2",
    "thermal_throttling": True,
    "power_throttling": False,
}


def _fields(metrics) -> dict:
    return {name: getattr(metrics, name) for name in FIRST_METRICS}


def _collect(rows):
    monitor = HardwarePerformanceMonitor.__new__(HardwarePerformanceMonitor)
    monitor.gpu_available = True
    with patch("utils.hardware_metrics.query_nvidia_gpus", return_value=rows):
        return asyncio.run(monitor.collect_gpu_metrics())


def test_collect_builds_the_first_gpu_from_its_own_row_and_the_second_leaks_nothing():
    assert _fields(_collect([FIRST, SECOND])) == FIRST_METRICS


def test_collect_yields_nothing_for_an_unreadable_core_value():
    assert _collect([{**FIRST, "memory.total": "[N/A]"}]) is None


def test_collect_yields_nothing_without_nvidia_smi():
    assert _collect(None) is None
