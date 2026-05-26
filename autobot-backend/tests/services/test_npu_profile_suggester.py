# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Table-driven unit tests for npu_profile_suggester (GH#6738).

Tests profile selection rules, model recommendation, compute class classification,
and capabilities summary generation without any external dependencies.
"""

import pytest

from services.npu_profile_suggester import (
    ProfileSuggestion,
    _capabilities_summary,
    _compute_class,
    _max_vram_gb,
    _recommend_models,
    suggest_profile,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _gpu_health(vram_gb: float, name: str = "RTX 3060") -> dict:
    """Minimal health dict with a single CUDA device."""
    return {
        "gpu": {
            "cuda_available": True,
            "cuda_devices": [{"name": name, "memory_gb": vram_gb}],
        },
        "ram": {"total_gb": 32.0, "available_gb": 20.0},
        "cpu": {"count": 16},
    }


def _cpu_health(ram_gb: float) -> dict:
    """Minimal health dict with no GPU."""
    return {
        "gpu": {"cuda_available": False, "cuda_devices": []},
        "ram": {"total_gb": ram_gb, "available_gb": ram_gb * 0.8},
        "cpu": {"count": 8},
    }


# ---------------------------------------------------------------------------
# _max_vram_gb
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "health,expected",
    [
        (_gpu_health(8.0), 8.0),
        (_gpu_health(24.0), 24.0),
        (_cpu_health(32.0), 0.0),
        ({}, 0.0),
        ({"gpu": {"cuda_devices": []}}, 0.0),
        (
            {
                "gpu": {
                    "cuda_devices": [
                        {"memory_gb": 8.0},
                        {"memory_gb": 16.0},
                    ]
                }
            },
            16.0,
        ),
    ],
)
def test_max_vram_gb(health, expected):
    assert _max_vram_gb(health) == expected


# ---------------------------------------------------------------------------
# _compute_class
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "health,vram_gb,expected",
    [
        (_gpu_health(8.0), 8.0, "consumer-gpu"),
        (_gpu_health(40.0, "A100"), 40.0, "datacenter-gpu"),
        (_cpu_health(32.0), 0.0, "cpu-only"),
        ({"architecture": "arm64", "os": "Darwin"}, 0.0, "apple-silicon"),
    ],
)
def test_compute_class(health, vram_gb, expected):
    assert _compute_class(health, vram_gb) == expected


# ---------------------------------------------------------------------------
# _recommend_models
# ---------------------------------------------------------------------------

_SAMPLE_TIERS = [
    {"min_vram_gb": 4, "models": [{"id": "gemma-3-1b", "reason": "fits 4GB"}]},
    {"min_vram_gb": 8, "models": [{"id": "gemma-3-4b", "reason": "fits 8GB"}]},
    {"min_vram_gb": 12, "models": [{"id": "qwen2.5-7b", "reason": "fits 12GB"}]},
]


@pytest.mark.parametrize(
    "vram_gb,expected_ids",
    [
        (0.0, []),
        (4.0, ["gemma-3-1b"]),
        (8.0, ["gemma-3-1b", "gemma-3-4b"]),
        (12.0, ["gemma-3-1b", "gemma-3-4b", "qwen2.5-7b"]),
        (100.0, ["gemma-3-1b", "gemma-3-4b", "qwen2.5-7b"]),
    ],
)
def test_recommend_models(vram_gb, expected_ids):
    models = _recommend_models(vram_gb, _SAMPLE_TIERS)
    assert [m["id"] for m in models] == expected_ids


# ---------------------------------------------------------------------------
# suggest_profile — table-driven profile selection rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "health,expected_profile",
    [
        # GPU ≥ 12GB without ONNX/OpenVINO → inference
        (_gpu_health(12.0), "inference"),
        # GPU ≥ 12GB + OpenVINO + strong CPU → mixed
        (
            {
                **_gpu_health(12.0),
                "openvino_available": True,
                "cpu": {"count": 16},
            },
            "mixed",
        ),
        # GPU 4–8GB without acceleration → inference
        (_gpu_health(6.0), "inference"),
        # GPU 4GB + ONNX + strong CPU → mixed
        (
            {
                **_gpu_health(4.0),
                "onnxruntime_available": True,
                "cpu": {"count": 12},
            },
            "mixed",
        ),
        # No GPU, RAM ≥ 16GB → embedding
        (_cpu_health(32.0), "embedding"),
        (_cpu_health(16.0), "embedding"),
        # No GPU, RAM < 16GB → relay
        (_cpu_health(8.0), "relay"),
        (_cpu_health(4.0), "relay"),
        # GPU below 4GB threshold → treated as no-GPU (relay or embedding)
        (
            {
                **_gpu_health(2.0),
                "ram": {"total_gb": 8.0},
                "cpu": {"count": 4},
            },
            "relay",
        ),
    ],
)
def test_suggest_profile_selection(health, expected_profile):
    suggestion = suggest_profile(health)
    assert suggestion.recommended_profile == expected_profile, (
        f"Expected {expected_profile!r} but got {suggestion.recommended_profile!r} " f"for health={health}"
    )


def test_suggest_profile_returns_models_for_gpu():
    health = _gpu_health(8.0)
    suggestion = suggest_profile(health)
    assert isinstance(suggestion.recommended_models, list)
    assert len(suggestion.recommended_models) > 0
    assert "id" in suggestion.recommended_models[0]
    assert "reason" in suggestion.recommended_models[0]


def test_suggest_profile_no_models_for_cpu_only():
    health = _cpu_health(32.0)
    suggestion = suggest_profile(health)
    # No VRAM → no model recommendations
    assert suggestion.recommended_models == []
    assert suggestion.vram_gb == 0.0


def test_suggest_profile_compute_class_consumer():
    suggestion = suggest_profile(_gpu_health(8.0))
    assert suggestion.compute_class == "consumer-gpu"


def test_suggest_profile_compute_class_datacenter():
    suggestion = suggest_profile(_gpu_health(40.0, "A100"))
    assert suggestion.compute_class == "datacenter-gpu"


def test_suggest_profile_capabilities_summary_contains_gpu_name():
    health = _gpu_health(8.0, "RTX 3060")
    suggestion = suggest_profile(health)
    assert "RTX 3060" in suggestion.capabilities_summary


def test_suggest_profile_capabilities_summary_no_gpu():
    health = _cpu_health(32.0)
    suggestion = suggest_profile(health)
    assert "no GPU" in suggestion.capabilities_summary


def test_suggest_profile_empty_health():
    """suggest_profile must not raise on empty/minimal health data."""
    suggestion = suggest_profile({})
    assert suggestion.recommended_profile in ("relay", "embedding", "inference", "mixed")


def test_suggest_profile_openvino_in_summary():
    health = {
        **_gpu_health(8.0),
        "openvino_available": True,
        "openvino_devices": ["CPU", "GPU.0"],
    }
    suggestion = suggest_profile(health)
    assert "OpenVINO" in suggestion.capabilities_summary
