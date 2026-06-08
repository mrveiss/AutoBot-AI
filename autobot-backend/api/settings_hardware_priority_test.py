# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for PATCH /api/settings/hardware-priority (Issue #3288)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.settings import HardwarePriorityRequest, router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    """Minimal FastAPI app that mounts only the settings router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/settings")
    return app


# ---------------------------------------------------------------------------
# Unit tests — HardwarePriorityRequest validation
# ---------------------------------------------------------------------------


class TestHardwarePriorityRequest:
    def test_valid_npu_first(self):
        req = HardwarePriorityRequest(priority_order=["npu", "gpu", "cpu"])
        assert req.priority_order == ["npu", "gpu", "cpu"]

    def test_valid_gpu_first(self):
        req = HardwarePriorityRequest(priority_order=["gpu", "npu", "cpu"])
        assert req.priority_order == ["gpu", "npu", "cpu"]

    def test_valid_cpu_first(self):
        req = HardwarePriorityRequest(priority_order=["cpu", "gpu", "npu"])
        assert req.priority_order == ["cpu", "gpu", "npu"]

    def test_rejects_missing_type(self):
        with pytest.raises(Exception):
            HardwarePriorityRequest(priority_order=["npu", "gpu"])

    def test_rejects_duplicate(self):
        with pytest.raises(Exception):
            HardwarePriorityRequest(priority_order=["npu", "npu", "cpu"])

    def test_rejects_invalid_value(self):
        with pytest.raises(Exception):
            HardwarePriorityRequest(priority_order=["npu", "gpu", "fpga"])

    def test_rejects_extra_values(self):
        with pytest.raises(Exception):
            HardwarePriorityRequest(priority_order=["npu", "gpu", "cpu", "cpu"])


# ---------------------------------------------------------------------------
# Integration tests — endpoint via TestClient
# ---------------------------------------------------------------------------


_FAKE_CONFIG = {
    "hardware": {
        "acceleration": {
            "priority_order": ["npu", "gpu", "cpu"],
        }
    }
}


class TestHardwarePriorityEndpoint:
    def test_patch_returns_200_with_valid_payload(self):
        app = _make_app()

        fake_config = {"hardware": {"acceleration": {"priority_order": ["npu", "gpu", "cpu"]}}}
        mock_hw = MagicMock()
        mock_hw.update_priorities = MagicMock()
        mock_revision = MagicMock()
        mock_revision.create_revision = AsyncMock()

        with (
            patch("api.settings.check_admin_permission", return_value=None),
            patch(
                "api.settings.get_db_session",
                return_value=MagicMock(__aenter__=AsyncMock(return_value=MagicMock()), __aexit__=AsyncMock()),
            ),
            patch("api.settings.ConfigService.get_full_config", return_value=dict(fake_config)),
            patch("api.settings.ConfigService.save_full_config", return_value={"status": "ok"}),
            patch("api.settings.ConfigRevisionService", return_value=mock_revision),
            patch("hardware_acceleration.get_hardware_acceleration_manager", return_value=mock_hw),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.patch(
                "/api/settings/hardware-priority",
                json={"priority_order": ["gpu", "npu", "cpu"]},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["priority_order"] == ["gpu", "npu", "cpu"]

    def test_patch_rejects_invalid_payload_422(self):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.patch(
            "/api/settings/hardware-priority",
            json={"priority_order": ["npu", "gpu"]},
        )
        assert resp.status_code == 422

    def test_patch_rejects_unknown_device_422(self):
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.patch(
            "/api/settings/hardware-priority",
            json={"priority_order": ["npu", "gpu", "fpga"]},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# HardwareAccelerationManager.update_priorities unit tests
# ---------------------------------------------------------------------------


class TestHardwareAccelerationManagerUpdatePriorities:
    def _make_manager(self):
        """Build a manager instance without triggering real hardware detection."""
        from hardware_acceleration import AccelerationType, HardwareAccelerationManager

        with (
            patch.object(
                HardwareAccelerationManager,
                "_detect_available_hardware",
            ),
            patch.object(
                HardwareAccelerationManager,
                "_configure_device_priorities",
            ),
        ):
            mgr = HardwareAccelerationManager.__new__(HardwareAccelerationManager)
            mgr.available_devices = {
                AccelerationType.NPU: {},
                AccelerationType.GPU: {},
                AccelerationType.CPU: {},
            }
            mgr.device_priorities = [
                AccelerationType.NPU,
                AccelerationType.GPU,
                AccelerationType.CPU,
            ]
            mgr.current_config = {"priority_order": [], "device_assignments": {}, "fallback_chain": []}
            mgr.npu_available = True
            mgr.gpu_available = True
            import psutil

            mgr.cpu_cores = psutil.cpu_count()
        return mgr

    def test_update_reorders_priorities(self):
        from hardware_acceleration import AccelerationType

        mgr = self._make_manager()
        mgr.update_priorities(["gpu", "npu", "cpu"])
        assert mgr.device_priorities[0] == AccelerationType.GPU
        assert mgr.device_priorities[1] == AccelerationType.NPU
        assert mgr.device_priorities[2] == AccelerationType.CPU

    def test_update_raises_on_missing_type(self):
        mgr = self._make_manager()
        with pytest.raises(ValueError, match="permutation"):
            mgr.update_priorities(["npu", "gpu"])

    def test_update_raises_on_duplicate(self):
        mgr = self._make_manager()
        with pytest.raises(ValueError, match="permutation"):
            mgr.update_priorities(["npu", "npu", "cpu"])

    def test_update_raises_on_unknown_value(self):
        mgr = self._make_manager()
        with pytest.raises((ValueError, KeyError)):
            mgr.update_priorities(["npu", "gpu", "tpu"])
