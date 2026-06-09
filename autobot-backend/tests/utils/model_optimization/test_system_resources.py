# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for SystemResourceAnalyzer multi-GPU VRAM detection. Issue #2032.

Covers:
- Single-GPU: _get_gpu_vram_all() returns correct total and per-GPU list
- Multi-GPU: sums free VRAM across all GPUs, per-GPU list has one entry per GPU
- No GPU / pynvml unavailable: returns (0.0, []) gracefully
- Zero-device count: returns (0.0, []) gracefully
- get_current_resources() populates both gpu_vram_gb and per_gpu_vram_gb fields
"""

from unittest.mock import MagicMock, patch

import pytest

from utils.model_optimization.system_resources import SystemResourceAnalyzer
from utils.model_optimization.types import SystemResources

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mem_info(free_bytes: int) -> MagicMock:
    """Create a fake pynvml MemoryInfo object."""
    info = MagicMock()
    info.free = free_bytes
    return info


def _gb(gb: float) -> int:
    """Convert GB float to bytes."""
    return int(gb * (1024**3))


# ---------------------------------------------------------------------------
# _get_gpu_vram_all — unit tests via pynvml mock
# ---------------------------------------------------------------------------


class TestGetGpuVramAll:
    """Unit tests for SystemResourceAnalyzer._get_gpu_vram_all()."""

    def _analyzer(self) -> SystemResourceAnalyzer:
        return SystemResourceAnalyzer()

    def test_no_pynvml_returns_zero(self):
        """When pynvml is not importable, return (0.0, [])."""
        analyzer = self._analyzer()
        with patch.dict("sys.modules", {"pynvml": None}):
            total, per_gpu = analyzer._get_gpu_vram_all()
        assert total == 0.0
        assert per_gpu == []

    def test_pynvml_exception_returns_zero(self):
        """When nvmlInit() raises, return (0.0, []) gracefully."""
        analyzer = self._analyzer()
        mock_pynvml = MagicMock()
        mock_pynvml.nvmlInit.side_effect = RuntimeError("driver not loaded")
        with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
            total, per_gpu = analyzer._get_gpu_vram_all()
        assert total == 0.0
        assert per_gpu == []

    def test_zero_device_count_returns_empty(self):
        """When nvmlDeviceGetCount() returns 0, return (0.0, [])."""
        analyzer = self._analyzer()
        mock_pynvml = MagicMock()
        mock_pynvml.nvmlDeviceGetCount.return_value = 0
        with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
            total, per_gpu = analyzer._get_gpu_vram_all()
        assert total == 0.0
        assert per_gpu == []
        # nvmlShutdown must always be called
        mock_pynvml.nvmlShutdown.assert_called_once()

    def test_single_gpu_correct_total(self):
        """Single GPU: total equals that GPU's free VRAM."""
        analyzer = self._analyzer()
        mock_pynvml = MagicMock()
        mock_pynvml.nvmlDeviceGetCount.return_value = 1
        mock_pynvml.nvmlDeviceGetMemoryInfo.return_value = _make_mem_info(_gb(8.0))
        with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
            total, per_gpu = analyzer._get_gpu_vram_all()
        assert total == pytest.approx(8.0, rel=1e-3)
        assert len(per_gpu) == 1
        assert per_gpu[0] == pytest.approx(8.0, rel=1e-3)

    def test_multi_gpu_sums_free_vram(self):
        """Multi-GPU: total is the sum of all GPUs' free VRAM (#2032)."""
        analyzer = self._analyzer()
        mock_pynvml = MagicMock()
        mock_pynvml.nvmlDeviceGetCount.return_value = 3
        # GPU 0: 8 GB free, GPU 1: 16 GB free, GPU 2: 12 GB free
        mock_pynvml.nvmlDeviceGetMemoryInfo.side_effect = [
            _make_mem_info(_gb(8.0)),
            _make_mem_info(_gb(16.0)),
            _make_mem_info(_gb(12.0)),
        ]
        with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
            total, per_gpu = analyzer._get_gpu_vram_all()
        assert total == pytest.approx(36.0, rel=1e-3)
        assert len(per_gpu) == 3
        assert per_gpu[0] == pytest.approx(8.0, rel=1e-3)
        assert per_gpu[1] == pytest.approx(16.0, rel=1e-3)
        assert per_gpu[2] == pytest.approx(12.0, rel=1e-3)

    def test_multi_gpu_per_gpu_list_order_preserved(self):
        """Per-GPU list preserves GPU index order (#2032)."""
        analyzer = self._analyzer()
        mock_pynvml = MagicMock()
        mock_pynvml.nvmlDeviceGetCount.return_value = 2
        free_values = [_gb(4.0), _gb(24.0)]
        mock_pynvml.nvmlDeviceGetMemoryInfo.side_effect = [_make_mem_info(v) for v in free_values]
        with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
            _, per_gpu = analyzer._get_gpu_vram_all()
        assert per_gpu[0] == pytest.approx(4.0, rel=1e-3)
        assert per_gpu[1] == pytest.approx(24.0, rel=1e-3)

    def test_nvmlshutdown_called_even_on_error(self):
        """nvmlShutdown() is called even when a per-GPU query fails (#2032)."""
        analyzer = self._analyzer()
        mock_pynvml = MagicMock()
        mock_pynvml.nvmlDeviceGetCount.return_value = 2
        # Second GPU raises an error mid-loop
        mock_pynvml.nvmlDeviceGetMemoryInfo.side_effect = [
            _make_mem_info(_gb(8.0)),
            RuntimeError("GPU 1 error"),
        ]
        with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
            total, per_gpu = analyzer._get_gpu_vram_all()
        # Should degrade gracefully to (0.0, [])
        assert total == 0.0
        assert per_gpu == []
        mock_pynvml.nvmlShutdown.assert_called_once()


