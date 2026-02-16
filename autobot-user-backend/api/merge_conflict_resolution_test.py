# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Merge Conflict Resolution API

Tests REST API endpoints for intelligent merge conflict resolution.

Part of Issue #246 - Intelligent Merge Conflict Resolution
"""

import tempfile
import textwrap
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Mock the auth middleware before importing the router
with patch("auth_middleware.check_admin_permission", return_value=True):
    from api.merge_conflict_resolution import router

client = TestClient(router)


@pytest.fixture
def conflict_file():
    """Create a temporary file with a merge conflict."""
    conflict_content = textwrap.dedent(
        """
        def hello():
        <<<<<<< HEAD
            return "current"
        =======
            return "incoming"
        >>>>>>> branch
    """
    )

    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write(conflict_content)
        f.flush()
        yield f.name


@pytest.fixture
def clean_file():
    """Create a temporary file without conflicts."""
    clean_content = "def hello():\n    return 'world'\n"

    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write(clean_content)
        f.flush()
        yield f.name


@pytest.fixture
def mock_admin():
    """Mock admin permission check."""
    with patch("auth_middleware.check_admin_permission", return_value=True):
        yield


class TestAnalyzeConflicts:
    """Test conflict analysis endpoint."""

    def test_analyze_conflicts_success(self, conflict_file, mock_admin):
        """Test successful conflict analysis."""
        response = client.post(
            "/analyze",
            json={"file_path": conflict_file},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["conflict_count"] == 1
        assert "conflicts" in data
        assert len(data["conflicts"]) == 1
        assert "severity_distribution" in data

    def test_analyze_no_conflicts(self, clean_file, mock_admin):
        """Test analysis of file without conflicts."""
        response = client.post(
            "/analyze",
            json={"file_path": clean_file},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["conflict_count"] == 0

    def test_analyze_nonexistent_file(self, mock_admin):
        """Test analysis of nonexistent file."""
        response = client.post(
            "/analyze",
            json={"file_path": "/nonexistent/file.py"},
        )

        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]

    def test_analyze_unsupported_file_type(self, mock_admin):
        """Test analysis of unsupported file type."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            response = client.post(
                "/analyze",
                json={"file_path": f.name},
            )

            assert response.status_code == 400
            assert "not supported" in response.json()["detail"]


