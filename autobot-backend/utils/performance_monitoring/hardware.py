# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Hardware Detection Module

Contains hardware detection utilities for GPU, NPU, and environment detection.

Extracted from performance_monitor.py as part of Issue #381 refactoring.
"""

import logging
import subprocess

logger = logging.getLogger(__name__)


class HardwareDetector:
    """Hardware detection utilities for performance monitoring."""

    @staticmethod
    def check_gpu_availability() -> bool:
        """Check if NVIDIA GPU is available and accessible."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and "RTX 4070" in result.stdout
        except Exception:
            return False

    @staticmethod
    def check_npu_availability() -> bool:
        """Check if Intel NPU is available."""
        try:
            # Check CPU model for Intel Ultra series
            with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
                cpuinfo = f.read()
                if "Intel(R) Core(TM) Ultra" in cpuinfo:
                    # Check for OpenVINO NPU support
                    try:
                        from openvino.runtime import Core

                        core = Core()
                        npu_devices = [d for d in core.available_devices if "NPU" in d]
                        return len(npu_devices) > 0
                    except ImportError:
                        return False
            return False
        except Exception:
            return False

    @staticmethod
    def check_wsl_environment() -> bool:
        """Check if running in WSL environment."""
        try:
            with open("/proc/version", "r", encoding="utf-8") as f:
                version_info = f.read()
                return "WSL" in version_info or "Microsoft" in version_info
        except Exception:
            return False
