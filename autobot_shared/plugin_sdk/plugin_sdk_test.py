# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin SDK Tests

Tests for BasePlugin, PluginManifest, PluginRegistry, HookRegistry,
PluginLoader, and PluginManager.

Issue #3278 - Plugin and extension system for third-party integrations.
"""

import pytest

from plugin_sdk.base import BasePlugin, PluginManifest, PluginRegistry, PluginStatus
from plugin_sdk.hooks import Hook, HookRegistry
from plugin_sdk.plugin_manager import PluginManager

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_manifest(**overrides) -> PluginManifest:
    defaults = {
        "name": "test-plugin",
        "version": "1.0.0",
        "display_name": "Test Plugin",
        "description": "A test plugin",
        "author": "mrveiss",
        "entry_point": "test.module",
    }
    defaults.update(overrides)
    return PluginManifest(**defaults)


class _ConcretePlugin(BasePlugin):
    """Minimal concrete plugin for tests."""

    def __init__(self, manifest, config=None):
        super().__init__(manifest, config)
        self.initialized = False
        self.shutdown_called = False

    async def initialize(self):
        self.initialized = True

    async def shutdown(self):
        self.shutdown_called = True


# ---------------------------------------------------------------------------
# PluginManifest validation
# ---------------------------------------------------------------------------


def test_manifest_valid():
    m = _make_manifest()
    assert m.name == "test-plugin"
    assert m.version == "1.0.0"


def test_manifest_invalid_version():
    with pytest.raises(Exception):
        _make_manifest(version="1.0")


def test_manifest_invalid_name():
    with pytest.raises(Exception):
        _make_manifest(name="bad name!")


# ---------------------------------------------------------------------------
# RequiredEnvVar validation
# ---------------------------------------------------------------------------


def test_required_env_var_accepts_valid_name():
    from plugin_sdk.base import RequiredEnvVar

    var = RequiredEnvVar(
        name="MY_PLUGIN_API_KEY",
        description="The API key.",
    )
    assert var.name == "MY_PLUGIN_API_KEY"
    assert var.secret is False
    assert var.required is False
    assert var.docs_url is None
    assert var.obtain_steps == []


def test_required_env_var_rejects_lowercase_name():
    from plugin_sdk.base import RequiredEnvVar

    with pytest.raises(Exception):
        RequiredEnvVar(name="my_plugin_api_key", description="x")


def test_required_env_var_rejects_leading_digit():
    from plugin_sdk.base import RequiredEnvVar

    with pytest.raises(Exception):
        RequiredEnvVar(name="1MY_KEY", description="x")


def test_required_env_var_rejects_special_chars():
    from plugin_sdk.base import RequiredEnvVar

    with pytest.raises(Exception):
        RequiredEnvVar(name="MY-KEY", description="x")


def test_required_env_var_rejects_empty_name():
    from plugin_sdk.base import RequiredEnvVar

    with pytest.raises(Exception):
        RequiredEnvVar(name="", description="x")


# ---------------------------------------------------------------------------
# BasePlugin lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plugin_initialize():
    manifest = _make_manifest()
    plugin = _ConcretePlugin(manifest)
    assert plugin.status == PluginStatus.UNLOADED
    await plugin.initialize()
    assert plugin.initialized is True


@pytest.mark.asyncio
async def test_plugin_enable_disable():
    manifest = _make_manifest()
    plugin = _ConcretePlugin(manifest)
    await plugin.enable()
    assert plugin.status == PluginStatus.ENABLED
    await plugin.disable()
    assert plugin.status == PluginStatus.DISABLED


@pytest.mark.asyncio
async def test_plugin_get_info():
    manifest = _make_manifest()
    plugin = _ConcretePlugin(manifest)
    info = plugin.get_info()
    assert info["name"] == "test-plugin"
    assert info["status"] == PluginStatus.UNLOADED.value


# ---------------------------------------------------------------------------
# PluginRegistry
# ---------------------------------------------------------------------------


def test_registry_register_and_get(monkeypatch):
    registry = PluginRegistry()
    registry.clear()
    plugin = _ConcretePlugin(_make_manifest())
    registry.register(plugin)
    assert registry.get_plugin("test-plugin") is plugin


def test_registry_duplicate_raises(monkeypatch):
    registry = PluginRegistry()
    registry.clear()
    plugin = _ConcretePlugin(_make_manifest())
    registry.register(plugin)
    with pytest.raises(ValueError):
        registry.register(plugin)


def test_registry_unregister(monkeypatch):
    registry = PluginRegistry()
    registry.clear()
    plugin = _ConcretePlugin(_make_manifest())
    registry.register(plugin)
    registry.unregister("test-plugin")
    assert registry.get_plugin("test-plugin") is None


@pytest.mark.asyncio
async def test_registry_get_enabled():
    registry = PluginRegistry()
    registry.clear()
    plugin = _ConcretePlugin(_make_manifest())
    registry.register(plugin)
    await plugin.enable()
    enabled = registry.get_enabled_plugins()
    assert "test-plugin" in enabled


# ---------------------------------------------------------------------------
# HookRegistry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hook_register_and_call():
    hr = HookRegistry()
    hr.clear()
    results = []

    async def cb(**kwargs):
        results.append(kwargs)

    hr.register_hook(Hook.ON_MESSAGE_RECEIVED.value, cb, plugin_name="test")
    await hr.call_hook(Hook.ON_MESSAGE_RECEIVED.value, session_id="s1", message="hello")
    assert len(results) == 1
    assert results[0]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_hook_sync_callback():
    hr = HookRegistry()
    hr.clear()
    results = []

    def sync_cb(**kwargs):
        results.append(kwargs.get("value"))

    hr.register_hook("custom_hook", sync_cb, plugin_name="test")
    await hr.call_hook("custom_hook", value=42)
    assert results == [42]


@pytest.mark.asyncio
async def test_hook_error_in_callback_does_not_propagate():
    hr = HookRegistry()
    hr.clear()

    async def bad_cb(**_):
        raise RuntimeError("plugin error")

    hr.register_hook("test_hook", bad_cb, plugin_name="bad-plugin")
    # Must not raise
    results = await hr.call_hook("test_hook")
    assert results == []


@pytest.mark.asyncio
async def test_hook_unregister_by_plugin():
    hr = HookRegistry()
    hr.clear()
    results = []

    async def cb(**_):
        results.append(1)

    hr.register_hook(Hook.ON_KB_SEARCH.value, cb, plugin_name="test")
    hr.unregister_hook(Hook.ON_KB_SEARCH.value, plugin_name="test")
    await hr.call_hook(Hook.ON_KB_SEARCH.value)
    assert results == []


def test_hook_count():
    hr = HookRegistry()
    hr.clear()
    hr.register_hook("h", lambda: None, plugin_name="p1")
    hr.register_hook("h", lambda: None, plugin_name="p2")
    assert hr.get_hook_count("h") == 2


# ---------------------------------------------------------------------------
# New hook enum values (Issue #3278)
# ---------------------------------------------------------------------------


def test_new_hook_values_exist():
    assert Hook.ON_KB_SEARCH.value == "on_kb_search"
    assert Hook.ON_KB_DOCUMENT_ADDED.value == "on_kb_document_added"
    assert Hook.ON_KB_DOCUMENT_REMOVED.value == "on_kb_document_removed"
    assert Hook.ON_WORKFLOW_START.value == "on_workflow_start"
    assert Hook.ON_WORKFLOW_COMPLETE.value == "on_workflow_complete"
    assert Hook.ON_WORKFLOW_ERROR.value == "on_workflow_error"


# ---------------------------------------------------------------------------
# PluginManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plugin_manager_startup_no_dirs():
    """PluginManager with no plugin dirs starts without error."""
    # Clear singleton state left by earlier tests
    PluginRegistry().clear()
    HookRegistry().clear()
    pm = PluginManager([])
    await pm.startup()
    assert pm.get_plugin_status() == {}
    await pm.shutdown()


@pytest.mark.asyncio
async def test_plugin_manager_double_startup_is_noop():
    """Calling startup twice does not raise or double-load."""
    pm = PluginManager([])
    await pm.startup()
    await pm.startup()  # should log warning and return early
    await pm.shutdown()


@pytest.mark.asyncio
async def test_plugin_manager_is_enabled_false_for_unknown():
    pm = PluginManager([])
    assert pm.is_enabled("nonexistent") is False
    await pm.shutdown()
