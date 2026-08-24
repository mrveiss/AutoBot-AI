# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for Security API endpoints
Tests REST API functionality for security management
"""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import the security API module
from api.security import CommandApprovalRequest, router

# Logger name used by api/security.py (``get_logger(__name__)``). The endpoints
# answer with a generic ``detail`` and keep the underlying exception in the log
# only — see d6659fddf (#1733, CodeQL stack-trace exposure). The error tests below
# pin both halves of that contract.
SECURITY_LOGGER = "api.security"
GENERIC_ERROR_DETAIL = "Internal server error"


class TestSecurityAPI:
    """Test Security API endpoints"""

    def setup_method(self):
        """Set up test fixtures"""
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/security")

        # Mock enhanced security layer
        self.mock_security_layer = MagicMock()
        self.app.state.security_layer = self.mock_security_layer

        self.client = TestClient(self.app)

    def test_get_security_status_success(self):
        """Test successful security status retrieval"""
        # Mock security layer responses
        self.mock_security_layer.get_pending_approvals.return_value = []
        self.mock_security_layer.enable_auth = True
        self.mock_security_layer.enable_command_security = True
        self.mock_security_layer.use_docker_sandbox = False

        response = self.client.get("/api/security/status")

        assert response.status_code == 200
        data = response.json()
        assert data["security_enabled"] is True
        assert data["command_security_enabled"] is True
        assert data["docker_sandbox_enabled"] is False
        assert data["pending_approvals"] == []

    def test_get_security_status_with_pending_approvals(self):
        """Test security status with pending approvals"""
        pending_approvals = [
            {"command_id": "cmd_123", "timestamp": "1234567890"},
            {"command_id": "cmd_456", "timestamp": "1234567891"},
        ]

        self.mock_security_layer.get_pending_approvals.return_value = pending_approvals
        self.mock_security_layer.enable_auth = False
        self.mock_security_layer.enable_command_security = True
        self.mock_security_layer.use_docker_sandbox = True

        response = self.client.get("/api/security/status")

        assert response.status_code == 200
        data = response.json()
        assert data["security_enabled"] is False
        assert data["docker_sandbox_enabled"] is True
        assert len(data["pending_approvals"]) == 2

    def test_get_security_status_reads_the_layer_currently_on_app_state(self):
        """Status is read from whichever SecurityLayer app.state holds right now.

        This test used to assert a "fall back to the basic security layer" branch
        that hard-coded command_security_enabled/docker_sandbox_enabled to False
        and pending_approvals to []. That branch existed only while there were two
        classes on two different app.state attributes (enhanced_security_layer vs
        security_layer); ee20dd6c7 (#10666) folded EnhancedSecurityLayer into the
        single canonical SecurityLayer, which always defines all four attributes
        (security_layer.py:99-109), so the branch was correctly removed.

        What is worth pinning on the surviving single-path implementation is that
        the endpoint re-reads app.state per request — a layer swapped in after
        startup is the one reported, no new SecurityLayer is constructed while one
        is present, and every value is mirrored from the layer rather than
        hard-coded.
        """
        delattr(self.app.state, "security_layer")

        replacement_layer = MagicMock()
        replacement_layer.enable_auth = True
        replacement_layer.enable_command_security = False
        replacement_layer.use_docker_sandbox = False
        replacement_layer.get_pending_approvals.return_value = []
        self.app.state.security_layer = replacement_layer

        with patch("api.security.SecurityLayer") as MockSecurityLayer:
            response = self.client.get("/api/security/status")

        assert response.status_code == 200
        data = response.json()
        assert data["security_enabled"] is True
        assert data["command_security_enabled"] is False
        assert data["docker_sandbox_enabled"] is False
        assert data["pending_approvals"] == []

        # The replacement layer was the one consulted...
        replacement_layer.get_pending_approvals.assert_called_once()
        # ...the layer removed from app.state was not...
        self.mock_security_layer.get_pending_approvals.assert_not_called()
        # ...and no redundant layer was built while one was already installed.
        MockSecurityLayer.assert_not_called()

    def test_get_security_status_on_demand_initialization(self):
        """Test security status with on-demand initialization"""
        # Remove both security layers
        delattr(self.app.state, "security_layer")

        with patch("api.security.SecurityLayer") as MockSecurityLayer:
            mock_instance = MagicMock()
            mock_instance.get_pending_approvals.return_value = []
            mock_instance.enable_auth = False
            mock_instance.enable_command_security = True
            mock_instance.use_docker_sandbox = False
            MockSecurityLayer.return_value = mock_instance

            response = self.client.get("/api/security/status")

            assert response.status_code == 200
            data = response.json()
            assert data["command_security_enabled"] is True

            # Check that security layer was initialized and stored
            assert hasattr(self.app.state, "security_layer")
            MockSecurityLayer.assert_called_once()

    def test_get_security_status_error(self, caplog):
        """Failures answer 500 with a generic detail and log the real cause."""
        self.mock_security_layer.get_pending_approvals.side_effect = Exception("Test error")

        with caplog.at_level(logging.ERROR, logger=SECURITY_LOGGER):
            response = self.client.get("/api/security/status")

        assert response.status_code == 500
        assert response.json()["detail"] == GENERIC_ERROR_DETAIL
        assert "Test error" not in response.text
        assert "Test error" in caplog.text

    def test_approve_command_success(self):
        """Test successful command approval"""
        approval_request = {"command_id": "cmd_123", "approved": True}

        response = self.client.post("/api/security/approve-command", json=approval_request)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cmd_123 approved" in data["message"]

        # Verify security layer was called
        self.mock_security_layer.approve_command.assert_called_once_with("cmd_123", True)

    def test_approve_command_denial(self):
        """Test command approval denial"""
        approval_request = {"command_id": "cmd_456", "approved": False}

        response = self.client.post("/api/security/approve-command", json=approval_request)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cmd_456 denied" in data["message"]

        self.mock_security_layer.approve_command.assert_called_once_with("cmd_456", False)

    def test_approve_command_error(self, caplog):
        """Failures answer 500 with a generic detail and log the real cause."""
        self.mock_security_layer.approve_command.side_effect = Exception("Approval error")

        approval_request = {"command_id": "cmd_123", "approved": True}

        with caplog.at_level(logging.ERROR, logger=SECURITY_LOGGER):
            response = self.client.post("/api/security/approve-command", json=approval_request)

        assert response.status_code == 500
        assert response.json()["detail"] == GENERIC_ERROR_DETAIL
        assert "Approval error" not in response.text
        assert "Approval error" in caplog.text

    def test_get_pending_approvals_success(self):
        """Test successful pending approvals retrieval"""
        pending_approvals = [
            {"command_id": "cmd_123", "timestamp": "1234567890"},
            {"command_id": "cmd_456", "timestamp": "1234567891"},
        ]

        self.mock_security_layer.get_pending_approvals.return_value = pending_approvals

        response = self.client.get("/api/security/pending-approvals")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 2
        assert data["pending_approvals"] == pending_approvals

    def test_get_pending_approvals_empty(self):
        """Test pending approvals retrieval when empty"""
        self.mock_security_layer.get_pending_approvals.return_value = []

        response = self.client.get("/api/security/pending-approvals")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 0
        assert data["pending_approvals"] == []

    def test_get_pending_approvals_error(self, caplog):
        """Failures answer 500 with a generic detail and log the real cause."""
        self.mock_security_layer.get_pending_approvals.side_effect = Exception("Database error")

        with caplog.at_level(logging.ERROR, logger=SECURITY_LOGGER):
            response = self.client.get("/api/security/pending-approvals")

        assert response.status_code == 500
        assert response.json()["detail"] == GENERIC_ERROR_DETAIL
        assert "Database error" not in response.text
        assert "Database error" in caplog.text

    def test_get_command_history_success(self):
        """Test successful command history retrieval"""
        command_history = [
            {
                "timestamp": "2023-01-01T10:00:00",
                "user": "test_user",
                "action": "command_execution_attempt",
                "outcome": "success",
                "details": {"command": "ls -la"},
            },
            {
                "timestamp": "2023-01-01T10:00:01",
                "user": "test_user",
                "action": "command_execution_complete",
                "outcome": "success",
                "details": {"command": "ls -la", "return_code": 0},
            },
        ]

        self.mock_security_layer.get_command_history.return_value = command_history

        response = self.client.get("/api/security/command-history")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 2
        assert data["command_history"] == command_history

    def test_get_command_history_with_filters(self):
        """Test command history retrieval with filters"""
        self.mock_security_layer.get_command_history.return_value = []

        response = self.client.get("/api/security/command-history?user=test_user&limit=10")

        assert response.status_code == 200

        # Verify filters were passed to security layer
        self.mock_security_layer.get_command_history.assert_called_once_with(user="test_user", limit=10)

    def test_get_command_history_default_parameters(self):
        """Test command history with default parameters"""
        self.mock_security_layer.get_command_history.return_value = []

        response = self.client.get("/api/security/command-history")

        assert response.status_code == 200

        # Verify default parameters
        self.mock_security_layer.get_command_history.assert_called_once_with(user=None, limit=50)

    def test_get_command_history_error(self, caplog):
        """Failures answer 500 with a generic detail and log the real cause."""
        self.mock_security_layer.get_command_history.side_effect = Exception("History error")

        with caplog.at_level(logging.ERROR, logger=SECURITY_LOGGER):
            response = self.client.get("/api/security/command-history")

        assert response.status_code == 500
        assert response.json()["detail"] == GENERIC_ERROR_DETAIL
        assert "History error" not in response.text
        assert "History error" in caplog.text

    def _write_audit_log(self, tmp_path, lines):
        """Point the security layer at a real audit log file holding ``lines``.

        api/security.py reads the audit log through ``aiofiles.open``, and
        aiofiles captures the builtin as ``aiofiles.threadpool.sync_open = open``
        at import time — so the ``patch("builtins.open", ...)`` these tests used
        to rely on never intercepted anything and the endpoint was silently
        reading (and failing to find) a literal ``test_audit.log`` in the CWD.
        A real file on disk exercises the actual read/parse path.
        """
        log_file = tmp_path / "audit.log"
        log_file.write_text("".join(lines), encoding="utf-8")
        self.mock_security_layer.audit_log_file = str(log_file)
        return log_file

    def test_get_audit_log_success(self, tmp_path):
        """Test successful audit log retrieval"""
        audit_entries = [
            {
                "timestamp": "2023-01-01T10:00:00",
                "user": "test_user",
                "action": "login",
                "outcome": "success",
            },
            {
                "timestamp": "2023-01-01T10:01:00",
                "user": "test_user",
                "action": "command_execution",
                "outcome": "success",
            },
        ]

        self._write_audit_log(tmp_path, [json.dumps(entry) + "\n" for entry in audit_entries])

        response = self.client.get("/api/security/audit-log")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 2
        assert data["audit_entries"] == audit_entries

    def test_get_audit_log_with_limit(self, tmp_path):
        """Test audit log retrieval with limit parameter"""
        self._write_audit_log(tmp_path, ['{"entry": 1}\n', '{"entry": 2}\n', '{"entry": 3}\n'])

        response = self.client.get("/api/security/audit-log?limit=2")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        # The limit keeps the *most recent* entries, not the first two.
        assert data["audit_entries"] == [{"entry": 2}, {"entry": 3}]

    def test_get_audit_log_file_not_found(self, tmp_path):
        """A log that was never written is an empty log, not an error."""
        self.mock_security_layer.audit_log_file = str(tmp_path / "nonexistent.log")

        response = self.client.get("/api/security/audit-log")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 0
        assert data["audit_entries"] == []

    def test_get_audit_log_malformed_json(self, tmp_path):
        """Test audit log retrieval with malformed JSON entries"""
        self._write_audit_log(
            tmp_path,
            ['{"valid": "entry1"}\n', "invalid json line\n", '{"valid": "entry2"}\n'],
        )

        response = self.client.get("/api/security/audit-log")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 2
        # The unparseable line is skipped; the surrounding valid ones survive.
        assert data["audit_entries"] == [{"valid": "entry1"}, {"valid": "entry2"}]

    def test_get_audit_log_error(self, tmp_path, caplog):
        """An unreadable audit log is a 500, never a silent empty log.

        Reporting ``count: 0`` when the file could not be read would tell an
        admin the audit trail is empty when it is merely inaccessible — see
        #13258. The exception text stays in the log, out of the response.
        """
        self.mock_security_layer.audit_log_file = str(tmp_path / "audit.log")

        with (
            patch(
                "api.security.aiofiles.open",
                side_effect=PermissionError("Permission denied"),
            ),
            caplog.at_level(logging.ERROR, logger=SECURITY_LOGGER),
        ):
            response = self.client.get("/api/security/audit-log")

        assert response.status_code == 500
        assert response.json()["detail"] == GENERIC_ERROR_DETAIL
        assert "Permission denied" not in response.text
        assert "Permission denied" in caplog.text


class TestSecurityAPIModels:
    """Test Pydantic models used in Security API"""

    def test_command_approval_request_valid(self):
        """Test valid CommandApprovalRequest"""
        request_data = {"command_id": "cmd_123", "approved": True}

        request = CommandApprovalRequest(**request_data)
        assert request.command_id == "cmd_123"
        assert request.approved is True

    def test_command_approval_request_denial(self):
        """Test CommandApprovalRequest for denial"""
        request_data = {"command_id": "cmd_456", "approved": False}

        request = CommandApprovalRequest(**request_data)
        assert request.command_id == "cmd_456"
        assert request.approved is False

    def test_command_approval_request_validation(self):
        """Test CommandApprovalRequest validation"""
        # Missing required fields should raise validation error
        with pytest.raises(Exception):  # Pydantic ValidationError
            CommandApprovalRequest()

        # Invalid types should raise validation error
        with pytest.raises(Exception):  # Pydantic ValidationError
            CommandApprovalRequest(command_id=123, approved="not_boolean")


class TestSecurityAPIIntegration:
    """Integration tests for Security API with enhanced security layer"""

    def setup_method(self):
        """Set up test fixtures"""
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/security")

        # Use real enhanced security layer (mocked where needed)
        with patch("api.security.SecurityLayer") as MockSecurityLayer:
            mock_instance = MagicMock()
            mock_instance.enable_auth = False
            mock_instance.enable_command_security = True
            mock_instance.use_docker_sandbox = False
            mock_instance.get_pending_approvals.return_value = []
            mock_instance.get_command_history.return_value = []
            MockSecurityLayer.return_value = mock_instance

            self.client = TestClient(self.app)

    def test_full_approval_workflow(self):
        """Test complete approval workflow"""
        # Get status (should trigger initialization)
        status_response = self.client.get("/api/security/status")
        assert status_response.status_code == 200

        # Check pending approvals
        pending_response = self.client.get("/api/security/pending-approvals")
        assert pending_response.status_code == 200

        # Approve a command
        approval_response = self.client.post(
            "/api/security/approve-command",
            json={"command_id": "cmd_test", "approved": True},
        )
        assert approval_response.status_code == 200

    def test_api_error_consistency(self, caplog):
        """Test that all endpoints handle errors consistently"""
        # Remove enhanced security layer to trigger error
        if hasattr(self.app.state, "security_layer"):
            delattr(self.app.state, "security_layer")

        with (
            patch(
                "api.security.SecurityLayer",
                side_effect=Exception("Init error"),
            ),
            caplog.at_level(logging.ERROR, logger=SECURITY_LOGGER),
        ):
            response = self.client.get("/api/security/status")

        assert response.status_code == 500
        assert response.json()["detail"] == GENERIC_ERROR_DETAIL
        assert "Init error" not in response.text
        assert "Init error" in caplog.text


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
