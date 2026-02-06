# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Security Assessment Workflow Manager

Tests the security assessment workflow functionality including:
- Assessment creation and lifecycle
- Phase transitions
- Host/port/vulnerability tracking
- Tool output parsing
- Memory MCP integration

Issue: #260
"""

from unittest.mock import AsyncMock

import pytest

from src.services.security_workflow_manager import (
    PHASE_DESCRIPTIONS,
    VALID_TRANSITIONS,
    AssessmentPhase,
    SecurityAssessment,
    SecurityWorkflowManager,
    TargetHost,
)


class TestAssessmentPhase:
    """Test AssessmentPhase enum."""

    def test_all_phases_defined(self):
        """Verify all expected phases are defined."""
        expected_phases = [
            "INIT",
            "RECON",
            "PORT_SCAN",
            "ENUMERATION",
            "VULN_ANALYSIS",
            "EXPLOITATION",
            "REPORTING",
            "COMPLETE",
            "ERROR",
        ]
        actual_phases = [p.value for p in AssessmentPhase]
        assert set(expected_phases) == set(actual_phases)

    def test_phase_string_value(self):
        """Test phase enum string values."""
        assert AssessmentPhase.INIT.value == "INIT"
        assert AssessmentPhase.RECON.value == "RECON"
        assert AssessmentPhase.ERROR.value == "ERROR"


class TestValidTransitions:
    """Test phase transition validation."""

    def test_init_transitions(self):
        """INIT can transition to RECON or ERROR."""
        assert "RECON" in VALID_TRANSITIONS["INIT"]
        assert "ERROR" in VALID_TRANSITIONS["INIT"]

    def test_complete_no_transitions(self):
        """COMPLETE is terminal - no valid transitions."""
        assert VALID_TRANSITIONS["COMPLETE"] == []

    def test_error_recovery_transitions(self):
        """ERROR can transition to most phases for recovery."""
        error_transitions = VALID_TRANSITIONS["ERROR"]
        assert "INIT" in error_transitions
        assert "RECON" in error_transitions
        assert "PORT_SCAN" in error_transitions

    def test_exploitation_requires_training(self):
        """VULN_ANALYSIS can transition to EXPLOITATION."""
        vuln_transitions = VALID_TRANSITIONS["VULN_ANALYSIS"]
        assert "EXPLOITATION" in vuln_transitions
        assert "REPORTING" in vuln_transitions


class TestTargetHost:
    """Test TargetHost dataclass."""

    def test_create_host(self):
        """Test basic host creation."""
        host = TargetHost(ip="192.168.1.1")
        assert host.ip == "192.168.1.1"
        assert host.hostname is None
        assert host.status == "unknown"
        assert host.ports == []
        assert host.services == []
        assert host.vulnerabilities == []

    def test_host_with_details(self):
        """Test host with all details."""
        host = TargetHost(
            ip="192.168.1.1",
            hostname="server.local",
            status="up",
            ports=[{"port": 22, "protocol": "tcp"}],
            services=[{"name": "ssh", "port": 22}],
            metadata={"os": "Linux"},
        )
        assert host.hostname == "server.local"
        assert host.status == "up"
        assert len(host.ports) == 1
        assert len(host.services) == 1

    def test_host_to_dict(self):
        """Test host serialization."""
        host = TargetHost(ip="192.168.1.1", hostname="test")
        data = host.to_dict()
        assert data["ip"] == "192.168.1.1"
        assert data["hostname"] == "test"
        assert isinstance(data["ports"], list)

    def test_host_from_dict(self):
        """Test host deserialization."""
        data = {
            "ip": "192.168.1.1",
            "hostname": "test",
            "status": "up",
            "ports": [],
            "services": [],
            "vulnerabilities": [],
            "metadata": {},
        }
        host = TargetHost.from_dict(data)
        assert host.ip == "192.168.1.1"
        assert host.status == "up"


class TestSecurityAssessment:
    """Test SecurityAssessment dataclass."""

    def test_create_assessment(self):
        """Test basic assessment creation."""
        assessment = SecurityAssessment(
            id="test-123",
            name="Test Assessment",
            target="192.168.1.0/24",
            scope=["192.168.1.0/24"],
            phase=AssessmentPhase.INIT,
        )
        assert assessment.id == "test-123"
        assert assessment.name == "Test Assessment"
        assert assessment.target == "192.168.1.0/24"
        assert assessment.phase == AssessmentPhase.INIT
        assert assessment.training_mode is False

    def test_assessment_timestamps(self):
        """Test automatic timestamp generation."""
        assessment = SecurityAssessment(
            id="test-123",
            name="Test",
            target="192.168.1.1",
            scope=["192.168.1.1"],
            phase=AssessmentPhase.INIT,
        )
        assert assessment.created_at != ""
        assert assessment.updated_at != ""

    def test_assessment_to_dict(self):
        """Test assessment serialization."""
        assessment = SecurityAssessment(
            id="test-123",
            name="Test",
            target="192.168.1.1",
            scope=["192.168.1.1"],
            phase=AssessmentPhase.RECON,
            training_mode=True,
        )
        data = assessment.to_dict()
        assert data["id"] == "test-123"
        assert data["phase"] == "RECON"
        assert data["training_mode"] is True

    def test_assessment_from_dict(self):
        """Test assessment deserialization."""
        data = {
            "id": "test-123",
            "name": "Test",
            "target": "192.168.1.1",
            "scope": ["192.168.1.1"],
            "phase": "PORT_SCAN",
            "training_mode": False,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "phase_history": [],
            "hosts": [],
            "findings": [],
            "actions_taken": [],
            "error_message": None,
            "metadata": {},
        }
        assessment = SecurityAssessment.from_dict(data)
        assert assessment.phase == AssessmentPhase.PORT_SCAN
        assert assessment.target == "192.168.1.1"


class TestSecurityWorkflowManager:
    """Test SecurityWorkflowManager class."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock()
        mock.sadd = AsyncMock()
        mock.srem = AsyncMock()
        mock.smembers = AsyncMock(return_value=set())
        mock.delete = AsyncMock(return_value=1)
        return mock

    @pytest.fixture
    def manager(self, mock_redis):
        """Create manager with mocked Redis."""
        mgr = SecurityWorkflowManager()
        mgr._redis_client = mock_redis
        return mgr

    @pytest.mark.asyncio
    async def test_create_assessment(self, manager):
        """Test assessment creation."""
        assessment = await manager.create_assessment(
            name="Test Scan",
            target="192.168.1.0/24",
            scope=["192.168.1.0/24"],
            training_mode=False,
        )

        assert assessment is not None
        assert assessment.name == "Test Scan"
        assert assessment.target == "192.168.1.0/24"
        assert assessment.phase == AssessmentPhase.INIT
        assert len(assessment.id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_create_training_assessment(self, manager):
        """Test assessment with training mode enabled."""
        assessment = await manager.create_assessment(
            name="Training Scan", target="10.0.0.1", training_mode=True
        )

        assert assessment.training_mode is True

    @pytest.mark.asyncio
    async def test_advance_phase(self, manager, mock_redis):
        """Test advancing through phases."""
        # Create assessment
        assessment = await manager.create_assessment(name="Test", target="192.168.1.1")

        # Mock get_assessment to return our assessment
        import json

        mock_redis.get = AsyncMock(return_value=json.dumps(assessment.to_dict()))

        # Advance to RECON
        updated = await manager.advance_phase(
            assessment.id, reason="Starting reconnaissance"
        )

        assert updated is not None
        assert updated.phase == AssessmentPhase.RECON

    @pytest.mark.asyncio
    async def test_add_host(self, manager, mock_redis):
        """Test adding a host to assessment."""
        assessment = await manager.create_assessment(
            name="Test", target="192.168.1.0/24"
        )

        import json

        mock_redis.get = AsyncMock(return_value=json.dumps(assessment.to_dict()))

        updated = await manager.add_host(
            assessment.id, ip="192.168.1.10", hostname="web-server", status="up"
        )

        assert updated is not None
        assert len(updated.hosts) == 1
        assert updated.hosts[0].ip == "192.168.1.10"
        assert updated.hosts[0].hostname == "web-server"

    @pytest.mark.asyncio
    async def test_add_port(self, manager, mock_redis):
        """Test adding a port to a host."""
        assessment = await manager.create_assessment(name="Test", target="192.168.1.1")

        import json

        mock_redis.get = AsyncMock(return_value=json.dumps(assessment.to_dict()))

        updated = await manager.add_port(
            assessment.id,
            host_ip="192.168.1.1",
            port=22,
            protocol="tcp",
            state="open",
            service="ssh",
            version="OpenSSH 8.0",
        )

        assert updated is not None
        assert len(updated.hosts) == 1
        assert len(updated.hosts[0].ports) == 1
        assert updated.hosts[0].ports[0]["port"] == 22

    @pytest.mark.asyncio
    async def test_add_vulnerability(self, manager, mock_redis):
        """Test adding a vulnerability."""
        assessment = await manager.create_assessment(name="Test", target="192.168.1.1")

        import json

        mock_redis.get = AsyncMock(return_value=json.dumps(assessment.to_dict()))

        updated = await manager.add_vulnerability(
            assessment.id,
            host_ip="192.168.1.1",
            cve_id="CVE-2024-1234",
            title="Test Vulnerability",
            severity="high",
            description="A test vulnerability",
        )

        assert updated is not None
        assert len(updated.hosts) == 1
        assert len(updated.hosts[0].vulnerabilities) == 1
        assert updated.hosts[0].vulnerabilities[0]["cve_id"] == "CVE-2024-1234"

    @pytest.mark.asyncio
    async def test_exploitation_requires_training(self, manager, mock_redis):
        """Test that exploitation phase requires training mode."""
        # Create non-training assessment
        assessment = await manager.create_assessment(
            name="Safe Scan", target="192.168.1.1", training_mode=False
        )

        # Simulate being in VULN_ANALYSIS phase
        assessment.phase = AssessmentPhase.VULN_ANALYSIS

        import json

        mock_redis.get = AsyncMock(return_value=json.dumps(assessment.to_dict()))

        # Try to advance to EXPLOITATION - should skip to REPORTING
        updated = await manager.advance_phase(
            assessment.id, target_phase="EXPLOITATION"
        )

        # Should skip exploitation and go to REPORTING
        assert updated.phase == AssessmentPhase.REPORTING

    @pytest.mark.asyncio
    async def test_training_mode_allows_exploitation(self, manager, mock_redis):
        """Test that training mode enables exploitation."""
        assessment = await manager.create_assessment(
            name="Training Scan", target="192.168.1.1", training_mode=True
        )

        assessment.phase = AssessmentPhase.VULN_ANALYSIS

        import json

        mock_redis.get = AsyncMock(return_value=json.dumps(assessment.to_dict()))

        updated = await manager.advance_phase(
            assessment.id, target_phase="EXPLOITATION"
        )

        assert updated.phase == AssessmentPhase.EXPLOITATION

    @pytest.mark.asyncio
    async def test_get_assessment_summary(self, manager, mock_redis):
        """Test getting assessment summary."""
        assessment = await manager.create_assessment(name="Test", target="192.168.1.1")

        # Add some data - note: vulnerabilities are counted from findings
        assessment.hosts = [
            TargetHost(
                ip="192.168.1.1",
                status="up",
                ports=[{"port": 22, "protocol": "tcp"}],
                services=[{"name": "ssh", "port": 22}],
                vulnerabilities=[{"severity": "high", "cve_id": "CVE-2024-1234"}],
            )
        ]
        # Add finding for the vulnerability (this is how they're counted)
        assessment.findings = [{"type": "vulnerability", "host": "192.168.1.1"}]

        import json

        mock_redis.get = AsyncMock(return_value=json.dumps(assessment.to_dict()))

        summary = await manager.get_assessment_summary(assessment.id)

        assert summary is not None
        assert summary["stats"]["hosts"] == 1
        assert summary["stats"]["ports"] == 1
        assert summary["stats"]["services"] == 1
        assert summary["stats"]["vulnerabilities"] == 1


class TestPhaseDescriptions:
    """Test phase descriptions configuration."""

    def test_all_phases_have_descriptions(self):
        """All phases should have descriptions."""
        for phase in AssessmentPhase:
            assert phase.value in PHASE_DESCRIPTIONS

    def test_phase_description_structure(self):
        """Phase descriptions should have required fields."""
        for phase, info in PHASE_DESCRIPTIONS.items():
            assert "description" in info
            assert "actions" in info
            assert isinstance(info["actions"], list)

    def test_exploitation_requires_training(self):
        """EXPLOITATION phase should require training mode."""
        exploit_info = PHASE_DESCRIPTIONS.get("EXPLOITATION", {})
        assert exploit_info.get("requires_training_mode") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
