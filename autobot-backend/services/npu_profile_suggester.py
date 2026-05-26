# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Auto-suggest NPU worker profile and recommended models from worker capabilities.

GH#6738: Reads hardware capabilities returned by the worker's /health endpoint
and derives a recommended_profile, recommended_models, compute_class, and
capabilities_summary so the pair-confirm dialog can pre-fill the profile selector.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)

_RECOMMENDATIONS_YAML = os.path.join(
    os.path.dirname(__file__),
    "..",
    "config",
    "npu_model_recommendations.yaml",
)

# Datacenter VRAM threshold (GB) — RTX A/H series start at ~16GB
_DATACENTER_GPU_VRAM_THRESHOLD_GB = 16.0
# "Strong CPU" threshold (logical cores) for mixed-mode decision
_STRONG_CPU_CORE_THRESHOLD = 8
# RAM threshold for embedding-only profile
_EMBEDDING_RAM_THRESHOLD_GB = 16.0
# Minimum GPU VRAM to qualify for inference profile
_MIN_INFERENCE_VRAM_GB = 4.0


@dataclass
class ProfileSuggestion:
    recommended_profile: str
    recommended_models: List[Dict[str, str]]
    vram_gb: float
    compute_class: str
    capabilities_summary: str


def _load_tiers() -> List[Dict[str, Any]]:
    try:
        with open(_RECOMMENDATIONS_YAML, "r") as fh:
            data = yaml.safe_load(fh)
        tiers = data.get("tiers", [])
        return sorted(tiers, key=lambda t: t["min_vram_gb"])
    except Exception as exc:
        logger.warning("Could not load npu_model_recommendations.yaml: %s", exc)
        return []


def _max_vram_gb(health_data: Dict[str, Any]) -> float:
    """Return the largest single-GPU VRAM in GB reported by the worker."""
    gpu = health_data.get("gpu", {})
    cuda_devices = gpu.get("cuda_devices", [])
    if not cuda_devices:
        return 0.0
    return max((d.get("memory_gb", 0.0) for d in cuda_devices), default=0.0)


def _has_strong_cpu(health_data: Dict[str, Any]) -> bool:
    cpu = health_data.get("cpu", {})
    return (cpu.get("count") or 0) >= _STRONG_CPU_CORE_THRESHOLD


def _has_openvino_or_onnx(health_data: Dict[str, Any]) -> bool:
    return bool(health_data.get("openvino_available")) or bool(health_data.get("onnxruntime_available"))


def _compute_class(health_data: Dict[str, Any], vram_gb: float) -> str:
    arch = health_data.get("architecture", "")
    if "arm" in arch.lower() and health_data.get("os") == "Darwin":
        return "apple-silicon"
    if vram_gb >= _DATACENTER_GPU_VRAM_THRESHOLD_GB:
        return "datacenter-gpu"
    if vram_gb > 0.0:
        return "consumer-gpu"
    return "cpu-only"


def _recommend_models(vram_gb: float, tiers: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Return all models from all tiers whose min_vram_gb <= vram_gb."""
    models: List[Dict[str, str]] = []
    for tier in tiers:
        if tier["min_vram_gb"] <= vram_gb:
            for m in tier.get("models", []):
                models.append({"id": m["id"], "reason": m["reason"]})
    return models


def _capabilities_summary(health_data: Dict[str, Any], vram_gb: float) -> str:
    gpu = health_data.get("gpu", {})
    cuda_available = gpu.get("cuda_available", False)
    devices = gpu.get("cuda_devices", [])

    parts: List[str] = []

    # CUDA / GPU info
    if cuda_available and devices:
        device_str = ", ".join(f"{d.get('name', 'GPU')} {d.get('memory_gb', 0):.0f}GB" for d in devices)
        parts.append(f"CUDA, {len(devices)}× {device_str}")
    else:
        parts.append("no GPU")

    # OpenVINO
    if health_data.get("openvino_available"):
        ov_devices = health_data.get("openvino_devices", [])
        parts.append(f"OpenVINO {', '.join(ov_devices) if ov_devices else 'yes'}")

    # ONNX
    if health_data.get("onnxruntime_available"):
        providers = health_data.get("onnxruntime_providers", [])
        parts.append(f"ONNX ({', '.join(providers[:2])})" if providers else "ONNX yes")

    # RAM
    ram = health_data.get("ram", {})
    total_gb = ram.get("total_gb")
    if total_gb:
        parts.append(f"{total_gb:.0f}GB RAM")

    return ", ".join(parts) if parts else "no capabilities detected"


def suggest_profile(health_data: Dict[str, Any]) -> ProfileSuggestion:
    """
    Derive a ProfileSuggestion from worker health / capabilities data.

    Decision table (GH#6738):
    - GPU ≥ 12GB                        → inference (or mixed if also CPU-strong + ONNX/OV)
    - GPU 4–8GB                         → inference (small models)
    - GPU + ONNX/OpenVINO + strong CPU  → mixed
    - No GPU, RAM ≥ 16GB               → embedding
    - No GPU, RAM < 16GB               → relay
    """
    tiers = _load_tiers()
    vram_gb = _max_vram_gb(health_data)
    cls = _compute_class(health_data, vram_gb)
    models = _recommend_models(vram_gb, tiers)
    summary = _capabilities_summary(health_data, vram_gb)

    has_gpu = vram_gb >= _MIN_INFERENCE_VRAM_GB
    has_accel = _has_openvino_or_onnx(health_data)
    strong_cpu = _has_strong_cpu(health_data)
    ram_gb = (health_data.get("ram") or {}).get("total_gb", 0.0) or 0.0

    if has_gpu and has_accel and strong_cpu:
        profile = "mixed"
    elif has_gpu:
        profile = "inference"
    elif ram_gb >= _EMBEDDING_RAM_THRESHOLD_GB:
        profile = "embedding"
    else:
        profile = "relay"

    return ProfileSuggestion(
        recommended_profile=profile,
        recommended_models=models,
        vram_gb=vram_gb,
        compute_class=cls,
        capabilities_summary=summary,
    )
