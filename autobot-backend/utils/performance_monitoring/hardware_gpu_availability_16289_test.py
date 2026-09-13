# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""HardwareDetector sees any NVIDIA GPU, not only an RTX 4070 (#16289)."""

from unittest.mock import patch

from utils.performance_monitoring.hardware import HardwareDetector


def _available(rows) -> bool:
    with patch("utils.performance_monitoring.hardware.query_nvidia_gpus", return_value=rows):
        return HardwareDetector.check_gpu_availability()


def test_a_gpu_other_than_an_rtx_4070_is_available():
    assert _available([{"name": "NVIDIA RTX A2000"}]) is True


def test_no_nvidia_smi_is_unavailable():
    assert _available(None) is False


def test_nvidia_smi_reporting_no_gpu_is_unavailable():
    assert _available([]) is False
