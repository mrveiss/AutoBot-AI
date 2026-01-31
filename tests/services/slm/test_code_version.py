# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for code version tracking (Issue #741)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import from slm-server models
import sys
sys.path.insert(0, "slm-server")
from models.database import Base, Node, CodeStatus


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

        saved = slm_db_session.query(Node).filter(
            Node.node_id == "test-node-1"
        ).first()
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

        saved = slm_db_session.query(Node).filter(
            Node.node_id == "test-node-2"
        ).first()
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

        saved = slm_db_session.query(Node).filter(
            Node.node_id == "test-node-3"
        ).first()
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

        saved = slm_db_session.query(Node).filter(
            Node.node_id == "test-node-4"
        ).first()
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

        saved = slm_db_session.query(Node).filter(
            Node.node_id == "test-node-5"
        ).first()
        assert saved.code_status == "up_to_date"
        assert saved.code_version == "abc123"
