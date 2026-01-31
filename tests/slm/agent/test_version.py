# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Agent Version Module (Issue #741).
"""

import json
import sys
from pathlib import Path

import pytest

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class TestAgentVersion:
    """Tests for AgentVersion class."""

    @pytest.fixture
    def temp_version_file(self, tmp_path):
        """Create a temporary version file."""
        version_file = tmp_path / "version.json"
        version_data = {
            "commit": "abc123def456",
            "built_at": "2026-01-31T12:00:00",
        }
        version_file.write_text(json.dumps(version_data))
        return version_file

    def test_initialization(self, tmp_path):
        """Test AgentVersion can be initialized."""
        from src.slm.agent.version import AgentVersion

        version_file = tmp_path / "version.json"
        agent_version = AgentVersion(version_file=version_file)

        assert agent_version.version_file == version_file

    def test_get_version_returns_commit(self, temp_version_file):
        """Test get_version returns commit hash."""
        from src.slm.agent.version import AgentVersion

        agent_version = AgentVersion(version_file=temp_version_file)
        version = agent_version.get_version()

        assert version == "abc123def456"

    def test_get_version_info_returns_full_data(self, temp_version_file):
        """Test get_version_info returns full version data."""
        from src.slm.agent.version import AgentVersion

        agent_version = AgentVersion(version_file=temp_version_file)
        info = agent_version.get_version_info()

        assert info["commit"] == "abc123def456"
        assert "built_at" in info

    def test_get_version_missing_file(self, tmp_path):
        """Test get_version with missing file returns None."""
        from src.slm.agent.version import AgentVersion

        agent_version = AgentVersion(version_file=tmp_path / "nonexistent.json")
        version = agent_version.get_version()

        assert version is None

    def test_save_version(self, tmp_path):
        """Test save_version creates file."""
        from src.slm.agent.version import AgentVersion

        version_file = tmp_path / "version.json"
        agent_version = AgentVersion(version_file=version_file)

        result = agent_version.save_version("new123commit")

        assert result is True
        assert version_file.exists()

        data = json.loads(version_file.read_text())
        assert data["commit"] == "new123commit"

    def test_save_version_with_extra_data(self, tmp_path):
        """Test save_version with extra metadata."""
        from src.slm.agent.version import AgentVersion

        version_file = tmp_path / "version.json"
        agent_version = AgentVersion(version_file=version_file)

        result = agent_version.save_version(
            "xyz789",
            extra_data={"source": "sync", "node_id": "node-001"},
        )

        assert result is True
        data = json.loads(version_file.read_text())
        assert data["source"] == "sync"
        assert data["node_id"] == "node-001"

    def test_is_outdated_true(self, temp_version_file):
        """Test is_outdated returns True when versions differ."""
        from src.slm.agent.version import AgentVersion

        agent_version = AgentVersion(version_file=temp_version_file)

        is_outdated = agent_version.is_outdated("different123")

        assert is_outdated is True

    def test_is_outdated_false(self, temp_version_file):
        """Test is_outdated returns False when versions match."""
        from src.slm.agent.version import AgentVersion

        agent_version = AgentVersion(version_file=temp_version_file)

        is_outdated = agent_version.is_outdated("abc123def456")

        assert is_outdated is False

    def test_clear_cache(self, temp_version_file):
        """Test clear_cache forces re-read."""
        from src.slm.agent.version import AgentVersion

        agent_version = AgentVersion(version_file=temp_version_file)

        # Load and cache
        agent_version.get_version()
        assert agent_version._cached_version is not None

        # Clear cache
        agent_version.clear_cache()
        assert agent_version._cached_version is None


class TestGetAgentVersion:
    """Tests for get_agent_version function."""

    def test_returns_singleton(self, tmp_path):
        """Test get_agent_version returns same instance."""
        from src.slm.agent.version import get_agent_version, reset_version_instance

        reset_version_instance()

        v1 = get_agent_version(version_file=tmp_path / "v.json")
        v2 = get_agent_version(version_file=tmp_path / "v.json")

        assert v1 is v2

        reset_version_instance()
