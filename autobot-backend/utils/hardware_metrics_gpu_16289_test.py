# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""HardwarePerformanceMonitor sees any NVIDIA GPU, not only an RTX 4070 (#16289)."""

from unittest.mock import patch

from utils.hardware_metrics import HardwarePerformanceMonitor


def _available(rows) -> bool:
    monitor = HardwarePerformanceMonitor.__new__(HardwarePerformanceMonitor)
    with patch("utils.hardware_metrics.query_nvidia_gpus", return_value=rows):
        return monitor._check_gpu_availability()


def test_a_gpu_other_than_an_rtx_4070_is_available():
    assert _available([{"name": "NVIDIA RTX A2000"}]) is True


def test_no_nvidia_smi_is_unavailable():
    assert _available(None) is False


def test_nvidia_smi_reporting_no_gpu_is_unavailable():
    assert _available([]) is False