# ---------------------------------------------------------------------------
# get_current_resources — integration smoke tests
# ---------------------------------------------------------------------------


class TestGetCurrentResourcesMultiGpu:
    """Verify get_current_resources() populates multi-GPU fields correctly (#2032)."""

    def _fake_virtual_memory(self):
        mem = MagicMock()
        mem.percent = 40.0
        mem.available = _gb(32.0)
        return mem

    def test_two_gpu_system_populates_fields(self):
        """get_current_resources() sets gpu_vram_gb and per_gpu_vram_gb."""
        analyzer = SystemResourceAnalyzer()
        mock_pynvml = MagicMock()
        mock_pynvml.nvmlDeviceGetCount.return_value = 2
        mock_pynvml.nvmlDeviceGetMemoryInfo.side_effect = [
            _make_mem_info(_gb(10.0)),
            _make_mem_info(_gb(10.0)),
        ]

        with (
            patch("psutil.cpu_percent", return_value=30.0),
            patch("psutil.virtual_memory", return_value=self._fake_virtual_memory()),
            patch.dict("sys.modules", {"pynvml": mock_pynvml}),
        ):
            resources = analyzer.get_current_resources()

        assert isinstance(resources, SystemResources)
        assert resources.gpu_vram_gb == pytest.approx(20.0, rel=1e-3)
        assert resources.per_gpu_vram_gb == pytest.approx([10.0, 10.0], rel=1e-3)

    def test_no_gpu_gives_zero_vram(self):
        """No GPU system: both VRAM fields are 0 / empty."""
        analyzer = SystemResourceAnalyzer()
        with (
            patch("psutil.cpu_percent", return_value=30.0),
            patch("psutil.virtual_memory", return_value=self._fake_virtual_memory()),
            patch.dict("sys.modules", {"pynvml": None}),
        ):
            resources = analyzer.get_current_resources()

        assert resources.gpu_vram_gb == 0.0
        assert resources.per_gpu_vram_gb == []

    def test_psutil_failure_returns_safe_defaults(self):
        """Crash in psutil path returns safe default SystemResources."""
        analyzer = SystemResourceAnalyzer()
        with patch("psutil.cpu_percent", side_effect=OSError("no proc")):
            resources = analyzer.get_current_resources()

        assert resources.cpu_percent == 50.0
        assert resources.available_memory_gb == 8.0
        assert resources.gpu_vram_gb == 0.0
        assert resources.per_gpu_vram_gb == []


# ---------------------------------------------------------------------------
# SystemResources dataclass — per_gpu_vram_gb field
# ---------------------------------------------------------------------------


class TestSystemResourcesPerGpuField:
    """Verify the per_gpu_vram_gb field on SystemResources (#2032)."""

    def test_default_per_gpu_is_empty_list(self):
        r = SystemResources(cpu_percent=50, memory_percent=50, available_memory_gb=16)
        assert r.per_gpu_vram_gb == []

    def test_explicit_per_gpu_list(self):
        r = SystemResources(
            cpu_percent=50,
            memory_percent=50,
            available_memory_gb=16,
            gpu_vram_gb=24.0,
            per_gpu_vram_gb=[8.0, 16.0],
        )
        assert r.per_gpu_vram_gb == [8.0, 16.0]

    def test_to_dict_includes_per_gpu_vram(self):
        r = SystemResources(
            cpu_percent=50,
            memory_percent=50,
            available_memory_gb=16,
            gpu_vram_gb=24.0,
            per_gpu_vram_gb=[8.0, 16.0],
        )
        d = r.to_dict()
        assert "per_gpu_vram_gb" in d
        assert d["per_gpu_vram_gb"] == [8.0, 16.0]

    def test_to_dict_per_gpu_is_copy(self):
        """to_dict() must return a copy, not the original list."""
        per_gpu = [8.0, 16.0]
        r = SystemResources(
            cpu_percent=50,
            memory_percent=50,
            available_memory_gb=16,
            per_gpu_vram_gb=per_gpu,
        )
        d = r.to_dict()
        d["per_gpu_vram_gb"].append(99.0)
        assert r.per_gpu_vram_gb == [
            8.0,
            16.0,
        ], "to_dict() must not expose internal list"
