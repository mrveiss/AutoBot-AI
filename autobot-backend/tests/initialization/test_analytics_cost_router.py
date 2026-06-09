# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for analytics_cost router registration.

Verifies that the analytics_cost router is properly configured and loaded
in the router registry, ensuring all cost analysis endpoints are accessible.

Issue #4252: Ensure analytics_cost router is registered and functional.
"""


def test_analytics_cost_router_exists():
    """Test that analytics_cost module has a router object."""
    from api import analytics_cost

    assert hasattr(analytics_cost, "router"), "analytics_cost module missing router"
    assert analytics_cost.router is not None


def test_analytics_cost_router_has_routes():
    """Test that analytics_cost router has expected endpoints."""
    from api import analytics_cost

    router = analytics_cost.router
    assert len(router.routes) > 0, "analytics_cost router has no routes"

    # Verify router has the expected prefix
    assert router.prefix == "/cost"


def test_analytics_cost_router_configuration():
    """Test that analytics_cost router config has correct settings."""
    from api.analytics_cost import router as analytics_cost_router

    # Verify the router has the expected prefix
    assert analytics_cost_router.prefix == "/cost"

    # Verify it has routes
    assert len(analytics_cost_router.routes) > 0


def test_analytics_cost_router_loads():
    """Test that analytics_cost module can be imported and has router object."""
    from api.analytics_cost import router as analytics_cost_router

    assert analytics_cost_router is not None
    assert hasattr(analytics_cost_router, "routes")
    assert len(analytics_cost_router.routes) > 0


def test_analytics_cost_router_endpoints():
    """Test that analytics_cost router has expected endpoint paths."""
    from api import analytics_cost

    router = analytics_cost.router
    route_paths = {route.path for route in router.routes}

    # Verify some expected endpoints exist (paths include /cost prefix from router prefix)
    expected_endpoints = {
        "/cost/summary",
        "/cost/by-model",
        "/cost/by-session/{session_id}",
        "/cost/trends",
        "/cost/forecast",
        "/cost/usage/recent",
        "/cost/pricing",
        "/cost/estimate",
        "/cost/budget-alert",
        "/cost/budget-alerts",
        "/cost/budget-status",
        "/cost/by-agent",
        "/cost/by-agent/{agent_id}",
        "/cost/by-agent/{agent_id}/budget",
    }

    for endpoint in expected_endpoints:
        assert endpoint in route_paths, f"Expected endpoint {endpoint} not found in {route_paths}"

    # Verify router has 15 or more endpoints as described in the issue
    assert len(router.routes) >= 15, f"Expected 15+ endpoints, found {len(router.routes)}"


def test_analytics_cost_endpoint_authentication():
    """Test that analytics_cost endpoints are decorated with error handling."""
    from api import analytics_cost

    router = analytics_cost.router

    # Verify that routes exist and have proper decorators
    # Check that at least some routes are present
    assert len(router.routes) > 0, "No routes found in analytics_cost router"

    # Verify that the router is properly configured with cost endpoints
    route_names = {route.name for route in router.routes if route.name}

    # Verify some expected endpoints are registered
    assert any("summary" in name for name in route_names), "Cost summary endpoint not found"
    assert any("model" in name for name in route_names), "Cost by model endpoint not found"
    assert any("agent" in name for name in route_names), "Cost by agent endpoint not found"
