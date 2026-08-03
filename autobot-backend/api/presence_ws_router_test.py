# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for presence_ws router registration and functionality.

Issue #4257: Verify that presence_ws router is properly registered
in the feature routers configuration.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI

from api.presence_ws import router


class TestPresenceWSRouter:
    """Test suite for presence_ws router registration."""

    def test_router_exists(self):
        """Test that the presence_ws router is defined."""
        assert router is not None
        assert hasattr(router, "routes")

    def test_router_has_websocket_endpoint(self):
        """Test that the router has the expected WebSocket endpoint."""
        # Check that the router has routes
        assert len(router.routes) > 0

        # Find the presence endpoint
        presence_routes = [r for r in router.routes if "presence" in str(r.path).lower()]
        assert len(presence_routes) > 0, "No presence endpoint found in router"

    def test_router_endpoint_path(self):
        """Test that the router endpoint has the correct path pattern."""
        # Get all route paths
        paths = [str(r.path) for r in router.routes]

        # Check for the presence endpoint
        expected_path = "/ws/sessions/{session_id}/presence"
        assert expected_path in paths, f"Expected path {expected_path} not found"

    def test_router_tags(self):
        """Test that the router has the correct OpenAPI tags."""
        # The router should have tags defined
        tags = router.tags if hasattr(router, "tags") else []
        assert (
            "collaboration" in tags or "websocket" in tags or "presence" in tags
        ), f"Expected tags not found. Got: {tags}"

    def test_router_can_be_mounted(self):
        """Test that the router can be mounted on a FastAPI app."""
        app = FastAPI()

        # This should not raise an exception
        try:
            app.include_router(router)
        except Exception as e:
            pytest.fail(f"Failed to mount router: {e}")

        # Verify the router was mounted
        assert len(app.routes) > 0


class TestPresenceWSConfiguration:
    """Test presence_ws router configuration."""

    def test_router_registered_in_feature_routers_config(self):
        """Test that presence_ws is properly registered in FEATURE_ROUTER_CONFIGS."""
        # Resolve the config relative to THIS file so the guard runs anywhere
        # (CI checkout, worktree, container) — #13409.
        # autobot_shared.ssot_config.PROJECT_ROOT is deliberately NOT used: it
        # walks up looking for a .env, which a git worktree has none of, so it
        # silently resolves to the main checkout instead (#13357).
        backend_root = Path(__file__).resolve().parents[1]
        config_file = backend_root / "initialization" / "router_registry" / "feature_routers.py"

        assert config_file.is_file(), f"feature_routers.py not found at {config_file}"
        content = config_file.read_text(encoding="utf-8")

        # Verify presence_ws is in the file
        assert "api.presence_ws" in content, "api.presence_ws not found in config"
        assert '"presence_ws"' in content, "presence_ws name not found in config"
        assert '"collaboration"' in content, "collaboration tag not found"
        assert '"websocket"' in content, "websocket tag not found"
        assert '"presence"' in content, "presence tag not found"

    def test_router_can_be_imported_by_loader(self):
        """Test that the router can be imported as expected by the loader."""
        import importlib

        # Test the import path directly
        module_path = "api.presence_ws"

        try:
            module = importlib.import_module(module_path)
            router_obj = getattr(module, "router")
            assert router_obj is not None, "Failed to get router from module"
        except ImportError as e:
            pytest.fail(f"Failed to import {module_path}: {e}")
        except AttributeError as e:
            pytest.fail(f"Router attribute not found in {module_path}: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
