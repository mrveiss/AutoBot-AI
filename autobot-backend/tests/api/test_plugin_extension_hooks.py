# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Integration tests for plugin extension-point dispatch (Issue #6970)."""

import pytest
from fastapi import APIRouter, FastAPI


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset plugin and bridge singletons before+after each test."""
    from plugin_manager import reset_plugin_manager_for_tests
    from plugin_sdk.async_bridge import AsyncSyncBridge
    from plugin_sdk.base import PluginRegistry
    from plugin_sdk.hooks import HookRegistry

    reset_plugin_manager_for_tests()
    HookRegistry().clear()
    PluginRegistry().clear()
    AsyncSyncBridge.reset_for_tests()
    yield
    reset_plugin_manager_for_tests()
    HookRegistry().clear()
    PluginRegistry().clear()
    AsyncSyncBridge.reset_for_tests()


@pytest.mark.asyncio
async def test_api_router_register_dispatch_mounts_plugin_routes():
    """Stub plugin's async API_ROUTER_REGISTER handler mounts a route on a
    real FastAPI app via dispatch_extension_point."""
    from plugin_sdk.base import (
        BasePlugin,
        PluginManifest,
        PluginRegistry,
        PluginStatus,
    )
    from plugin_sdk.hooks import Hook
    from plugin_sdk.plugin_manager import PluginManager

    app = FastAPI()
    plugin_router = APIRouter()

    @plugin_router.get("/from-plugin")
    async def from_plugin():
        return {"ok": True}

    class StubPlugin(BasePlugin):
        async def initialize(self):
            self.register_extension_point(Hook.API_ROUTER_REGISTER, self._on_register)

        async def shutdown(self):
            pass

        async def _on_register(self, app):
            app.include_router(plugin_router, prefix="/api/stub")

    manifest = PluginManifest(
        name="stub-api",
        version="1.0.0",
        display_name="Stub",
        description="Stub for #6970 test.",
        author="test",
        entry_point="test.module",
    )
    plugin = StubPlugin(manifest)
    await plugin.initialize()
    plugin.status = PluginStatus.ENABLED
    PluginRegistry().register(plugin)

    pm = PluginManager(plugin_dirs=[])
    await pm.dispatch_extension_point(Hook.API_ROUTER_REGISTER, app)

    paths = [r.path for r in app.routes]
    assert "/api/stub/from-plugin" in paths
