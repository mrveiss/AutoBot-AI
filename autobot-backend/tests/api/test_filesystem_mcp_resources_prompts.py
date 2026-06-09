# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for MCP Resources and Prompts endpoints (Issue MVA-2164)

Tests the filesystem MCP bridge's resource and prompt template functionality,
ensuring proper URI handling, validation, and template rendering.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_file(tmp_path):
    """Create a test file for resource reading tests."""
    test_file = tmp_path / "test_resource.txt"
    test_file.write_text("Test resource content\nLine 2\nLine 3")
    return str(test_file)


class TestMCPResources:
    """Tests for MCP resource endpoints."""

    def test_list_resources_success(self, client: TestClient, admin_headers):
        """Test listing available MCP resources."""
        response = client.get("/api/filesystem/mcp/resources", headers=admin_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "resources" in data
        assert "total" in data
        assert isinstance(data["resources"], list)
        assert data["total"] >= 0

        # Verify resource structure if any exist
        if data["resources"]:
            resource = data["resources"][0]
            assert "uri" in resource
            assert "name" in resource
            assert resource["uri"].startswith("file://")

    def test_list_resources_requires_auth(self, client: TestClient):
        """Test that listing resources requires admin authentication."""
        response = client.get("/api/filesystem/mcp/resources")
        assert response.status_code == 401

    def test_read_resource_success(self, client: TestClient, admin_headers, test_file, monkeypatch):
        """Test reading a resource by URI."""
        # Mock is_path_allowed to accept test file
        from api import filesystem_mcp

        original_allowed = filesystem_mcp.ALLOWED_DIRECTORIES
        monkeypatch.setattr(filesystem_mcp, "ALLOWED_DIRECTORIES", [str(test_file.rsplit("/", 1)[0]) + "/"])

        uri = f"file://{test_file}"
        response = client.post(
            "/api/filesystem/mcp/resources/read",
            headers=admin_headers,
            json={"uri": uri},
        )

        # Restore original
        monkeypatch.setattr(filesystem_mcp, "ALLOWED_DIRECTORIES", original_allowed)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["uri"] == uri
        assert "Test resource content" in data["content"]
        assert data["size_bytes"] > 0
        assert "mime_type" in data

    def test_read_resource_invalid_uri_scheme(self, client: TestClient, admin_headers):
        """Test that non-file:// URIs are rejected."""
        response = client.post(
            "/api/filesystem/mcp/resources/read",
            headers=admin_headers,
            json={"uri": "http://example.com/file"},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Only file:// URIs are supported" in data["detail"]

    def test_read_resource_not_found(self, client: TestClient, admin_headers, monkeypatch):
        """Test reading a non-existent resource."""
        from api import filesystem_mcp

        original_allowed = filesystem_mcp.ALLOWED_DIRECTORIES
        monkeypatch.setattr(filesystem_mcp, "ALLOWED_DIRECTORIES", ["/tmp/"])

        response = client.post(
            "/api/filesystem/mcp/resources/read",
            headers=admin_headers,
            json={"uri": "file:///tmp/nonexistent_file.txt"},
        )

        monkeypatch.setattr(filesystem_mcp, "ALLOWED_DIRECTORIES", original_allowed)

        assert response.status_code == 404

    def test_read_resource_requires_auth(self, client: TestClient, test_file):
        """Test that reading resources requires admin authentication."""
        uri = f"file://{test_file}"
        response = client.post("/api/filesystem/mcp/resources/read", json={"uri": uri})
        assert response.status_code == 401


class TestMCPPrompts:
    """Tests for MCP prompt template endpoints."""

    def test_list_prompts_success(self, client: TestClient, admin_headers):
        """Test listing available prompt templates."""
        response = client.get("/api/filesystem/mcp/prompts", headers=admin_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "prompts" in data
        assert "total" in data
        assert isinstance(data["prompts"], list)
        assert data["total"] >= 2  # Should have at least 2 prompts

        # Verify prompt structure
        prompt = data["prompts"][0]
        assert "name" in prompt
        assert "description" in prompt
        assert "arguments" in prompt

    def test_list_prompts_requires_auth(self, client: TestClient):
        """Test that listing prompts requires admin authentication."""
        response = client.get("/api/filesystem/mcp/prompts")
        assert response.status_code == 401

    def test_get_prompt_analyze_directory(self, client: TestClient, admin_headers):
        """Test getting the analyze_directory prompt template."""
        response = client.post(
            "/api/filesystem/mcp/prompts/get",
            headers=admin_headers,
            json={
                "name": "analyze_directory",
                "arguments": {"path": "/tmp/test_dir"},
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["name"] == "analyze_directory"
        assert "messages" in data
        assert len(data["messages"]) > 0

        message = data["messages"][0]
        assert message["role"] == "user"
        assert "/tmp/test_dir" in message["content"]
        assert "analyze" in message["content"].lower()

    def test_get_prompt_summarize_file(self, client: TestClient, admin_headers):
        """Test getting the summarize_file prompt template."""
        response = client.post(
            "/api/filesystem/mcp/prompts/get",
            headers=admin_headers,
            json={
                "name": "summarize_file",
                "arguments": {"path": "/tmp/test.py", "focus": "security"},
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["name"] == "summarize_file"
        assert len(data["messages"]) > 0

        message = data["messages"][0]
        assert "/tmp/test.py" in message["content"]
        assert "security" in message["content"]

    def test_get_prompt_search_pattern(self, client: TestClient, admin_headers):
        """Test getting the search_pattern prompt template."""
        response = client.post(
            "/api/filesystem/mcp/prompts/get",
            headers=admin_headers,
            json={
                "name": "search_pattern",
                "arguments": {"directory": "/tmp/src", "pattern": "*.py"},
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["name"] == "search_pattern"
        assert len(data["messages"]) > 0

        message = data["messages"][0]
        assert "/tmp/src" in message["content"]
        assert "*.py" in message["content"]

    def test_get_prompt_missing_arguments(self, client: TestClient, admin_headers):
        """Test that missing required arguments are rejected."""
        response = client.post(
            "/api/filesystem/mcp/prompts/get",
            headers=admin_headers,
            json={"name": "analyze_directory", "arguments": {}},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Missing required argument" in data["detail"]

    def test_get_prompt_unknown_template(self, client: TestClient, admin_headers):
        """Test that unknown template names are rejected."""
        response = client.post(
            "/api/filesystem/mcp/prompts/get",
            headers=admin_headers,
            json={"name": "unknown_template", "arguments": {}},
        )
        assert response.status_code == 400
        data = response.json()
        assert "Unknown prompt template" in data["detail"]

    def test_get_prompt_requires_auth(self, client: TestClient):
        """Test that getting prompts requires admin authentication."""
        response = client.post(
            "/api/filesystem/mcp/prompts/get",
            json={
                "name": "analyze_directory",
                "arguments": {"path": "/tmp/test"},
            },
        )
        assert response.status_code == 401


class TestMCPIntegration:
    """Integration tests for MCP resources and prompts."""

    def test_resources_and_prompts_workflow(self, client: TestClient, admin_headers):
        """Test a complete workflow: list resources, list prompts, get prompt."""
        # List resources
        resources_response = client.get("/api/filesystem/mcp/resources", headers=admin_headers)
        assert resources_response.status_code == 200

        # List prompts
        prompts_response = client.get("/api/filesystem/mcp/prompts", headers=admin_headers)
        assert prompts_response.status_code == 200

        prompts_data = prompts_response.json()
        assert prompts_data["total"] >= 1

        # Get a prompt
        prompt_response = client.post(
            "/api/filesystem/mcp/prompts/get",
            headers=admin_headers,
            json={
                "name": prompts_data["prompts"][0]["name"],
                "arguments": {"path": "/tmp/test", "directory": "/tmp", "pattern": "*.txt"},
            },
        )
        # Should succeed or return 400 for missing args, but not 500
        assert prompt_response.status_code in [200, 400]
