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

from plugin_sdk.base import (
    BasePlugin,
    PluginManifest,
    PluginRegistry,
    PluginStatus,
    RequiredEnvVar,
)
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
    with pytest.raises(Exception):
        RequiredEnvVar(name="my_plugin_api_key", description="x")


def test_required_env_var_rejects_leading_digit():
    with pytest.raises(Exception):
        RequiredEnvVar(name="1MY_KEY", description="x")


def test_required_env_var_rejects_special_chars():
    with pytest.raises(Exception):
        RequiredEnvVar(name="MY-KEY", description="x")


def test_required_env_var_rejects_empty_name():
    with pytest.raises(Exception):
        RequiredEnvVar(name="", description="x")


def test_required_env_var_rejects_unicode_letters():
    """Unicode uppercase letters (e.g. Ω, Ё) are not legal POSIX env var names."""
    with pytest.raises(Exception):
        RequiredEnvVar(name="Ω_KEY", description="x")  # Ω


def test_required_env_var_rejects_mixed_case_in_middle():
    """Lowercase chars anywhere in the name are rejected, not just at the start."""
    with pytest.raises(Exception):
        RequiredEnvVar(name="MY_key", description="x")


def test_required_env_var_rejects_empty_description():
    """Description must be non-empty (min_length=1)."""
    with pytest.raises(Exception):
        RequiredEnvVar(name="MY_KEY", description="")


# ---------------------------------------------------------------------------
# PluginManifest.required_env field
# ---------------------------------------------------------------------------


def test_manifest_default_required_env_is_empty_list():
    """Backward compat: existing plugin.json without the field still parses."""
    m = _make_manifest()
    assert m.required_env == []


def test_manifest_with_required_env_parses():
    m = _make_manifest(
        required_env=[
            {
                "name": "MY_API_KEY",
                "description": "API key for service.",
                "secret": True,
                "required": False,
                "docs_url": "https://example.com/keys",
                "obtain_steps": ["Sign in", "Generate key"],
            }
        ]
    )
    assert len(m.required_env) == 1
    var = m.required_env[0]
    assert isinstance(var, RequiredEnvVar)
    assert var.name == "MY_API_KEY"
    assert var.secret is True
    assert var.docs_url == "https://example.com/keys"
    assert var.obtain_steps == ["Sign in", "Generate key"]


# ---------------------------------------------------------------------------
# PluginLoader._check_required_env
# ---------------------------------------------------------------------------


def test_check_required_env_returns_empty_when_no_required_env(monkeypatch):
    from plugin_sdk.loader import PluginLoader

    loader = PluginLoader([])
    manifest = _make_manifest()
    missing_required, missing_optional = loader._check_required_env(manifest)
    assert missing_required == []
    assert missing_optional == []


def test_check_required_env_finds_missing_required(monkeypatch):
    from plugin_sdk.loader import PluginLoader

    monkeypatch.delenv("TEST_REQUIRED_VAR", raising=False)
    loader = PluginLoader([])
    manifest = _make_manifest(
        required_env=[
            {
                "name": "TEST_REQUIRED_VAR",
                "description": "Required.",
                "required": True,
            }
        ]
    )
    missing_required, missing_optional = loader._check_required_env(manifest)
    assert missing_required == ["TEST_REQUIRED_VAR"]
    assert missing_optional == []


def test_check_required_env_finds_missing_optional(monkeypatch):
    from plugin_sdk.loader import PluginLoader

    monkeypatch.delenv("TEST_OPTIONAL_VAR", raising=False)
    loader = PluginLoader([])
    manifest = _make_manifest(
        required_env=[
            {
                "name": "TEST_OPTIONAL_VAR",
                "description": "Optional.",
                "required": False,
            }
        ]
    )
    missing_required, missing_optional = loader._check_required_env(manifest)
    assert missing_required == []
    assert missing_optional == ["TEST_OPTIONAL_VAR"]


