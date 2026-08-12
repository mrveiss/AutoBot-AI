# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for Merge Conflict Resolution API

Tests REST API endpoints for intelligent merge conflict resolution.

Part of Issue #246 - Intelligent Merge Conflict Resolution
"""

import os
import tempfile
import textwrap

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.merge_conflict_resolution import router
from auth_middleware import check_admin_permission

# Mirror the real mount point so these tests exercise production URLs (#13183).
# ``api.merge_conflict_resolution`` is registered in
# initialization/router_registry/feature_routers.py under the registry prefix
# "/code-intelligence/merge-conflicts", and app_factory._register_routers mounts
# every registry router at f"/api{prefix}". The router itself is a bare
# ``APIRouter()`` with no prefix of its own, so there is nothing to double up.
API_PREFIX = "/api/code-intelligence/merge-conflicts"

# autobot_shared.security.path_validator only permits /opt/autobot and the
# system temp dir (#2848); anything else is rejected with a generic
# "Invalid or disallowed path" *before* an endpoint's existence check runs.
# Point the "missing path" cases at an allowed root so they genuinely exercise
# the does-not-exist branch they are named for.
_TMP_ROOT = tempfile.gettempdir()
MISSING_FILE = os.path.join(_TMP_ROOT, "autobot-merge-conflict-tests", "missing.py")
MISSING_REPO = os.path.join(_TMP_ROOT, "autobot-merge-conflict-tests", "missing-repo")


def payload(response):
    """Unwrap the standard DataResponse envelope.

    ``utils.response_helpers.create_success_response`` always returns
    ``{"success": ..., "data": ..., "message": ..., "timestamp": ...}``, so the
    endpoint payload lives under "data". Indexing (rather than ``.get``) keeps
    the envelope shape itself under assertion.
    """
    return response.json()["data"]


@pytest.fixture
def app():
    """Create test FastAPI app.

    An ``APIRouter`` is a bare ASGI callable with no middleware stack, so
    ``AsyncExitStackMiddleware`` never runs and ``fastapi_middleware_astack``
    never lands in the request scope. The router has to be mounted on a real
    ``FastAPI`` app for TestClient to reach an endpoint at all (#13183).
    """
    app = FastAPI()
    app.include_router(router, prefix=API_PREFIX)
    # ``Depends(check_admin_permission)`` captures the function object when the
    # endpoint module is imported, so patching the ``auth_middleware`` attribute
    # afterwards can never reach it. Override the dependency instead — the same
    # pattern api/themes_test.py uses.
    app.dependency_overrides[check_admin_permission] = lambda: True
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def conflict_file():
    """Create a temporary file with a merge conflict."""
    conflict_content = textwrap.dedent("""
        def hello():
        <<<<<<< HEAD
            return "current"
        =======
            return "incoming"
        >>>>>>> branch
    """)

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


class TestAnalyzeConflicts:
    """Test conflict analysis endpoint."""

    def test_analyze_conflicts_success(self, client, conflict_file):
        """Test successful conflict analysis."""
        response = client.post(
            f"{API_PREFIX}/analyze",
            json={"file_path": conflict_file},
        )

        assert response.status_code == 200
        data = payload(response)
        assert data["status"] == "success"
        assert data["conflict_count"] == 1
        assert "conflicts" in data
        assert len(data["conflicts"]) == 1
        assert "severity_distribution" in data

    def test_analyze_no_conflicts(self, client, clean_file):
        """Test analysis of file without conflicts."""
        response = client.post(
            f"{API_PREFIX}/analyze",
            json={"file_path": clean_file},
        )

        assert response.status_code == 200
        data = payload(response)
        assert data["status"] == "success"
        assert data["conflict_count"] == 0

    def test_analyze_nonexistent_file(self, client):
        """Test analysis of nonexistent file."""
        response = client.post(
            f"{API_PREFIX}/analyze",
            json={"file_path": MISSING_FILE},
        )

        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]

    def test_analyze_disallowed_path(self, client):
        """Test analysis of a path outside the allowed roots (#2848)."""
        response = client.post(
            f"{API_PREFIX}/analyze",
            json={"file_path": "/nonexistent/file.py"},
        )

        assert response.status_code == 400
        assert "Invalid or disallowed path" in response.json()["detail"]

    def test_analyze_unsupported_file_type(self, client):
        """Test analysis of unsupported file type."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            response = client.post(
                f"{API_PREFIX}/analyze",
                json={"file_path": f.name},
            )

            assert response.status_code == 400
            assert "Only source code files are supported" in response.json()["detail"]


class TestResolveConflicts:
    """Test conflict resolution endpoint."""

    def test_resolve_conflicts_success(self, client, conflict_file):
        """Test successful conflict resolution."""
        response = client.post(
            f"{API_PREFIX}/resolve",
            json={
                "file_path": conflict_file,
                "strategy": "semantic_merge",
                "safe_mode": True,
                "validate": True,
            },
        )

        assert response.status_code == 200
        data = payload(response)
        assert data["status"] == "success"
        assert data["resolved_count"] == 1
        assert len(data["results"]) == 1
        assert data["safe_mode"] is True
        # safe_mode forces review for every strategy except accept_both /
        # pattern_based, so this must be True here.
        assert data["summary"]["requires_review"] is True
        assert "average_confidence" in data["summary"]

    def test_resolve_no_conflicts(self, client, clean_file):
        """Test resolution of file without conflicts."""
        response = client.post(
            f"{API_PREFIX}/resolve",
            json={"file_path": clean_file},
        )

        assert response.status_code == 200
        assert payload(response)["status"] == "success"
        # The "no conflicts" wording lives on the envelope, not the payload.
        assert "No conflicts" in response.json()["message"]

    def test_resolve_invalid_strategy(self, client, conflict_file):
        """Test resolution with invalid strategy."""
        response = client.post(
            f"{API_PREFIX}/resolve",
            json={
                "file_path": conflict_file,
                "strategy": "invalid_strategy",
            },
        )

        assert response.status_code == 400
        assert "Invalid resolution strategy" in response.json()["detail"]

    def test_resolve_accept_ours(self, client, conflict_file):
        """Test accept ours resolution strategy."""
        response = client.post(
            f"{API_PREFIX}/resolve",
            json={
                "file_path": conflict_file,
                "strategy": "accept_ours",
            },
        )

        assert response.status_code == 200
        results = payload(response)["results"]
        assert len(results) == 1
        assert results[0]["strategy"] == "accept_ours"
        assert 'return "current"' in results[0]["resolved_content"]
        assert 'return "incoming"' not in results[0]["resolved_content"]

    def test_resolve_accept_theirs(self, client, conflict_file):
        """Test accept theirs resolution strategy."""
        response = client.post(
            f"{API_PREFIX}/resolve",
            json={
                "file_path": conflict_file,
                "strategy": "accept_theirs",
            },
        )

        assert response.status_code == 200
        results = payload(response)["results"]
        assert len(results) == 1
        assert results[0]["strategy"] == "accept_theirs"
        assert 'return "incoming"' in results[0]["resolved_content"]
        assert 'return "current"' not in results[0]["resolved_content"]


class TestRepositoryAnalysis:
    """Test repository analysis endpoint."""

    def test_analyze_repository_success(self, client):
        """Test successful repository analysis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file with conflicts
            with open(f"{tmpdir}/test.py", "w", encoding="utf-8") as f:
                f.write("<<<<<<< HEAD\nx = 1\n=======\nx = 2\n>>>>>>> branch\n")

            response = client.post(
                f"{API_PREFIX}/analyze-repository",
                json={"repo_path": tmpdir},
            )

            assert response.status_code == 200
            data = payload(response)
            assert data["status"] == "success"
            assert data["total_files_with_conflicts"] >= 1
            assert data["total_conflicts"] >= 1

    def test_analyze_repository_no_conflicts(self, client):
        """Test repository analysis with no conflicts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a clean file
            with open(f"{tmpdir}/test.py", "w", encoding="utf-8") as f:
                f.write("def hello():\n    pass\n")

            response = client.post(
                f"{API_PREFIX}/analyze-repository",
                json={"repo_path": tmpdir},
            )

            assert response.status_code == 200
            data = payload(response)
            assert data["total_files_with_conflicts"] == 0
            assert data["total_conflicts"] == 0

    def test_analyze_repository_nonexistent(self, client):
        """Test repository analysis with nonexistent path."""
        response = client.post(
            f"{API_PREFIX}/analyze-repository",
            json={"repo_path": MISSING_REPO},
        )

        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]

    def test_analyze_repository_not_directory(self, client):
        """Test repository analysis with file path instead of directory."""
        with tempfile.NamedTemporaryFile() as f:
            response = client.post(
                f"{API_PREFIX}/analyze-repository",
                json={"repo_path": f.name},
            )

            assert response.status_code == 400
            assert "not a directory" in response.json()["detail"]


class TestApplyResolution:
    """Test apply resolution endpoint."""

    def test_apply_resolution_success(self, client, conflict_file):
        """Test successful resolution application."""
        resolved_content = "def hello():\n    return 'resolved'\n"

        response = client.post(
            f"{API_PREFIX}/apply",
            json={
                "file_path": conflict_file,
                "resolved_content": resolved_content,
                "create_backup": True,
            },
        )

        assert response.status_code == 200
        data = payload(response)
        assert data["status"] == "success"
        assert data["backup_path"] is not None

        # Verify file was updated
        with open(conflict_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert content == resolved_content

    def test_apply_resolution_no_backup(self, client, conflict_file):
        """Test resolution application without backup."""
        resolved_content = "def hello():\n    return 'resolved'\n"

        response = client.post(
            f"{API_PREFIX}/apply",
            json={
                "file_path": conflict_file,
                "resolved_content": resolved_content,
                "create_backup": False,
            },
        )

        assert response.status_code == 200
        assert payload(response)["backup_path"] is None

    def test_apply_resolution_nonexistent_file(self, client):
        """Test application to nonexistent file."""
        response = client.post(
            f"{API_PREFIX}/apply",
            json={
                "file_path": MISSING_FILE,
                "resolved_content": "test",
            },
        )

        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]


class TestUtilityEndpoints:
    """Test utility endpoints."""

    def test_get_resolution_strategies(self, client):
        """Test getting available resolution strategies."""
        response = client.get(f"{API_PREFIX}/strategies")

        assert response.status_code == 200
        data = payload(response)
        assert data["status"] == "success"
        assert "strategies" in data
        strategies = data["strategies"]
        assert "semantic_merge" in strategies
        assert "accept_ours" in strategies
        assert "accept_theirs" in strategies
        assert "accept_both" in strategies
        assert "pattern_based" in strategies
        assert "manual_review" in strategies

    def test_check_file_conflicts_with_conflicts(self, client, conflict_file):
        """Test checking file with conflicts."""
        response = client.get(f"{API_PREFIX}/check", params={"file_path": conflict_file})

        assert response.status_code == 200
        data = payload(response)
        assert data["status"] == "success"
        assert data["has_conflicts"] is True

    def test_check_file_conflicts_without_conflicts(self, client, clean_file):
        """Test checking file without conflicts."""
        response = client.get(f"{API_PREFIX}/check", params={"file_path": clean_file})

        assert response.status_code == 200
        assert payload(response)["has_conflicts"] is False

    def test_check_nonexistent_file(self, client):
        """Test checking nonexistent file."""
        response = client.get(f"{API_PREFIX}/check", params={"file_path": MISSING_FILE})

        assert response.status_code == 400
        assert "does not exist" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
