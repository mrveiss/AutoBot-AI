# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for self_capabilities router (Issue #4258)

Verifies that the self_capabilities router is properly registered and the
GET /api/capabilities endpoint is accessible and returns the expected structure.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.self_capabilities import router


@pytest.fixture
def app():
    """Create a minimal FastAPI app with the self_capabilities router."""
    app = FastAPI(title="TestApp", version="1.0.0", description="Test")
    app.include_router(router, prefix="/api", tags=["self-capabilities"])
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create a TestClient for the app."""
    return TestClient(app)


def test_self_capabilities_endpoint_exists(client: TestClient):
    """Verify that GET /api/capabilities endpoint is accessible."""
    response = client.get("/api/capabilities")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


def test_self_capabilities_returns_correct_structure(client: TestClient):
    """Verify that GET /api/capabilities returns expected response structure."""
    response = client.get("/api/capabilities")
    assert response.status_code == 200
    data = response.json()

    # Verify required keys in response
    required_keys = [
        "total_endpoints",
        "unique_paths",
        "endpoints",
        "by_tag",
        "by_operation_type",
        "api_paths",
    ]
    for key in required_keys:
        assert key in data, f"Missing required key '{key}' in response: {data.keys()}"


def test_self_capabilities_endpoints_structure(client: TestClient):
    """Verify the structure of individual endpoint entries."""
    response = client.get("/api/capabilities")
    data = response.json()

    # Verify endpoints list is present and non-empty
    assert isinstance(data["endpoints"], list)
    assert len(data["endpoints"]) > 0, "Expected at least one endpoint"

    # Verify structure of first endpoint
    endpoint = data["endpoints"][0]
    required_fields = [
        "path",
        "method",
        "operation_type",
        "summary",
        "description",
        "tags",
        "operation_id",
    ]
    for field in required_fields:
        assert field in endpoint, f"Missing required field '{field}' in endpoint entry: {endpoint.keys()}"


def test_self_capabilities_has_capabilities_endpoint(client: TestClient):
    """Verify that the /capabilities endpoint itself is included in the discovery."""
    response = client.get("/api/capabilities")
    data = response.json()

    # Find the capabilities endpoint in the list
    capabilities_endpoints = [ep for ep in data["endpoints"] if "/capabilities" in ep["path"]]
    assert len(capabilities_endpoints) > 0, "Expected /api/capabilities endpoint to be in discovery list"


def test_self_capabilities_grouping_by_tag(client: TestClient):
    """Verify that endpoints are correctly grouped by tag."""
    response = client.get("/api/capabilities")
    data = response.json()

    # Verify by_tag is a dictionary
    assert isinstance(data["by_tag"], dict)

    # Verify it contains entries
    assert len(data["by_tag"]) > 0, "Expected at least one tag group"

    # Verify each tag group contains endpoint paths
    for tag, paths in data["by_tag"].items():
        assert isinstance(paths, list), f"Expected paths for tag '{tag}' to be a list"
        assert len(paths) > 0, f"Expected at least one path for tag '{tag}'"


def test_self_capabilities_grouping_by_operation_type(client: TestClient):
    """Verify that endpoints are correctly grouped by operation type."""
    response = client.get("/api/capabilities")
    data = response.json()

    # Verify by_operation_type is a dictionary
    assert isinstance(data["by_operation_type"], dict)

    # Verify expected operation types
    valid_operations = {"query", "create", "update", "delete"}
    for op_type in data["by_operation_type"].keys():
        assert op_type in valid_operations or op_type in {
            "get",
            "post",
            "put",
            "patch",
            "delete",
        }, f"Unexpected operation type: {op_type}"


def test_self_capabilities_api_paths_list(client: TestClient):
    """Verify that api_paths contains unique paths."""
    response = client.get("/api/capabilities")
    data = response.json()

    # Verify api_paths is a list
    assert isinstance(data["api_paths"], list)

    # Verify it's not empty
    assert len(data["api_paths"]) > 0

    # Verify all entries are unique
    assert len(data["api_paths"]) == len(set(data["api_paths"])), "api_paths should not contain duplicates"

    # Verify each path starts with /
    for path in data["api_paths"]:
        assert path.startswith("/"), f"Expected path to start with '/', got: {path}"


def test_self_capabilities_total_endpoints_count(client: TestClient):
    """Verify that total_endpoints count matches endpoints list length."""
    response = client.get("/api/capabilities")
    data = response.json()

    assert isinstance(data["total_endpoints"], int)
    assert data["total_endpoints"] == len(data["endpoints"]), "total_endpoints should match endpoints list length"


def test_self_capabilities_unique_paths_count(client: TestClient):
    """Verify that unique_paths count matches api_paths list length."""
    response = client.get("/api/capabilities")
    data = response.json()

    assert isinstance(data["unique_paths"], int)
    assert data["unique_paths"] == len(data["api_paths"]), "unique_paths should match api_paths list length"


def test_self_capabilities_endpoint_registration(app: FastAPI):
    """Verify that the router was properly registered with the app."""
    # Check that the app has the capabilities route
    routes = [route for route in app.routes if "/capabilities" in route.path]
    assert len(routes) > 0, "Expected /api/capabilities route to be registered"

    # Verify the route method
    assert any(
        "GET" in str(route.methods) for route in routes if "/capabilities" in route.path
    ), "Expected GET method on /api/capabilities"
