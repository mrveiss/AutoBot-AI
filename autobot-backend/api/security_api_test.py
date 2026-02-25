"""
Unit tests for Security API endpoints
Tests REST API functionality for security management
"""

import json
from unittest.mock import MagicMock, patch

import pytest

# Import the security API module
from api.security import CommandApprovalRequest, router
from fastapi import FastAPI
from fastapi.testclient import TestClient


class TestSecurityAPI:
    """Test Security API endpoints"""

    def setup_method(self):
        """Set up test fixtures"""
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/security")

        # Mock enhanced security layer
        self.mock_security_layer = MagicMock()
        self.app.state.enhanced_security_layer = self.mock_security_layer

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

    def test_get_security_status_fallback_to_basic_security(self):
        """Test security status fallback when enhanced security not available"""
        # Remove enhanced security layer, add basic security layer
        delattr(self.app.state, "enhanced_security_layer")

        basic_security = MagicMock()
        basic_security.enable_auth = True
        self.app.state.security_layer = basic_security

        response = self.client.get("/api/security/status")

        assert response.status_code == 200
        data = response.json()
        assert data["security_enabled"] is True
        assert data["command_security_enabled"] is False  # Not available in basic
        assert data["docker_sandbox_enabled"] is False  # Not available in basic
        assert data["pending_approvals"] == []  # Not available in basic

    def test_get_security_status_on_demand_initialization(self):
        """Test security status with on-demand initialization"""
        # Remove both security layers
        delattr(self.app.state, "enhanced_security_layer")

        with patch("api.security.EnhancedSecurityLayer") as MockSecurityLayer:
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
            assert hasattr(self.app.state, "enhanced_security_layer")
            MockSecurityLayer.assert_called_once()

    def test_get_security_status_error(self):
        """Test security status endpoint error handling"""
        self.mock_security_layer.get_pending_approvals.side_effect = Exception(
            "Test error"
        )

        response = self.client.get("/api/security/status")

        assert response.status_code == 500
        data = response.json()
        assert "Test error" in data["detail"]

    def test_approve_command_success(self):
        """Test successful command approval"""
        approval_request = {"command_id": "cmd_123", "approved": True}

        response = self.client.post(
            "/api/security/approve-command", json=approval_request
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cmd_123 approved" in data["message"]

        # Verify security layer was called
        self.mock_security_layer.approve_command.assert_called_once_with(
            "cmd_123", True
        )

    def test_approve_command_denial(self):
        """Test command approval denial"""
        approval_request = {"command_id": "cmd_456", "approved": False}

        response = self.client.post(
            "/api/security/approve-command", json=approval_request
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cmd_456 denied" in data["message"]

        self.mock_security_layer.approve_command.assert_called_once_with(
            "cmd_456", False
        )

    def test_approve_command_error(self):
        """Test command approval error handling"""
        self.mock_security_layer.approve_command.side_effect = Exception(
            "Approval error"
        )

        approval_request = {"command_id": "cmd_123", "approved": True}

        response = self.client.post(
            "/api/security/approve-command", json=approval_request
        )

        assert response.status_code == 500
        data = response.json()
        assert "Approval error" in data["detail"]

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

    def test_get_pending_approvals_error(self):
        """Test pending approvals endpoint error handling"""
        self.mock_security_layer.get_pending_approvals.side_effect = Exception(
            "Database error"
        )

        response = self.client.get("/api/security/pending-approvals")

        assert response.status_code == 500
        data = response.json()
        assert "Database error" in data["detail"]

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

        response = self.client.get(
            "/api/security/command-history?user=test_user&limit=10"
        )

        assert response.status_code == 200

        # Verify filters were passed to security layer
        self.mock_security_layer.get_command_history.assert_called_once_with(
            user="test_user", limit=10
        )

    def test_get_command_history_default_parameters(self):
        """Test command history with default parameters"""
        self.mock_security_layer.get_command_history.return_value = []

        response = self.client.get("/api/security/command-history")

        assert response.status_code == 200

        # Verify default parameters
        self.mock_security_layer.get_command_history.assert_called_once_with(
            user=None, limit=50
        )

    def test_get_command_history_error(self):
        """Test command history endpoint error handling"""
        self.mock_security_layer.get_command_history.side_effect = Exception(
            "History error"
        )

        response = self.client.get("/api/security/command-history")

        assert response.status_code == 500
        data = response.json()
        assert "History error" in data["detail"]

    def test_get_audit_log_success(self):
        """Test successful audit log retrieval"""
        # Mock audit log file content
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

        self.mock_security_layer.audit_log_file = "test_audit.log"

        # Mock file reading
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.readlines.return_value = [
                json.dumps(entry) + "\n" for entry in audit_entries
            ]

            response = self.client.get("/api/security/audit-log")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["count"] == 2
            assert len(data["audit_entries"]) == 2

    def test_get_audit_log_with_limit(self):
        """Test audit log retrieval with limit parameter"""
        self.mock_security_layer.audit_log_file = "test_audit.log"

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.readlines.return_value = [
                '{"entry": 1}\n',
                '{"entry": 2}\n',
                '{"entry": 3}\n',
            ]

            response = self.client.get("/api/security/audit-log?limit=2")

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 2  # Limited to last 2 entries

    def test_get_audit_log_file_not_found(self):
        """Test audit log retrieval when file doesn't exist"""
        self.mock_security_layer.audit_log_file = "nonexistent.log"

        with patch("builtins.open", side_effect=FileNotFoundError()):
            response = self.client.get("/api/security/audit-log")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["count"] == 0
            assert data["audit_entries"] == []

    def test_get_audit_log_malformed_json(self):
        """Test audit log retrieval with malformed JSON entries"""
        self.mock_security_layer.audit_log_file = "test_audit.log"

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.readlines.return_value = [
                '{"valid": "entry1"}\n',
                "invalid json line\n",
                '{"valid": "entry2"}\n',
            ]

            response = self.client.get("/api/security/audit-log")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["count"] == 2  # Only valid JSON entries

    def test_get_audit_log_error(self):
        """Test audit log endpoint error handling"""
        self.mock_security_layer.audit_log_file = "test_audit.log"

        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            response = self.client.get("/api/security/audit-log")

            assert response.status_code == 500
            data = response.json()
            assert "Permission denied" in data["detail"]


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
        with patch("api.security.EnhancedSecurityLayer") as MockSecurityLayer:
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

    def test_api_error_consistency(self):
        """Test that all endpoints handle errors consistently"""
        # Remove enhanced security layer to trigger error
        if hasattr(self.app.state, "enhanced_security_layer"):
            delattr(self.app.state, "enhanced_security_layer")

        with patch(
            "api.security.EnhancedSecurityLayer",
            side_effect=Exception("Init error"),
        ):
            response = self.client.get("/api/security/status")
            assert response.status_code == 500
            assert "Init error" in response.json()["detail"]


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