class TestResolveConflicts:
    """Test conflict resolution endpoint."""

    def test_resolve_conflicts_success(self, conflict_file, mock_admin):
        """Test successful conflict resolution."""
        response = client.post(
            "/resolve",
            json={
                "file_path": conflict_file,
                "strategy": "semantic_merge",
                "safe_mode": True,
                "validate": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["resolution_count"] == 1
        assert "resolutions" in data
        assert "summary" in data

    def test_resolve_no_conflicts(self, clean_file, mock_admin):
        """Test resolution of file without conflicts."""
        response = client.post(
            "/resolve",
            json={"file_path": clean_file},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "No conflicts" in data["message"]

    def test_resolve_invalid_strategy(self, conflict_file, mock_admin):
        """Test resolution with invalid strategy."""
        response = client.post(
            "/resolve",
            json={
                "file_path": conflict_file,
                "strategy": "invalid_strategy",
            },
        )

        assert response.status_code == 400
        assert "Invalid resolution strategy" in response.json()["detail"]

    def test_resolve_accept_ours(self, conflict_file, mock_admin):
        """Test accept ours resolution strategy."""
        response = client.post(
            "/resolve",
            json={
                "file_path": conflict_file,
                "strategy": "accept_ours",
            },
        )

        assert response.status_code == 200
        data = response.json()
        resolutions = data["resolutions"]
        assert len(resolutions) == 1
        assert resolutions[0]["strategy"] == "accept_ours"

    def test_resolve_accept_theirs(self, conflict_file, mock_admin):
        """Test accept theirs resolution strategy."""
        response = client.post(
            "/resolve",
            json={
                "file_path": conflict_file,
                "strategy": "accept_theirs",
            },
        )

        assert response.status_code == 200
        data = response.json()
        resolutions = data["resolutions"]
        assert resolutions[0]["strategy"] == "accept_theirs"


class TestRepositoryAnalysis:
    """Test repository analysis endpoint."""

    def test_analyze_repository_success(self, mock_admin):
        """Test successful repository analysis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file with conflicts
            with open(f"{tmpdir}/test.py", "w") as f:
                f.write("<<<<<<< HEAD\nx = 1\n=======\nx = 2\n>>>>>>> branch\n")

            response = client.post(
                "/analyze-repository",
                json={"repo_path": tmpdir},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["total_files_with_conflicts"] >= 1
            assert data["total_conflicts"] >= 1

    def test_analyze_repository_no_conflicts(self, mock_admin):
        """Test repository analysis with no conflicts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a clean file
            with open(f"{tmpdir}/test.py", "w") as f:
                f.write("def hello():\n    pass\n")

            response = client.post(
                "/analyze-repository",
                json={"repo_path": tmpdir},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["total_files_with_conflicts"] == 0

    def test_analyze_repository_nonexistent(self, mock_admin):
        """Test repository analysis with nonexistent path."""
        response = client.post(
            "/analyze-repository",
            json={"repo_path": "/nonexistent/path"},
        )

        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]

    def test_analyze_repository_not_directory(self, mock_admin):
        """Test repository analysis with file path instead of directory."""
        with tempfile.NamedTemporaryFile() as f:
            response = client.post(
                "/analyze-repository",
                json={"repo_path": f.name},
            )

            assert response.status_code == 400
            assert "not a directory" in response.json()["detail"]


class TestApplyResolution:
    """Test apply resolution endpoint."""

    def test_apply_resolution_success(self, conflict_file, mock_admin):
        """Test successful resolution application."""
        resolved_content = "def hello():\n    return 'resolved'\n"

        response = client.post(
            "/apply",
            json={
                "file_path": conflict_file,
                "resolved_content": resolved_content,
                "create_backup": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["backup_path"] is not None

        # Verify file was updated
        with open(conflict_file, "r") as f:
            content = f.read()
            assert content == resolved_content

    def test_apply_resolution_no_backup(self, conflict_file, mock_admin):
        """Test resolution application without backup."""
        resolved_content = "def hello():\n    return 'resolved'\n"

        response = client.post(
            "/apply",
            json={
                "file_path": conflict_file,
                "resolved_content": resolved_content,
                "create_backup": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["backup_path"] is None

    def test_apply_resolution_nonexistent_file(self, mock_admin):
        """Test application to nonexistent file."""
        response = client.post(
            "/apply",
            json={
                "file_path": "/nonexistent/file.py",
                "resolved_content": "test",
            },
        )

        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]


class TestUtilityEndpoints:
    """Test utility endpoints."""

    def test_get_resolution_strategies(self, mock_admin):
        """Test getting available resolution strategies."""
        response = client.get("/strategies")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "strategies" in data
        strategies = data["strategies"]
        assert "semantic_merge" in strategies
        assert "accept_ours" in strategies
        assert "accept_theirs" in strategies
        assert "accept_both" in strategies
        assert "pattern_based" in strategies
        assert "manual_review" in strategies

    def test_check_file_conflicts_with_conflicts(self, conflict_file, mock_admin):
        """Test checking file with conflicts."""
        response = client.get(f"/check?file_path={conflict_file}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["has_conflicts"] is True

    def test_check_file_conflicts_without_conflicts(self, clean_file, mock_admin):
        """Test checking file without conflicts."""
        response = client.get(f"/check?file_path={clean_file}")

        assert response.status_code == 200
        data = response.json()
        assert data["has_conflicts"] is False

    def test_check_nonexistent_file(self, mock_admin):
        """Test checking nonexistent file."""
        response = client.get("/check?file_path=/nonexistent/file.py")

        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
