# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
GPU Detection Module

Issue #381: Extracted from gpu_acceleration_optimizer.py god class refactoring.
Contains GPU availability checking and capability detection.
"""

import logging
import subprocess
from typing import Any, Dict

from .types import GPUCapabilities

logger = logging.getLogger(__name__)


def check_gpu_availability() -> bool:
    """Check if NVIDIA GPU is available."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and "RTX" in result.stdout
    except Exception:
        return False


def detect_gpu_capabilities(gpu_available: bool) -> GPUCapabilities:
    """Detect GPU capabilities and features."""
    capabilities = GPUCapabilities()

    if not gpu_available:
        return capabilities

    try:
        # Get detailed GPU information
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,cuda_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            if len(parts) >= 3:
                gpu_name = parts[0].strip()
                memory_mb = int(parts[1].strip())
                cuda_version = parts[2].strip()

                capabilities.name = gpu_name
                capabilities.memory_gb = round(memory_mb / 1024, 1)
                capabilities.cuda_version = cuda_version
                capabilities.tensor_cores = "RTX" in gpu_name
                capabilities.mixed_precision = True

        # Try to get compute capability using nvidia-ml-py if available
        capabilities = _detect_detailed_capabilities(capabilities)

    except Exception as e:
        logger.error("Error detecting GPU capabilities: %s", e)

    return capabilities


def _detect_detailed_capabilities(capabilities: GPUCapabilities) -> GPUCapabilities:
    """Detect detailed capabilities using pynvml if available."""
    try:
        import pynvml

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)

        major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
        capabilities.compute_capability = f"{major}.{minor}"

        # Get additional device info
        multiprocessor_count = pynvml.nvmlDeviceGetMultiProcessorCount(handle)
        capabilities.multiprocessor_count = multiprocessor_count

        pynvml.nvmlShutdown()

    except ImportError:
        logger.debug("pynvml not available for detailed GPU capabilities")
    except Exception as e:
        logger.debug("Failed to get detailed GPU capabilities: %s", e)

    return capabilities


def get_gpu_capabilities_dict(gpu_available: bool) -> Dict[str, Any]:
    """Get GPU capabilities as a dictionary (legacy interface)."""
    capabilities = detect_gpu_capabilities(gpu_available)
    return capabilities.to_dict()