def test_check_required_env_separates_required_and_optional(monkeypatch):
    from plugin_sdk.loader import PluginLoader

    monkeypatch.delenv("TEST_REQ_A", raising=False)
    monkeypatch.delenv("TEST_OPT_B", raising=False)
    monkeypatch.setenv("TEST_REQ_C", "value")
    loader = PluginLoader([])
    manifest = _make_manifest(
        required_env=[
            {"name": "TEST_REQ_A", "description": "x", "required": True},
            {"name": "TEST_OPT_B", "description": "x", "required": False},
            {"name": "TEST_REQ_C", "description": "x", "required": True},
        ]
    )
    missing_required, missing_optional = loader._check_required_env(manifest)
    assert missing_required == ["TEST_REQ_A"]
    assert missing_optional == ["TEST_OPT_B"]


def test_check_required_env_treats_empty_string_as_missing(monkeypatch):
    """An env var set to empty string is treated as not configured."""
    from plugin_sdk.loader import PluginLoader

    monkeypatch.setenv("TEST_EMPTY_VAR", "")
    loader = PluginLoader([])
    manifest = _make_manifest(
        required_env=[
            {"name": "TEST_EMPTY_VAR", "description": "x", "required": True}
        ]
    )
    missing_required, _ = loader._check_required_env(manifest)
    assert missing_required == ["TEST_EMPTY_VAR"]


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


# ---------------------------------------------------------------------------
# PluginLoader.load_plugin integration with required_env
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_plugin_returns_none_when_required_env_missing(monkeypatch, caplog):
    """Plugin with a missing required env var fails to load with an error log."""
    from plugin_sdk.loader import PluginLoader

    monkeypatch.delenv("TEST_REQ_LOAD_FAIL", raising=False)

    PluginRegistry().clear()
    loader = PluginLoader([])
    manifest = _make_manifest(
        required_env=[
            {
                "name": "TEST_REQ_LOAD_FAIL",
                "description": "x",
                "required": True,
            }
        ]
    )

    monkeypatch.setattr(
        loader, "_import_plugin_class", lambda ep: _ConcretePlugin
    )

    with caplog.at_level("ERROR"):
        result = await loader.load_plugin(manifest)

    assert result is None
    assert "TEST_REQ_LOAD_FAIL" in caplog.text


@pytest.mark.asyncio
async def test_load_plugin_succeeds_with_optional_env_missing(monkeypatch, caplog):
    """Plugin with missing optional env var loads, with info log."""
    from plugin_sdk.loader import PluginLoader

    PluginRegistry().clear()
    monkeypatch.delenv("TEST_OPT_LOAD_OK", raising=False)

    loader = PluginLoader([])
    manifest = _make_manifest(
        name="opt-test-plugin",
        required_env=[
            {
                "name": "TEST_OPT_LOAD_OK",
                "description": "x",
                "required": False,
            }
        ],
    )

    monkeypatch.setattr(
        loader, "_import_plugin_class", lambda ep: _ConcretePlugin
    )

    with caplog.at_level("INFO"):
        plugin = await loader.load_plugin(manifest)

    assert plugin is not None
    assert "TEST_OPT_LOAD_OK" in caplog.text


@pytest.mark.asyncio
async def test_load_plugin_succeeds_when_all_required_env_set(monkeypatch):
    """Plugin loads normally when all required env vars are configured."""
    from plugin_sdk.loader import PluginLoader

    PluginRegistry().clear()
    monkeypatch.setenv("TEST_REQ_LOAD_PRESENT", "value")

    loader = PluginLoader([])
    manifest = _make_manifest(
        name="all-set-plugin",
        required_env=[
            {
                "name": "TEST_REQ_LOAD_PRESENT",
                "description": "x",
                "required": True,
            }
        ],
    )

    monkeypatch.setattr(
        loader, "_import_plugin_class", lambda ep: _ConcretePlugin
    )

    plugin = await loader.load_plugin(manifest)
    assert plugin is not None
    assert plugin.manifest.name == "all-set-plugin"
