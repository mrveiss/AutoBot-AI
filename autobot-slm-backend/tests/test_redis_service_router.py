# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for api/redis_service.py (#11340).

Covers:
- Status parsing (_map_active_state): all vocabulary values.
- Action allowlist: valid actions pass; invalid actions raise 400.
- GET /status: subprocess mock → correct status payload.
- POST /{action}: subprocess mock → 200 on success, 500 on non-zero rc.
- POST /{action}: unknown action → 400 (never runs subprocess).
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.redis_service import _map_active_state, router
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

app = FastAPI()
app.include_router(router)
client = TestClient(app)


# ---------------------------------------------------------------------------
# Unit: _map_active_state
# ---------------------------------------------------------------------------


class TestMapActiveState:
    def test_active_maps_to_running(self):
        assert _map_active_state("active\n") == "running"

    def test_inactive_maps_to_stopped(self):
        assert _map_active_state("inactive") == "stopped"

    def test_deactivating_maps_to_stopped(self):
        assert _map_active_state("deactivating") == "stopped"

    def test_failed_maps_to_failed(self):
        assert _map_active_state("failed") == "failed"

    def test_error_maps_to_failed(self):
        assert _map_active_state("error") == "failed"

    def test_unknown_text_maps_to_unknown(self):
        assert _map_active_state("activating") == "unknown"

    def test_empty_maps_to_unknown(self):
        assert _map_active_state("") == "unknown"

    def test_case_insensitive(self):
        assert _map_active_state("ACTIVE") == "running"


# ---------------------------------------------------------------------------
# Integration: GET /status
# ---------------------------------------------------------------------------


class TestGetRedisStatus:
    def test_running_status(self):
        # Patch _run_systemctl to return "active" and _fetch_redis_info for metrics
        with (
            patch("api.redis_service._run_systemctl", new=AsyncMock(return_value=(0, "active\n", ""))),
            patch("api.redis_service._fetch_redis_info", new=AsyncMock(return_value=(120, 1048576, 2097152, 3))),
        ):
            resp = client.get("/redis-service/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["uptime_seconds"] == 120
        assert data["connected_clients"] == 3
        assert "last_checked" in data

    def test_stopped_status(self):
        with patch("api.redis_service._run_systemctl", new=AsyncMock(return_value=(3, "inactive\n", ""))):
            resp = client.get("/redis-service/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    def test_failed_status(self):
        with patch("api.redis_service._run_systemctl", new=AsyncMock(return_value=(3, "failed\n", ""))):
            resp = client.get("/redis-service/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"

    def test_unknown_state_maps_to_unknown(self):
        with patch("api.redis_service._run_systemctl", new=AsyncMock(return_value=(3, "activating\n", ""))):
            resp = client.get("/redis-service/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "unknown"


# ---------------------------------------------------------------------------
# Integration: POST /{action}
# ---------------------------------------------------------------------------


class TestControlRedisService:
    @pytest.mark.parametrize("action", ["start", "stop", "restart"])
    def test_valid_action_succeeds(self, action: str):
        with patch("api.redis_service._run_systemctl", new=AsyncMock(return_value=(0, "", ""))):
            resp = client.post(f"/redis-service/{action}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action"] == action

    @pytest.mark.parametrize("action", ["start", "stop", "restart"])
    def test_valid_action_subprocess_failure_returns_500(self, action: str):
        with patch(
            "api.redis_service._run_systemctl",
            new=AsyncMock(return_value=(1, "", "permission denied")),
        ):
            resp = client.post(f"/redis-service/{action}")
        assert resp.status_code == 500
        assert "permission denied" in resp.json()["detail"]

    @pytest.mark.parametrize(
        "bad_action",
        ["delete", "enable", "disable", "kill", "is-active"],
    )
    def test_invalid_action_returns_400_without_subprocess(self, bad_action: str):
        with patch("api.redis_service._run_systemctl") as mock_systemctl:
            resp = client.post(f"/redis-service/{bad_action}")
        # _run_systemctl must NOT have been called for rejected actions
        mock_systemctl.assert_not_called()
        assert resp.status_code == 400
        assert "Invalid action" in resp.json()["detail"]
