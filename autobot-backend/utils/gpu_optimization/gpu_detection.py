# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
GPU Detection Module

Issue #381: Extracted from gpu_acceleration_optimizer.py god class refactoring.
Issue #1959: Expanded beyond RTX to support all NVIDIA, AMD, and Intel GPUs.
Contains GPU availability checking and capability detection.
"""

import functools
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from .types import GPUCapabilities

logger = logging.getLogger(__name__)

# Stashed GPU name from initial nvidia-smi probe (#2222)
_nvidia_gpu_name: Optional[str] = None

# NVIDIA GPU families known to have tensor cores
_TENSOR_CORE_FAMILIES = {
    "RTX",
    "A100",
    "A10",
    "A30",
    "A40",
    "A6000",
    "H100",
    "H200",
    "L40",
    "L4",
    "T4",
    "V100",
}


def _check_nvidia_gpu() -> Optional[str]:
    """Check for NVIDIA GPU via nvidia-smi, returning the GPU name or None.

    Issue #2222: Returns the name so callers can reuse it without
    spawning a second nvidia-smi subprocess.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        name = result.stdout.strip()
        if result.returncode == 0 and name:
            return name
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    except Exception:
        return None


def _check_amd_gpu() -> bool:
    """Check if an AMD GPU is available via rocm-smi or sysfs."""
    try:
        result = subprocess.run(
            ["rocm-smi", "--showid"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception:
        pass
    # Sysfs fallback: AMD vendor ID = 0x1002
    return _check_sysfs_vendor("0x1002")


def _check_intel_gpu() -> bool:
    """Check if an Intel discrete GPU is available via sysfs."""
    # Intel vendor ID = 0x8086
    return _check_sysfs_vendor("0x8086")


def _check_sysfs_vendor(vendor_id: str) -> bool:
    """Check sysfs DRM devices for a specific PCI vendor ID."""
    drm_path = Path("/sys/class/drm")
    if not drm_path.exists():
        return False
    try:
        for card_dir in drm_path.iterdir():
            vendor_file = card_dir / "device" / "vendor"
            if vendor_file.exists():
                content = vendor_file.read_text(encoding="utf-8").strip()
                if content == vendor_id:
                    return True
    except Exception:
        pass
    return False


def _has_tensor_cores(gpu_name: str) -> bool:
    """Check if an NVIDIA GPU has tensor cores based on name."""
    name_upper = gpu_name.upper()
    return any(family in name_upper for family in _TENSOR_CORE_FAMILIES)


@functools.lru_cache(maxsize=1)
def _detect_vendor() -> Optional[str]:
    """Detect GPU vendor, caching the result to avoid duplicate subprocess calls.

    Issue #1990: Both check_gpu_availability() and detect_gpu_capabilities()
    need the vendor — this runs detection once and caches the result.
    Issue #2222: Stashes the NVIDIA GPU name from the initial probe so
    _detect_nvidia_capabilities() can skip its redundant nvidia-smi call.
    Use _detect_vendor.cache_clear() to reset (e.g. in tests).
    """
    global _nvidia_gpu_name
    nvidia_name = _check_nvidia_gpu()
    if nvidia_name:
        _nvidia_gpu_name = nvidia_name
        return "nvidia"
    if _check_amd_gpu():
        return "amd"
    if _check_intel_gpu():
        return "intel"
    return None


def check_gpu_availability() -> bool:
    """Check if any supported GPU is available."""
    return _detect_vendor() is not None


def detect_gpu_capabilities(gpu_available: bool) -> GPUCapabilities:
    """Detect GPU capabilities and features."""
    capabilities = GPUCapabilities()

    if not gpu_available:
        return capabilities

    vendor = _detect_vendor()
    if vendor == "nvidia":
        capabilities = _detect_nvidia_capabilities(capabilities)
    elif vendor == "amd":
        capabilities.vendor = "amd"
        capabilities = _detect_amd_capabilities(capabilities)
    elif vendor == "intel":
        capabilities.vendor = "intel"
        capabilities.name = "Intel GPU (detected via sysfs)"

    return capabilities


def _detect_nvidia_capabilities(
    capabilities: GPUCapabilities,
) -> GPUCapabilities:
    """Detect NVIDIA GPU capabilities via nvidia-smi + pynvml.

    Issue #2222: Reuses the GPU name stashed by _detect_vendor() and
    queries only memory.total + cuda_version from nvidia-smi.
    """
    capabilities.vendor = "nvidia"
    gpu_name = _nvidia_gpu_name
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,cuda_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            if len(parts) >= 2:
                memory_mb = int(parts[0].strip())
                cuda_version = parts[1].strip()

                capabilities.name = gpu_name or "NVIDIA GPU"
                capabilities.memory_gb = round(memory_mb / 1024, 1)
                capabilities.cuda_version = cuda_version
                capabilities.tensor_cores = _has_tensor_cores(gpu_name or "")
                capabilities.mixed_precision = True
    except Exception as e:
        logger.error("Error detecting NVIDIA GPU capabilities: %s", e)

    capabilities = _detect_detailed_capabilities(capabilities)
    return capabilities


def _detect_amd_capabilities(
    capabilities: GPUCapabilities,
) -> GPUCapabilities:
    """Detect AMD GPU capabilities via rocm-smi."""
    try:
        result = subprocess.run(
            ["rocm-smi", "--showproductname"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                if "GPU" in line or ":" in line:
                    capabilities.name = line.strip()
                    break

        mem_result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if mem_result.returncode == 0:
            for line in mem_result.stdout.splitlines():
                if "total" in line.lower():
                    parts = line.split()
                    for part in parts:
                        try:
                            mem_mb = float(part)
                            if mem_mb > 100:
                                capabilities.memory_gb = round(mem_mb / 1024, 1)
                                break
                        except ValueError:
                            continue
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception as e:
        logger.error("Error detecting AMD GPU capabilities: %s", e)
    return capabilities


def _detect_detailed_capabilities(
    capabilities: GPUCapabilities,
) -> GPUCapabilities:
    """Detect detailed capabilities using pynvml if available."""
    try:
        import pynvml

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)

        major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
        capabilities.compute_capability = f"{major}.{minor}"

        multiprocessor_count = pynvml.nvmlDeviceGetMultiProcessorCount(handle)
        capabilities.multiprocessor_count = multiprocessor_count

        pynvml.nvmlShutdown()

    except ImportError:
        logger.debug("pynvml not available for detailed GPU capabilities")
    except Exception as e:
        logger.debug("Failed to get detailed GPU capabilities: %s", e)

    return capabilities


def get_gpu_capabilities_dict(
    gpu_available: bool,
) -> Dict[str, Any]:
    """Get GPU capabilities as a dictionary (legacy interface)."""
    capabilities = detect_gpu_capabilities(gpu_available)
    return capabilities.to_dict()
