# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""diagnostics._get_gpu_info reads the first GPU through autobot_shared.gpu_telemetry (#16289)."""

from unittest.mock import patch

from diagnostics import PerformanceOptimizedDiagnostics

RTX = {
    "name": "NVIDIA GeForce RTX 4070 Laptop GPU",
    "memory.total": "8188",
    "memory.used": "2047",
    "utilization.gpu": "12",
}
UNAVAILABLE = {"status": "nvidia-smi not available or no GPU detected"}


def _info(rows):
    diagnostics = PerformanceOptimizedDiagnostics.__new__(PerformanceOptimizedDiagnostics)
    with patch("diagnostics.query_nvidia_gpus", return_value=rows):
        return diagnostics._get_gpu_info()


def test_the_first_gpu_is_reported_and_the_second_does_not_leak_in():
    second = {"name": "NVIDIA RTX A2000", "memory.total": "6138", "memory.used": "10", "utilization.gpu": "0"}

    assert _info([RTX, second]) == {
        "name": "NVIDIA GeForce RTX 4070 Laptop GPU",
        "memory_total_mb": 8188,
        "memory_used_mb": 2047,
        "utilization_percent": 12,
        "memory_usage_percent": 25.0,
    }


def test_no_nvidia_smi_is_reported_as_unavailable():
    assert _info(None) == UNAVAILABLE


def test_no_gpu_rows_is_reported_as_unavailable():
    assert _info([]) == UNAVAILABLE


def test_an_unreadable_value_is_a_detection_error():
    assert _info([{**RTX, "memory.total": "[N/A]"}]) == {"status": "GPU detection error"}
