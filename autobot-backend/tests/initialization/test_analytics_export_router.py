# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for analytics_export router registration.

Verifies that the analytics_export router is properly configured and loaded
in the router registry, ensuring all export endpoints are accessible.

Issue #4253: Ensure analytics_export router is registered and functional.
"""


def test_analytics_export_router_exists():
    """Test that analytics_export module has a router object."""
    from api import analytics_export

    assert hasattr(analytics_export, "router"), "analytics_export module missing router"
    assert analytics_export.router is not None


def test_analytics_export_router_has_routes():
    """Test that analytics_export router has expected endpoints."""
    from api import analytics_export

    router = analytics_export.router
    assert len(router.routes) > 0, "analytics_export router has no routes"

    # Verify router has the expected prefix
    assert router.prefix == "/export"


def test_analytics_export_router_configuration():
    """Test that analytics_export router config has correct settings."""
    from api.analytics_export import router as analytics_export_router

    # Verify the router has the expected prefix
    assert analytics_export_router.prefix == "/export"

    # Verify it has routes
    assert len(analytics_export_router.routes) > 0


def test_analytics_export_router_loads():
    """Test that analytics_export module can be imported and has router object."""
    from api.analytics_export import router as analytics_export_router

    assert analytics_export_router is not None
    assert hasattr(analytics_export_router, "routes")
    assert len(analytics_export_router.routes) > 0


def test_analytics_export_router_endpoints():
    """Test that analytics_export router has expected endpoint paths."""
    from api import analytics_export

    router = analytics_export.router
    route_paths = {route.path for route in router.routes}

    # Verify some expected endpoints exist (paths include /export prefix from router prefix)
    expected_endpoints = {
        "/export/csv/costs",
        "/export/csv/agents",
        "/export/csv/usage",
        "/export/json/full",
        "/export/prometheus",
        "/export/grafana-dashboard",
        "/export/formats",
    }

    for endpoint in expected_endpoints:
        assert endpoint in route_paths, f"Expected endpoint {endpoint} not found in {route_paths}"

    # Verify router has 7 or more endpoints as described in the module
    assert len(router.routes) >= 7, f"Expected 7+ endpoints, found {len(router.routes)}"


def test_analytics_export_endpoint_tags():
    """Test that analytics_export endpoints are tagged correctly."""
    from api import analytics_export

    router = analytics_export.router
    tags = router.tags

    # Verify that the router has the expected tags
    assert "analytics" in tags, "Missing 'analytics' tag"
    assert "export" in tags, "Missing 'export' tag"
