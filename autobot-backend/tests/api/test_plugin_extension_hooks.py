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


@pytest.mark.asyncio
async def test_api_router_register_failure_isolation():
    """One plugin's handler raises; other plugins still mount their routes.
    Failed plugin's status is set to ERROR; others remain ENABLED."""
    from plugin_sdk.base import (
        BasePlugin,
        PluginManifest,
        PluginRegistry,
        PluginStatus,
    )
    from plugin_sdk.hooks import Hook, HookRegistry
    from plugin_sdk.plugin_manager import PluginManager

    HookRegistry().clear()
    PluginRegistry().clear()

    app = FastAPI()

    ok_router = APIRouter()

    @ok_router.get("/from-ok-plugin")
    async def from_ok():
        return {"ok": True}

    class FailingPlugin(BasePlugin):
        async def initialize(self):
            self.register_extension_point(Hook.API_ROUTER_REGISTER, self._fail)

        async def shutdown(self):
            pass

        async def _fail(self, app):
            raise RuntimeError("intentional failure during route registration")

    class OkPlugin(BasePlugin):
        async def initialize(self):
            self.register_extension_point(Hook.API_ROUTER_REGISTER, self._mount)

        async def shutdown(self):
            pass

        async def _mount(self, app):
            app.include_router(ok_router, prefix="/api/ok")

    def _mk(cls, name):
        m = PluginManifest(
            name=name,
            version="1.0.0",
            display_name=name,
            description="Stub.",
            author="test",
            entry_point="test.module",
        )
        return cls(m)

    p_fail = _mk(FailingPlugin, "plugin-fail")
    p_ok = _mk(OkPlugin, "plugin-ok")

    # Order matters — failing plugin's initialize() must register FIRST so it
    # dispatches first. Otherwise the test doesn't prove the loop continues
    # after a raise.
    await p_fail.initialize()
    p_fail.status = PluginStatus.ENABLED
    PluginRegistry().register(p_fail)

    await p_ok.initialize()
    p_ok.status = PluginStatus.ENABLED
    PluginRegistry().register(p_ok)

    pm = PluginManager(plugin_dirs=[])
    await pm.dispatch_extension_point(Hook.API_ROUTER_REGISTER, app)

    # OK plugin's route is mounted despite the first plugin raising
    paths = [r.path for r in app.routes]
    assert "/api/ok/from-ok-plugin" in paths

    # Failing plugin is marked ERROR; OK plugin stays ENABLED
    assert p_fail.status == PluginStatus.ERROR
    assert p_ok.status == PluginStatus.ENABLED


def test_celery_task_register_dispatch_via_async_bridge():
    """Stub plugin's async CELERY_TASK_REGISTER handler registers a Celery
    task via the AsyncSyncBridge (sync-to-async invocation)."""
    import asyncio

    from celery import Celery

    from plugin_sdk.async_bridge import AsyncSyncBridge
    from plugin_sdk.base import (
        BasePlugin,
        PluginManifest,
        PluginRegistry,
        PluginStatus,
    )
    from plugin_sdk.hooks import Hook, HookRegistry
    from plugin_sdk.plugin_manager import PluginManager

    HookRegistry().clear()
    PluginRegistry().clear()
    AsyncSyncBridge.reset_for_tests()

    fake_celery_app = Celery("test")

    class StubCeleryPlugin(BasePlugin):
        async def initialize(self):
            self.register_extension_point(
                Hook.CELERY_TASK_REGISTER, self._on_register
            )

        async def shutdown(self):
            pass

        async def _on_register(self, celery_app):
            @celery_app.task(name="stub.from_plugin")
            def stub_task():
                return "ok"

    manifest = PluginManifest(
        name="stub-celery",
        version="1.0.0",
        display_name="Stub Celery",
        description="Stub for #6970 test.",
        author="test",
        entry_point="test.module",
    )
    plugin = StubCeleryPlugin(manifest)
    asyncio.run(plugin.initialize())
    plugin.status = PluginStatus.ENABLED
    PluginRegistry().register(plugin)

    pm = PluginManager(plugin_dirs=[])

    async def _dispatch():
        await pm.dispatch_extension_point(
            Hook.CELERY_TASK_REGISTER, fake_celery_app
        )

    AsyncSyncBridge().run_coro(_dispatch())

    assert "stub.from_plugin" in fake_celery_app.tasks
    AsyncSyncBridge.reset_for_tests()
