# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test diagnostics router registration.

Issue #4254: Verify diagnostics router is properly registered and discoverable.
"""

import pytest

# Test that the diagnostics router can be imported
from api.diagnostics import get_engine, router
from initialization.router_registry.monitoring_routers import MONITORING_ROUTER_CONFIGS


class TestDiagnosticsRouterRegistration:
    """Test suite for diagnostics router registration."""

    def test_diagnostics_router_exists(self):
        """Verify diagnostics router object exists with correct configuration."""
        assert router is not None
        assert router.prefix == "/api/diagnostics"
        assert "diagnostics" in router.tags

    def test_diagnostics_router_in_registry(self):
        """Verify diagnostics router is registered in MONITORING_ROUTER_CONFIGS."""
        config_names = [config[4] for config in MONITORING_ROUTER_CONFIGS]
        assert "diagnostics" in config_names, f"Diagnostics router not found in registry. Available: {config_names}"

    def test_diagnostics_router_config_format(self):
        """Verify diagnostics router config has correct format."""
        diagnostics_config = None
        for config in MONITORING_ROUTER_CONFIGS:
            if config[4] == "diagnostics":
                diagnostics_config = config
                break

        assert diagnostics_config is not None
        module_path, router_attr, prefix, tags, name = diagnostics_config
        assert module_path == "api.diagnostics"
        assert router_attr == "router"
        assert prefix == ""  # Router already has /api/diagnostics prefix
        assert "diagnostics" in tags
        assert name == "diagnostics"

    def test_diagnostics_router_has_endpoints(self):
        """Verify diagnostics router has expected endpoints."""
        routes = [route.path for route in router.routes]
        assert "/analyze-failure" in routes
        assert "/health" in routes

    def test_diagnostics_router_endpoint_methods(self):
        """Verify diagnostics router endpoints have correct HTTP methods."""
        endpoint_methods = {}
        for route in router.routes:
            if route.path not in endpoint_methods:
                endpoint_methods[route.path] = []
            endpoint_methods[route.path].extend(route.methods or [])

        # analyze-failure should support both POST and GET
        assert "POST" in endpoint_methods.get("/analyze-failure", [])
        assert "GET" in endpoint_methods.get("/analyze-failure", [])

        # health should support GET
        assert "GET" in endpoint_methods.get("/health", [])

    @pytest.mark.asyncio
    async def test_get_engine_singleton(self):
        """Verify get_engine returns a singleton instance."""
        engine1 = get_engine()
        engine2 = get_engine()
        assert engine1 is engine2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
