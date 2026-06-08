# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for VRAM-aware model selection. Issue #1966."""

import pytest

from utils.model_optimization.types import (
    ModelInfo,
    ModelPerformanceLevel,
    SystemResources,
    estimate_model_memory_gb,
)


class TestEstimateModelMemoryGB:
    """Test the standalone memory estimation function."""

    def test_7b_q4_estimate(self):
        mem = estimate_model_memory_gb("7B", "Q4_K_M")
        # 7 * 0.5 + 0.000008 * 7 * 2048 + 0.5 = 3.5 + 0.114 + 0.5 = 4.11
        assert 3.5 < mem < 5.0

    def test_70b_q4_estimate(self):
        mem = estimate_model_memory_gb("70B", "Q4_K_M")
        assert mem > 35.0

    def test_13b_fp16_estimate(self):
        mem = estimate_model_memory_gb("13B", "F16")
        assert mem > 24.0

    def test_500m_model(self):
        mem = estimate_model_memory_gb("500M", "Q4_K_M")
        assert mem < 2.0

    def test_unknown_quant_uses_default(self):
        mem = estimate_model_memory_gb("7B", "UNKNOWN")
        # Falls back to 0.5 bpp
        assert 3.0 < mem < 5.0


class TestModelInfoEstimateMemory:
    """Test ModelInfo.estimate_memory_gb method."""

    def _make_model(self, param_size, quant, size_gb=4.0):
        return ModelInfo(
            name="test",
            size_gb=size_gb,
            parameter_size=param_size,
            quantization=quant,
            family="test",
            performance_level=ModelPerformanceLevel.STANDARD,
        )

    def test_estimate_memory_delegates(self):
        model = self._make_model("7B", "Q4_K_M")
        assert model.estimate_memory_gb() == pytest.approx(estimate_model_memory_gb("7B", "Q4_K_M"), abs=0.01)


class TestSystemResourcesGPUVRAM:
    """Test SystemResources includes gpu_vram_gb field."""

    def test_default_vram_is_zero(self):
        r = SystemResources(cpu_percent=50, memory_percent=50, available_memory_gb=16)
        assert r.gpu_vram_gb == 0.0

    def test_explicit_vram(self):
        r = SystemResources(
            cpu_percent=50,
            memory_percent=50,
            available_memory_gb=16,
            gpu_vram_gb=8.0,
        )
        assert r.gpu_vram_gb == 8.0

    def test_to_dict_includes_vram(self):
        r = SystemResources(
            cpu_percent=50,
            memory_percent=50,
            available_memory_gb=16,
            gpu_vram_gb=8.0,
        )
        d = r.to_dict()
        assert "gpu_vram_gb" in d
        assert d["gpu_vram_gb"] == 8.0


class TestFitsResourceConstraintsWithVRAM:
    """Test that fits_resource_constraints checks VRAM."""

    def _make_model(self, param_size, quant):
        return ModelInfo(
            name="test",
            size_gb=40.0,
            parameter_size=param_size,
            quantization=quant,
            family="test",
            performance_level=ModelPerformanceLevel.ADVANCED,
        )

    def test_model_exceeds_vram_rejected(self):
        resources = SystemResources(
            cpu_percent=30,
            memory_percent=40,
            available_memory_gb=64,
            gpu_vram_gb=8.0,
        )
        big_model = self._make_model("70B", "Q4_K_M")
        assert big_model.fits_resource_constraints(resources) is False

    def test_small_model_fits_vram(self):
        resources = SystemResources(
            cpu_percent=30,
            memory_percent=40,
            available_memory_gb=32,
            gpu_vram_gb=8.0,
        )
        small_model = ModelInfo(
            name="phi3:mini",
            size_gb=2.0,
            parameter_size="3.8B",
            quantization="Q4_K_M",
            family="phi",
            performance_level=ModelPerformanceLevel.LIGHTWEIGHT,
        )
        assert small_model.fits_resource_constraints(resources) is True

    def test_no_vram_skips_vram_check(self):
        resources = SystemResources(
            cpu_percent=30,
            memory_percent=40,
            available_memory_gb=64,
            gpu_vram_gb=0.0,
        )
        model = self._make_model("7B", "Q4_K_M")
        # No VRAM check, only RAM check — should pass with 64GB available
        assert model.fits_resource_constraints(resources) is True
