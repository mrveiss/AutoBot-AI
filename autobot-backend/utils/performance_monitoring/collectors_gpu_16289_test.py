# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GPUCollector parses each GPU's row on its own and still returns the first (#16289).

Reporting every GPU to the consumers is #16297; this pins that the first GPU's
metrics are built from the first row alone.
"""

import asyncio
from unittest.mock import patch

from autobot_shared.gpu_telemetry import METRICS_QUERY_FIELDS
from utils.performance_monitoring.collectors import GPUCollector

FIRST = dict(
    zip(
        METRICS_QUERY_FIELDS,
        [
            "NVIDIA GeForce RTX 4070 Laptop GPU",
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
            "NVIDIA RTX A2000",
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
    "name": "NVIDIA GeForce RTX 4070 Laptop GPU",
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


def _collect(rows, available=True):
    with patch("utils.performance_monitoring.collectors.query_nvidia_gpus", return_value=rows) as query:
        metrics = asyncio.run(GPUCollector(available).collect())
    return metrics, query


def test_the_first_gpu_is_built_from_its_own_row_and_the_second_leaks_nothing():
    metrics, _ = _collect([FIRST, SECOND])

    assert _fields(metrics) == FIRST_METRICS


def test_an_unreadable_core_value_yields_no_metrics():
    metrics, _ = _collect([{**FIRST, "temperature.gpu": "[N/A]"}])

    assert metrics is None


def test_no_nvidia_smi_yields_no_metrics():
    metrics, _ = _collect(None)

    assert metrics is None


def test_an_unavailable_gpu_is_never_queried():
    metrics, query = _collect([FIRST], available=False)

    assert metrics is None
    query.assert_not_called()
