# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for code version tracking (Issue #741)."""

# Import from slm-server models
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, "slm-server")
from models.database import Base, CodeStatus, Node  # noqa: E402, F401


@pytest.fixture(scope="function")
def slm_db_session():
    """Create an in-memory SQLite database for SLM models."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class TestNodeCodeVersion:
    """Test Node code version fields."""

    def test_node_has_code_version_field(self, slm_db_session):
        """Node model should have code_version field."""
        node = Node(
            node_id="test-node-1",
            hostname="test-host",
            ip_address="192.168.1.1",
            code_version="abc123def",
        )
        slm_db_session.add(node)
        slm_db_session.commit()

        saved = slm_db_session.query(Node).filter(Node.node_id == "test-node-1").first()
        assert saved is not None
        assert saved.code_version == "abc123def"

    def test_node_has_code_status_field(self, slm_db_session):
        """Node model should have code_status field."""
        node = Node(
            node_id="test-node-2",
            hostname="test-host",
            ip_address="192.168.1.2",
            code_status=CodeStatus.UNKNOWN.value,
        )
        slm_db_session.add(node)
        slm_db_session.commit()

        saved = slm_db_session.query(Node).filter(Node.node_id == "test-node-2").first()
        assert saved is not None
        assert saved.code_status == "unknown"

    def test_code_version_defaults_to_none(self, slm_db_session):
        """code_version should default to None (nullable)."""
        node = Node(
            node_id="test-node-3",
            hostname="test-host",
            ip_address="192.168.1.3",
        )
        slm_db_session.add(node)
        slm_db_session.commit()

        saved = slm_db_session.query(Node).filter(Node.node_id == "test-node-3").first()
        assert saved is not None
        assert saved.code_version is None

    def test_code_status_defaults_to_unknown(self, slm_db_session):
        """code_status should default to 'unknown'."""
        node = Node(
            node_id="test-node-4",
            hostname="test-host",
            ip_address="192.168.1.4",
        )
        slm_db_session.add(node)
        slm_db_session.commit()

        saved = slm_db_session.query(Node).filter(Node.node_id == "test-node-4").first()
        assert saved is not None
        assert saved.code_status == CodeStatus.UNKNOWN.value

    def test_code_status_enum_values(self):
        """CodeStatus enum should have required values."""
        assert CodeStatus.UP_TO_DATE.value == "up_to_date"
        assert CodeStatus.OUTDATED.value == "outdated"
        assert CodeStatus.UNKNOWN.value == "unknown"

    def test_code_status_can_be_updated(self, slm_db_session):
        """code_status should be updatable."""
        node = Node(
            node_id="test-node-5",
            hostname="test-host",
            ip_address="192.168.1.5",
            code_status=CodeStatus.UNKNOWN.value,
        )
        slm_db_session.add(node)
        slm_db_session.commit()

        # Update the status
        node.code_status = CodeStatus.UP_TO_DATE.value
        node.code_version = "abc123"
        slm_db_session.commit()

        saved = slm_db_session.query(Node).filter(Node.node_id == "test-node-5").first()
        assert saved.code_status == "up_to_date"
        assert saved.code_version == "abc123"


class TestHeartbeatSchemas:
    """Test heartbeat schema extensions (Issue #741)."""

    def test_heartbeat_request_accepts_code_version(self):
        """HeartbeatRequest should accept code_version field."""
        from models.schemas import HeartbeatRequest

        request = HeartbeatRequest(
            cpu_percent=25.0,
            memory_percent=50.0,
            disk_percent=30.0,
            code_version="abc123def456",
        )
        assert request.code_version == "abc123def456"

    def test_heartbeat_request_code_version_optional(self):
        """HeartbeatRequest code_version should be optional."""
        from models.schemas import HeartbeatRequest

        request = HeartbeatRequest(
            cpu_percent=10.0,
            memory_percent=20.0,
            disk_percent=15.0,
        )
        assert request.code_version is None

    def test_heartbeat_response_includes_update_info(self):
        """HeartbeatResponse should include update availability info."""
        from models.schemas import HeartbeatResponse

        response = HeartbeatResponse(
            status="ok",
            update_available=True,
            latest_version="def789abc",
        )
        assert response.update_available is True
        assert response.latest_version == "def789abc"

    def test_heartbeat_response_defaults(self):
        """HeartbeatResponse should have sensible defaults."""
        from models.schemas import HeartbeatResponse

        response = HeartbeatResponse()
        assert response.status == "ok"
        assert response.update_available is False
        assert response.latest_version is None
        assert response.update_url is None

    def test_heartbeat_response_with_update_url(self):
        """HeartbeatResponse should support update_url field."""
        from models.schemas import HeartbeatResponse

        response = HeartbeatResponse(
            status="ok",
            update_available=True,
            latest_version="v1.2.3",
            update_url="https://github.com/mrveiss/AutoBot-AI/releases/tag/v1.2.3",
        )
        assert (
            response.update_url
            == "https://github.com/mrveiss/AutoBot-AI/releases/tag/v1.2.3"
        )


class TestHeartbeatVersionTracking:
    """Tests for heartbeat version tracking (Issue #741)."""

    def test_version_comparison_logic_up_to_date(self):
        """Test version comparison marks node UP_TO_DATE when versions match."""
        node_version = "abc123"
        latest_version = "abc123"

        # This is the logic we expect the endpoint to implement
        if node_version == latest_version:
            code_status = CodeStatus.UP_TO_DATE.value
        elif node_version and node_version != latest_version:
            code_status = CodeStatus.OUTDATED.value
        else:
            code_status = CodeStatus.UNKNOWN.value

        assert code_status == CodeStatus.UP_TO_DATE.value

    def test_version_comparison_logic_outdated(self):
        """Test version comparison marks node OUTDATED when versions differ."""
        node_version = "abc123"
        latest_version = "def456"

        # This is the logic we expect the endpoint to implement
        if node_version == latest_version:
            code_status = CodeStatus.UP_TO_DATE.value
        elif node_version and node_version != latest_version:
            code_status = CodeStatus.OUTDATED.value
        else:
            code_status = CodeStatus.UNKNOWN.value

        assert code_status == CodeStatus.OUTDATED.value

    def test_version_comparison_logic_unknown_no_version(self):
        """Test version comparison marks node UNKNOWN when no version provided."""
        node_version = None
        latest_version = "def456"

        # This is the logic we expect the endpoint to implement
        if node_version and node_version == latest_version:
            code_status = CodeStatus.UP_TO_DATE.value
        elif node_version and node_version != latest_version:
            code_status = CodeStatus.OUTDATED.value
        else:
            code_status = CodeStatus.UNKNOWN.value

        assert code_status == CodeStatus.UNKNOWN.value

    def test_heartbeat_response_update_available_true(self):
        """Test HeartbeatResponse when update is available."""
        from models.schemas import HeartbeatResponse

        # Simulate outdated node
        code_status = CodeStatus.OUTDATED.value
        latest_version = "def456"
        node_id = "test-node"

        update_available = (
            code_status == CodeStatus.OUTDATED.value and latest_version is not None
        )

        response = HeartbeatResponse(
            status="ok",
            update_available=update_available,
            latest_version=latest_version if update_available else None,
            update_url=f"/api/nodes/{node_id}/code-package"
            if update_available
            else None,
        )

        assert response.update_available is True
        assert response.latest_version == "def456"
        assert response.update_url == f"/api/nodes/{node_id}/code-package"

    def test_heartbeat_response_update_available_false(self):
        """Test HeartbeatResponse when no update is available."""
        from models.schemas import HeartbeatResponse

        # Simulate up-to-date node
        code_status = CodeStatus.UP_TO_DATE.value
        latest_version = "abc123"

        update_available = (
            code_status == CodeStatus.OUTDATED.value and latest_version is not None
        )

        response = HeartbeatResponse(
            status="ok",
            update_available=update_available,
            latest_version=latest_version if update_available else None,
            update_url=None
            if not update_available
            else "/api/nodes/test-node/code-package",
        )

        assert response.update_available is False
        assert response.latest_version is None
        assert response.update_url is None
