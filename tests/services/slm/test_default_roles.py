# tests/services/slm/test_default_roles.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SLM default role initialization."""

import pytest
from backend.services.slm.db_service import SLMDatabaseService


class TestDefaultRoles:
    """Test default role initialization."""

    @pytest.fixture
    def slm_db(self, tmp_path):
        """Create SLM database service with temp database."""
        db_path = tmp_path / "test_slm.db"
        return SLMDatabaseService(db_path=str(db_path))

    def test_default_roles_created(self, slm_db):
        """Test that default roles are created on init."""
        roles = slm_db.get_all_roles()
        role_names = [r.name for r in roles]

        assert "frontend" in role_names
        assert "redis" in role_names
        assert "npu-worker" in role_names
        assert "ai-stack" in role_names
        assert "browser" in role_names

    def test_redis_role_is_stateful(self, slm_db):
        """Test Redis role is marked stateful."""
        role = slm_db.get_role_by_name("redis")
        assert role.service_type == "stateful"

    def test_frontend_role_is_stateless(self, slm_db):
        """Test Frontend role is marked stateless."""
        role = slm_db.get_role_by_name("frontend")
        assert role.service_type == "stateless"

    def test_roles_have_health_checks(self, slm_db):
        """Test roles have health check definitions."""
        redis_role = slm_db.get_role_by_name("redis")
        assert len(redis_role.health_checks) > 0
        assert redis_role.health_checks[0]["type"] == "tcp"

    def test_default_roles_not_duplicated(self, tmp_path):
        """Test that default roles are not created again on second init."""
        db_path = tmp_path / "test_slm.db"

        # First init
        db1 = SLMDatabaseService(db_path=str(db_path))
        initial_count = len(db1.get_all_roles())

        # Second init (same database)
        db2 = SLMDatabaseService(db_path=str(db_path))
        second_count = len(db2.get_all_roles())

        assert initial_count == second_count == 5
