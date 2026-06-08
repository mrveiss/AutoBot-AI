# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for model memory estimation functions. Issue #1966.

Covers:
- estimate_model_memory_gb() across all supported quantization levels
- _parse_parameter_billions() for all documented string formats
- ModelInfo.fits_resource_constraints() with SystemResources and dict resources
"""

import pytest

from utils.model_optimization.types import (
    ModelInfo,
    ModelPerformanceLevel,
    SystemResources,
    _parse_parameter_billions,
    estimate_model_memory_gb,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model(
    param_size: str,
    quant: str,
    perf_level: ModelPerformanceLevel = ModelPerformanceLevel.STANDARD,
) -> ModelInfo:
    """Build a minimal ModelInfo for testing."""
    return ModelInfo(
        name="test-model",
        size_gb=4.0,
        parameter_size=param_size,
        quantization=quant,
        family="llama",
        performance_level=perf_level,
    )


# ---------------------------------------------------------------------------
# _parse_parameter_billions
# ---------------------------------------------------------------------------


class TestParseParameterBillions:
    """Unit tests for the parameter-size string parser."""

    def test_whole_billions(self):
        assert _parse_parameter_billions("7B") == pytest.approx(7.0)

    def test_large_billions(self):
        assert _parse_parameter_billions("70B") == pytest.approx(70.0)

    def test_13b(self):
        assert _parse_parameter_billions("13B") == pytest.approx(13.0)

    def test_fractional_billions(self):
        assert _parse_parameter_billions("1.5B") == pytest.approx(1.5)

    def test_small_fractional_billions(self):
        assert _parse_parameter_billions("0.5B") == pytest.approx(0.5)

    def test_millions_to_billions(self):
        # 500M → 0.5B
        assert _parse_parameter_billions("500M") == pytest.approx(0.5)

    def test_2000m_equals_2b(self):
        assert _parse_parameter_billions("2000M") == pytest.approx(2.0)

    def test_lowercase_b(self):
        """Parser must be case-insensitive (strips upper())."""
        assert _parse_parameter_billions("7b") == pytest.approx(7.0)

    def test_lowercase_m(self):
        assert _parse_parameter_billions("500m") == pytest.approx(0.5)

    def test_whitespace_stripped(self):
        assert _parse_parameter_billions("  13B  ") == pytest.approx(13.0)

    def test_invalid_string_returns_default_7b(self):
        """Completely non-numeric input returns the 7B default."""
        result = _parse_parameter_billions("unknown")
        assert result == pytest.approx(7.0)

    def test_empty_string_returns_default_7b(self):
        result = _parse_parameter_billions("")
        assert result == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# estimate_model_memory_gb — quantization coverage
# ---------------------------------------------------------------------------


class TestEstimateModelMemoryGBQuantizations:
    """Verify weight + KV-cache + overhead formula for all BPP entries."""

    def _expected(self, params_b: float, bpp: float, ctx: int = 2048) -> float:
        return params_b * bpp + 0.000008 * params_b * ctx + 0.5

    # Full-precision variants
    def test_f32(self):
        result = estimate_model_memory_gb("7B", "F32")
        assert result == pytest.approx(self._expected(7.0, 4.0), rel=1e-4)

    def test_f16(self):
        result = estimate_model_memory_gb("7B", "F16")
        assert result == pytest.approx(self._expected(7.0, 2.0), rel=1e-4)

    def test_bf16(self):
        result = estimate_model_memory_gb("7B", "BF16")
        assert result == pytest.approx(self._expected(7.0, 2.0), rel=1e-4)

    # 8-bit variants
    def test_q8_0(self):
        result = estimate_model_memory_gb("7B", "Q8_0")
        assert result == pytest.approx(self._expected(7.0, 1.0), rel=1e-4)

    def test_q8_alias(self):
        result = estimate_model_memory_gb("7B", "Q8")
        assert result == pytest.approx(self._expected(7.0, 1.0), rel=1e-4)

    # 6-bit
    def test_q6_k(self):
        result = estimate_model_memory_gb("7B", "Q6_K")
        assert result == pytest.approx(self._expected(7.0, 0.75), rel=1e-4)

    # 5-bit variants
    def test_q5_k_m(self):
        result = estimate_model_memory_gb("7B", "Q5_K_M")
        assert result == pytest.approx(self._expected(7.0, 0.625), rel=1e-4)

    def test_q5_k_s(self):
        result = estimate_model_memory_gb("7B", "Q5_K_S")
        assert result == pytest.approx(self._expected(7.0, 0.625), rel=1e-4)

    def test_q5_1(self):
        result = estimate_model_memory_gb("7B", "Q5_1")
        assert result == pytest.approx(self._expected(7.0, 0.625), rel=1e-4)

    def test_q5_0(self):
        result = estimate_model_memory_gb("7B", "Q5_0")
        assert result == pytest.approx(self._expected(7.0, 0.625), rel=1e-4)

    # 4-bit variants
    def test_q4_k_m(self):
        result = estimate_model_memory_gb("7B", "Q4_K_M")
        assert result == pytest.approx(self._expected(7.0, 0.5), rel=1e-4)

    def test_q4_k_s(self):
        result = estimate_model_memory_gb("7B", "Q4_K_S")
        assert result == pytest.approx(self._expected(7.0, 0.5), rel=1e-4)

    def test_q4_1(self):
        result = estimate_model_memory_gb("7B", "Q4_1")
        assert result == pytest.approx(self._expected(7.0, 0.5), rel=1e-4)

    def test_q4_0(self):
        result = estimate_model_memory_gb("7B", "Q4_0")
        assert result == pytest.approx(self._expected(7.0, 0.5), rel=1e-4)

    # 3-bit variants
    def test_q3_k_m(self):
        result = estimate_model_memory_gb("7B", "Q3_K_M")
        assert result == pytest.approx(self._expected(7.0, 0.375), rel=1e-4)

    def test_q3_k_s(self):
        result = estimate_model_memory_gb("7B", "Q3_K_S")
        assert result == pytest.approx(self._expected(7.0, 0.375), rel=1e-4)

    def test_q3_k_l(self):
        result = estimate_model_memory_gb("7B", "Q3_K_L")
        assert result == pytest.approx(self._expected(7.0, 0.375), rel=1e-4)

    # 2-bit
    def test_q2_k(self):
        result = estimate_model_memory_gb("7B", "Q2_K")
        assert result == pytest.approx(self._expected(7.0, 0.25), rel=1e-4)

    # i-quant variants
    def test_iq4_xs(self):
        result = estimate_model_memory_gb("7B", "IQ4_XS")
        assert result == pytest.approx(self._expected(7.0, 0.5), rel=1e-4)

    def test_iq3_xxs(self):
        result = estimate_model_memory_gb("7B", "IQ3_XXS")
        assert result == pytest.approx(self._expected(7.0, 0.375), rel=1e-4)

    def test_iq2_xxs(self):
        result = estimate_model_memory_gb("7B", "IQ2_XXS")
        assert result == pytest.approx(self._expected(7.0, 0.25), rel=1e-4)

    # Unknown quantization falls back to _DEFAULT_BPP = 0.5
    def test_unknown_quant_uses_default_bpp(self):
        result = estimate_model_memory_gb("7B", "CUSTOM_QUANT")
        assert result == pytest.approx(self._expected(7.0, 0.5), rel=1e-4)

    # Context tokens affect KV-cache component
    def test_larger_context_increases_estimate(self):
        mem_2k = estimate_model_memory_gb("7B", "Q4_K_M", context_tokens=2048)
        mem_8k = estimate_model_memory_gb("7B", "Q4_K_M", context_tokens=8192)
        assert mem_8k > mem_2k

    def test_zero_context_omits_kv_cache(self):
        mem = estimate_model_memory_gb("7B", "Q4_K_M", context_tokens=0)
        # Only weight storage + overhead
        expected = 7.0 * 0.5 + 0.5
        assert mem == pytest.approx(expected, rel=1e-4)

    # Sub-billion models
    def test_500m_model_small(self):
        result = estimate_model_memory_gb("500M", "Q4_K_M")
        assert result < 2.0

    # Large models
    def test_70b_model_large(self):
        result = estimate_model_memory_gb("70B", "Q4_K_M")
        assert result > 35.0

    def test_case_insensitive_quant(self):
        """Quantization lookup must be case-insensitive."""
        upper = estimate_model_memory_gb("7B", "Q4_K_M")
        lower = estimate_model_memory_gb("7B", "q4_k_m")
        assert upper == pytest.approx(lower, rel=1e-4)


# ---------------------------------------------------------------------------
# ModelInfo.fits_resource_constraints
# ---------------------------------------------------------------------------


class TestFitsResourceConstraints:
    """Test fits_resource_constraints with SystemResources and dict resources."""

    # --- SystemResources API ---

    def test_model_fits_ample_ram(self):
        """A small model fits in a system with plenty of RAM."""
        model = _make_model("7B", "Q4_K_M")
        resources = SystemResources(
            cpu_percent=30.0,
            memory_percent=40.0,
            available_memory_gb=32.0,
        )
        assert model.fits_resource_constraints(resources) is True

    def test_model_rejected_insufficient_ram(self):
        """A 70B model cannot fit in 4 GB RAM."""
        model = _make_model("70B", "Q4_K_M", ModelPerformanceLevel.ADVANCED)
        resources = SystemResources(
            cpu_percent=30.0,
            memory_percent=40.0,
            available_memory_gb=4.0,
        )
        assert model.fits_resource_constraints(resources) is False

    def test_high_cpu_reduces_limit_to_1gb(self):
        """When CPU > 90%, only sub-1GB models are allowed."""
        model = _make_model("7B", "Q4_K_M")
        resources = SystemResources(
            cpu_percent=95.0,
            memory_percent=50.0,
            available_memory_gb=32.0,
        )
        assert model.fits_resource_constraints(resources) is False

    def test_very_low_available_memory_blocks_all_but_tiny(self):
        """When available RAM < 2 GB, only sub-1GB models are allowed."""
        model = _make_model("7B", "Q4_K_M")
        resources = SystemResources(
            cpu_percent=30.0,
            memory_percent=95.0,
            available_memory_gb=1.0,
        )
        assert model.fits_resource_constraints(resources) is False

    def test_model_exceeds_vram_rejected(self):
        """Model that exceeds GPU VRAM must be rejected even with ample RAM."""
        model = _make_model("70B", "Q4_K_M", ModelPerformanceLevel.ADVANCED)
        resources = SystemResources(
            cpu_percent=20.0,
            memory_percent=20.0,
            available_memory_gb=128.0,
            gpu_vram_gb=8.0,
        )
        assert model.fits_resource_constraints(resources) is False

    def test_model_fits_vram(self):
        """Small model fits in available VRAM."""
        model = _make_model("3.8B", "Q4_K_M", ModelPerformanceLevel.LIGHTWEIGHT)
        resources = SystemResources(
            cpu_percent=20.0,
            memory_percent=20.0,
            available_memory_gb=32.0,
            gpu_vram_gb=8.0,
        )
        assert model.fits_resource_constraints(resources) is True

    def test_zero_vram_skips_vram_check(self):
        """gpu_vram_gb=0 means no GPU info — only RAM check applies."""
        model = _make_model("7B", "Q4_K_M")
        resources = SystemResources(
            cpu_percent=20.0,
            memory_percent=20.0,
            available_memory_gb=32.0,
            gpu_vram_gb=0.0,
        )
        assert model.fits_resource_constraints(resources) is True

    # --- Dict API (backward compatibility) ---

    def test_dict_api_model_fits(self):
        """Dict resource API allows a model when RAM is ample."""
        model = _make_model("7B", "Q4_K_M")
        resources = {
            "cpu_percent": 30.0,
            "memory_percent": 40.0,
            "available_memory_gb": 32.0,
        }
        assert model.fits_resource_constraints(resources) is True

    def test_dict_api_model_rejected_insufficient_ram(self):
        """Dict resource API rejects model when RAM is too low."""
        model = _make_model("70B", "Q4_K_M", ModelPerformanceLevel.ADVANCED)
        resources = {
            "cpu_percent": 30.0,
            "memory_percent": 40.0,
            "available_memory_gb": 4.0,
        }
        assert model.fits_resource_constraints(resources) is False

    def test_dict_api_high_cpu_blocks_model(self):
        """Dict resource API respects high CPU check."""
        model = _make_model("7B", "Q4_K_M")
        resources = {
            "cpu_percent": 95.0,
            "memory_percent": 50.0,
            "available_memory_gb": 32.0,
        }
        assert model.fits_resource_constraints(resources) is False

    def test_dict_api_missing_keys_use_defaults(self):
        """Dict with missing keys falls back to safe defaults (8 GB, 50%)."""
        model = _make_model("7B", "Q4_K_M")
        # Empty dict → defaults: cpu=50, available_memory=8 GB → 80% = 6.4 GB
        # 7B Q4_K_M estimate ≈ 4.1 GB → should fit
        assert model.fits_resource_constraints({}) is True

    def test_dict_api_with_gpu_vram_gb(self):
        """Dict resource API respects gpu_vram_gb when present (Issue #1966)."""
        model = _make_model("70B", "Q4_K_M", ModelPerformanceLevel.ADVANCED)
        resources = {
            "cpu_percent": 20.0,
            "memory_percent": 20.0,
            "available_memory_gb": 128.0,
            "gpu_vram_gb": 8.0,
        }
        # 70B Q4 ≫ 8 GB VRAM
        assert model.fits_resource_constraints(resources) is False

    def test_dict_api_without_gpu_vram_gb_no_vram_check(self):
        """Dict without gpu_vram_gb key treats VRAM as 0 (no VRAM check)."""
        model = _make_model("70B", "Q4_K_M", ModelPerformanceLevel.ADVANCED)
        # Lots of RAM but no gpu_vram_gb key — should fall through to RAM check
        resources = {
            "cpu_percent": 20.0,
            "memory_percent": 20.0,
            "available_memory_gb": 128.0,
        }
        # 70B Q4 ≈ 35+ GB, 80% of 128 = 102.4 GB → fits RAM
        assert model.fits_resource_constraints(resources) is True
