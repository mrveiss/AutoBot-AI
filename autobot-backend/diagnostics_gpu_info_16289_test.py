# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""diagnostics._get_gpu_info reads the first GPU through autobot_shared.gpu_telemetry (#16289)."""

from unittest.mock import patch

from diagnostics import PerformanceOptimizedDiagnostics

GPU_A = {"name": "NVIDIA Test GPU A", "memory.total": "16384", "memory.used": "4096", "utilization.gpu": "30"}
UNAVAILABLE = {"status": "nvidia-smi not available or no GPU detected"}
_GPU_INFO_FIELDS = ("name", "memory.total", "memory.used", "utilization.gpu")


def _info(rows):
    diagnostics = PerformanceOptimizedDiagnostics.__new__(PerformanceOptimizedDiagnostics)
    with patch("diagnostics.query_nvidia_gpus", return_value=rows) as query:
        info = diagnostics._get_gpu_info()
    query.assert_called_once_with(_GPU_INFO_FIELDS)
    return info


def test_the_first_gpu_is_reported_and_the_second_does_not_leak_in():
    gpu_b = {"name": "NVIDIA Test GPU B", "memory.total": "6144", "memory.used": "10", "utilization.gpu": "0"}

    assert _info([GPU_A, gpu_b]) == {
        "name": "NVIDIA Test GPU A",
        "memory_total_mb": 16384,
        "memory_used_mb": 4096,
        "utilization_percent": 30,
        "memory_usage_percent": 25.0,
    }


def test_no_nvidia_smi_is_reported_as_unavailable():
    assert _info(None) == UNAVAILABLE


def test_no_gpu_rows_is_reported_as_unavailable():
    assert _info([]) == UNAVAILABLE


def test_an_unreadable_value_is_a_detection_error():
    assert _info([{**GPU_A, "memory.total": "[N/A]"}]) == {"status": "GPU detection error"}
