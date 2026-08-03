# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for #13259: all 5 project_state endpoints dropped their
payload.

Each declared response_model=DataResponse[XResponse] over a flat dict return;
the fix declares the concrete XResponse model directly.
"""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.project_state import router
from project_state_manager import DevelopmentPhase


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


class TestRunValidationResponsePayload:
    def test_returns_the_completion_message_on_the_wire(self):
        client = _make_client()
        mock_manager = MagicMock()
        mock_manager.validate_all_phases.return_value = {}

        with patch("api.project_state.get_project_state_manager", return_value=mock_manager):
            response = client.post("/api/project/validate")

        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "Validation completed"
        assert body["results"] == {}
        assert body["success"] is True


class TestGetValidationReportResponsePayload:
    def test_returns_the_real_report_text_on_the_wire(self):
        client = _make_client()
        mock_manager = MagicMock()
        mock_manager.generate_validation_report.return_value = "# Report\nAll phases green."
        mock_manager.current_phase = DevelopmentPhase.PHASE_1_CORE
        mock_manager.phases = {DevelopmentPhase.PHASE_1_CORE: MagicMock(last_validated=None)}

        with patch("api.project_state.get_project_state_manager", return_value=mock_manager):
            response = client.get("/api/project/report")

        assert response.status_code == 200
        body = response.json()
        assert body["report"] == "# Report\nAll phases green."
        assert body["success"] is True


class TestGetAllPhasesResponsePayload:
    def test_returns_the_real_current_phase_on_the_wire(self):
        client = _make_client()
        mock_manager = MagicMock()
        mock_manager.current_phase = DevelopmentPhase.PHASE_2_ORCHESTRATION
        mock_manager.phases = {}

        with patch("api.project_state.get_project_state_manager", return_value=mock_manager):
            response = client.get("/api/project/phases")

        assert response.status_code == 200
        body = response.json()
        assert body["current_phase"] == "phase_2_orchestration"
        assert body["phases"] == {}


class TestActivatePhaseResponsePayload:
    def test_returns_the_activated_phase_on_the_wire(self):
        client = _make_client()
        mock_manager = MagicMock()
        mock_manager.phases = {DevelopmentPhase.PHASE_1_CORE: MagicMock(is_active=False)}
        mock_manager.current_phase = DevelopmentPhase.PHASE_2_ORCHESTRATION

        with patch("api.project_state.get_project_state_manager", return_value=mock_manager):
            response = client.post("/api/project/phase/phase_1_core/activate")

        assert response.status_code == 200
        body = response.json()
        assert body["current_phase"] == "phase_1_core"
        assert "phase_1_core" in body["message"]
        mock_manager.save_state.assert_called_once()


class TestAutoProgressPhasesResponsePayload:
    def test_returns_the_real_progression_result_on_the_wire(self):
        client = _make_client()
        mock_manager = MagicMock()
        mock_manager.auto_progress_phases.return_value = {"phases_advanced": 2}

        with patch("api.project_state.get_project_state_manager", return_value=mock_manager):
            response = client.post("/api/project/auto-progress")

        assert response.status_code == 200
        body = response.json()
        assert body["progression_result"]["phases_advanced"] == 2
        assert body["message"] == "Auto progression completed"
