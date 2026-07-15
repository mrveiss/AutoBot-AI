# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for api/monitoring_hardware.py — Issue #10717.

Verifies that:
1. get_gpu_status / get_npu_status proxy real detection results from the
   HardwareAccelerationManager (via the _detect_*_sync helpers).
2. Both async methods fall back to available=False on any error — never raise.
3. Backward-compatible 'available' key is always present in every response.
"""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures / shared payloads
# ---------------------------------------------------------------------------

GPU_DETECTED = {
    "available": True,
    "vendor": "NVIDIA",
    "devices": ["RTX 4070 (12288MB)"],
}

NPU_DETECTED = {
    "available": True,
    "devices": ["NPU"],
    "openvino_support": True,
}

GPU_ABSENT = {"available": False}
NPU_ABSENT = {"available": False}
FALLBACK_GPU = {"available": False, "error": "Detection failed"}
FALLBACK_NPU = {"available": False, "error": "Detection failed"}


# ---------------------------------------------------------------------------
# Test: async methods proxy detection results and never raise
# ---------------------------------------------------------------------------


class TestGetGpuStatus:
    """Unit tests for LocalHardwareMonitor.get_gpu_status."""

    async def test_proxies_detected_gpu(self):
        """When GPU is detected the response includes available=True + real fields."""
        from api.monitoring_hardware import LocalHardwareMonitor

        stub = LocalHardwareMonitor()
        with patch("api.monitoring_hardware._detect_gpu_sync", return_value=GPU_DETECTED):
            result = await stub.get_gpu_status()

        assert result["available"] is True
        assert result["vendor"] == "NVIDIA"
        assert "RTX 4070" in result["devices"][0]

    async def test_proxies_absent_gpu(self):
        """When no GPU is detected available=False is returned cleanly."""
        from api.monitoring_hardware import LocalHardwareMonitor

        stub = LocalHardwareMonitor()
        with patch("api.monitoring_hardware._detect_gpu_sync", return_value=GPU_ABSENT):
            result = await stub.get_gpu_status()

        assert result["available"] is False
        assert "error" not in result

    async def test_never_raises_on_detection_error(self):
        """get_gpu_status must never propagate an exception from _detect_gpu_sync."""
        from api.monitoring_hardware import LocalHardwareMonitor

        stub = LocalHardwareMonitor()
        with patch("api.monitoring_hardware._detect_gpu_sync", side_effect=RuntimeError("boom")):
            try:
                result = await stub.get_gpu_status()
                # asyncio.to_thread can reraise; if the method itself doesn't
                # swallow it the test catches it below.
                assert "available" in result
            except Exception:
                pytest.fail("get_gpu_status raised — it must never propagate exceptions")

    async def test_available_key_always_present(self):
        """'available' key must exist whether GPU is present or absent."""
        from api.monitoring_hardware import LocalHardwareMonitor

        stub = LocalHardwareMonitor()
        for payload in (GPU_DETECTED, GPU_ABSENT, FALLBACK_GPU):
            with patch("api.monitoring_hardware._detect_gpu_sync", return_value=payload):
                result = await stub.get_gpu_status()
            assert "available" in result, f"'available' missing for payload={payload}"


# ---------------------------------------------------------------------------
# Test: async methods proxy NPU detection results and never raise
# ---------------------------------------------------------------------------


class TestGetNpuStatus:
    """Unit tests for LocalHardwareMonitor.get_npu_status."""

    async def test_proxies_detected_npu(self):
        """When NPU is detected the response includes available=True + real fields."""
        from api.monitoring_hardware import LocalHardwareMonitor

        stub = LocalHardwareMonitor()
        with patch("api.monitoring_hardware._detect_npu_sync", return_value=NPU_DETECTED):
            result = await stub.get_npu_status()

        assert result["available"] is True
        assert result["openvino_support"] is True
        assert "NPU" in result["devices"]

    async def test_proxies_absent_npu(self):
        """When no NPU is detected available=False is returned cleanly."""
        from api.monitoring_hardware import LocalHardwareMonitor

        stub = LocalHardwareMonitor()
        with patch("api.monitoring_hardware._detect_npu_sync", return_value=NPU_ABSENT):
            result = await stub.get_npu_status()

        assert result["available"] is False
        assert "error" not in result

    async def test_never_raises_on_detection_error(self):
        """get_npu_status must never propagate an exception from _detect_npu_sync."""
        from api.monitoring_hardware import LocalHardwareMonitor

        stub = LocalHardwareMonitor()
        with patch("api.monitoring_hardware._detect_npu_sync", side_effect=RuntimeError("boom")):
            try:
                result = await stub.get_npu_status()
                assert "available" in result
            except Exception:
                pytest.fail("get_npu_status raised — it must never propagate exceptions")

    async def test_available_key_always_present(self):
        """'available' key must exist whether NPU is present or absent."""
        from api.monitoring_hardware import LocalHardwareMonitor

        stub = LocalHardwareMonitor()
        for payload in (NPU_DETECTED, NPU_ABSENT, FALLBACK_NPU):
            with patch("api.monitoring_hardware._detect_npu_sync", return_value=payload):
                result = await stub.get_npu_status()
            assert "available" in result, f"'available' missing for payload={payload}"


# ---------------------------------------------------------------------------
# Test: _detect_gpu_sync helper (sync detection function)
# ---------------------------------------------------------------------------


class TestDetectGpuSync:
    """Unit tests for the synchronous _detect_gpu_sync helper."""

    def test_returns_real_data_when_gpu_present(self):
        """Correctly maps manager fields into the response dict."""
        from api.monitoring_hardware import _detect_gpu_sync

        mock_mgr = MagicMock()
        mock_mgr.gpu_available = True

        mock_accel_type = MagicMock()
        mock_gpu_key = mock_accel_type.GPU
        mock_mgr.available_devices = {
            mock_gpu_key: {"vendor": "NVIDIA", "devices": ["RTX 4070 (12288MB)"]},
        }

        mock_hw_module = MagicMock()
        mock_hw_module.AccelerationType = mock_accel_type
        mock_hw_module.get_hardware_acceleration_manager.return_value = mock_mgr

        with patch.dict("sys.modules", {"hardware_acceleration": mock_hw_module}):
            result = _detect_gpu_sync()

        assert result["available"] is True
        assert result["vendor"] == "NVIDIA"

    def test_returns_available_false_when_absent(self):
        """Returns available=False without error when mgr.gpu_available is False."""
        from api.monitoring_hardware import _detect_gpu_sync

        mock_mgr = MagicMock()
        mock_mgr.gpu_available = False
        mock_mgr.available_devices = {}

        mock_hw_module = MagicMock()
        mock_hw_module.get_hardware_acceleration_manager.return_value = mock_mgr

        with patch.dict("sys.modules", {"hardware_acceleration": mock_hw_module}):
            result = _detect_gpu_sync()

        assert result["available"] is False
        assert "error" not in result

    def test_returns_fallback_on_import_error(self):
        """Returns available=False + error key when hardware_acceleration is missing."""
        from api.monitoring_hardware import _detect_gpu_sync

        with patch.dict("sys.modules", {"hardware_acceleration": None}):
            result = _detect_gpu_sync()

        assert result["available"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# Test: _detect_npu_sync helper (sync detection function)
# ---------------------------------------------------------------------------


class TestDetectNpuSync:
    """Unit tests for the synchronous _detect_npu_sync helper."""

    def test_returns_real_data_when_npu_present(self):
        """Correctly maps manager fields into the response dict."""
        from api.monitoring_hardware import _detect_npu_sync

        mock_mgr = MagicMock()
        mock_mgr.npu_available = True

        mock_accel_type = MagicMock()
        mock_npu_key = mock_accel_type.NPU
        mock_mgr.available_devices = {
            mock_npu_key: {"openvino_support": True, "devices": ["NPU"]},
        }

        mock_hw_module = MagicMock()
        mock_hw_module.AccelerationType = mock_accel_type
        mock_hw_module.get_hardware_acceleration_manager.return_value = mock_mgr

        with patch.dict("sys.modules", {"hardware_acceleration": mock_hw_module}):
            result = _detect_npu_sync()

        assert result["available"] is True
        assert result["openvino_support"] is True

    def test_returns_available_false_when_absent(self):
        """Returns available=False without error when mgr.npu_available is False."""
        from api.monitoring_hardware import _detect_npu_sync

        mock_mgr = MagicMock()
        mock_mgr.npu_available = False
        mock_mgr.available_devices = {}

        mock_hw_module = MagicMock()
        mock_hw_module.get_hardware_acceleration_manager.return_value = mock_mgr

        with patch.dict("sys.modules", {"hardware_acceleration": mock_hw_module}):
            result = _detect_npu_sync()

        assert result["available"] is False
        assert "error" not in result

    def test_returns_fallback_on_import_error(self):
        """Returns available=False + error key when hardware_acceleration is missing."""
        from api.monitoring_hardware import _detect_npu_sync

        with patch.dict("sys.modules", {"hardware_acceleration": None}):
            result = _detect_npu_sync()

        assert result["available"] is False
        assert "error" in result
