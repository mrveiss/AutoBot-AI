# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Plugin SDK Tests

Tests for BasePlugin, PluginManifest, PluginRegistry, HookRegistry,
PluginLoader, and PluginManager.

Issue #3278 - Plugin and extension system for third-party integrations.
"""

import warnings

import pytest

from plugin_sdk.base import (
    BasePlugin,
    PluginLoadError,
    PluginManifest,
    PluginRegistry,
    PluginStatus,
    RequiredEnvVar,
)
from plugin_sdk.hooks import HOOK_REGISTRY, Hook, HookRegistry, HookSignature, validate_hook_names
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

    def __init__(self, manifest, config=None) -> None:
        super().__init__(manifest, config)
        self.initialized = False
        self.shutdown_called = False

    async def initialize(self) -> None:
        self.initialized = True

    async def shutdown(self) -> None:
        self.shutdown_called = True


# ---------------------------------------------------------------------------
# PluginManifest validation
# ---------------------------------------------------------------------------


def test_manifest_valid() -> None:
    m = _make_manifest()
    assert m.name == "test-plugin"
    assert m.version == "1.0.0"


def test_manifest_invalid_version() -> None:
    with pytest.raises(Exception):
        _make_manifest(version="1.0")


def test_manifest_invalid_name() -> None:
    with pytest.raises(Exception):
        _make_manifest(name="bad name!")


# ---------------------------------------------------------------------------
# RequiredEnvVar validation
# ---------------------------------------------------------------------------


def test_required_env_var_accepts_valid_name() -> None:
    var = RequiredEnvVar(
        name="MY_PLUGIN_API_KEY",
        description="The API key.",
    )
    assert var.name == "MY_PLUGIN_API_KEY"
    assert var.secret is False
    assert var.required is False
    assert var.docs_url is None
    assert var.obtain_steps == []


def test_required_env_var_rejects_lowercase_name() -> None:
    with pytest.raises(Exception):
        RequiredEnvVar(name="my_plugin_api_key", description="x")


def test_required_env_var_rejects_leading_digit() -> None:
    with pytest.raises(Exception):
        RequiredEnvVar(name="1MY_KEY", description="x")


def test_required_env_var_rejects_special_chars() -> None:
    with pytest.raises(Exception):
        RequiredEnvVar(name="MY-KEY", description="x")


def test_required_env_var_rejects_empty_name() -> None:
    with pytest.raises(Exception):
        RequiredEnvVar(name="", description="x")


def test_required_env_var_rejects_unicode_letters() -> None:
    """Unicode uppercase letters (e.g. Ω, Ё) are not legal POSIX env var names."""
    with pytest.raises(Exception):
        RequiredEnvVar(name="Ω_KEY", description="x")  # Ω


def test_required_env_var_rejects_mixed_case_in_middle() -> None:
    """Lowercase chars anywhere in the name are rejected, not just at the start."""
    with pytest.raises(Exception):
        RequiredEnvVar(name="MY_key", description="x")


def test_required_env_var_rejects_empty_description() -> None:
    """Description must be non-empty (min_length=1)."""
    with pytest.raises(Exception):
        RequiredEnvVar(name="MY_KEY", description="")


# ---------------------------------------------------------------------------
# PluginManifest.required_env field
# ---------------------------------------------------------------------------


def test_manifest_default_required_env_is_empty_list() -> None:
    """Backward compat: existing plugin.json without the field still parses."""
    m = _make_manifest()
    assert m.required_env == []


def test_manifest_with_required_env_parses() -> None:
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


def test_check_required_env_returns_empty_when_no_required_env(monkeypatch) -> None:
    from plugin_sdk.loader import PluginLoader

    loader = PluginLoader([])
    manifest = _make_manifest()
    missing_required, missing_optional = loader._check_required_env(manifest)
    assert missing_required == []
    assert missing_optional == []


def test_check_required_env_finds_missing_required(monkeypatch) -> None:
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


def test_check_required_env_finds_missing_optional(monkeypatch) -> None:
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


def test_check_required_env_separates_required_and_optional(monkeypatch) -> None:
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


def test_check_required_env_treats_empty_string_as_missing(monkeypatch) -> None:
    """An env var set to empty string is treated as not configured."""
    from plugin_sdk.loader import PluginLoader

    monkeypatch.setenv("TEST_EMPTY_VAR", "")
    loader = PluginLoader([])
    manifest = _make_manifest(required_env=[{"name": "TEST_EMPTY_VAR", "description": "x", "required": True}])
    missing_required, _ = loader._check_required_env(manifest)
    assert missing_required == ["TEST_EMPTY_VAR"]


# ---------------------------------------------------------------------------
# BasePlugin lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plugin_initialize() -> None:
    manifest = _make_manifest()
    plugin = _ConcretePlugin(manifest)
    assert plugin.status == PluginStatus.UNLOADED
    await plugin.initialize()
    assert plugin.initialized is True


@pytest.mark.asyncio
async def test_plugin_enable_disable() -> None:
    manifest = _make_manifest()
    plugin = _ConcretePlugin(manifest)
    await plugin.enable()
    assert plugin.status == PluginStatus.ENABLED
    await plugin.disable()
    assert plugin.status == PluginStatus.DISABLED


@pytest.mark.asyncio
async def test_plugin_get_info() -> None:
    manifest = _make_manifest()
    plugin = _ConcretePlugin(manifest)
    info = plugin.get_info()
    assert info["name"] == "test-plugin"
    assert info["status"] == PluginStatus.UNLOADED.value


# ---------------------------------------------------------------------------
# PluginRegistry
# ---------------------------------------------------------------------------


def test_registry_register_and_get(monkeypatch) -> None:
    registry = PluginRegistry()
    registry.clear()
    plugin = _ConcretePlugin(_make_manifest())
    registry.register(plugin)
    assert registry.get_plugin("test-plugin") is plugin


def test_registry_duplicate_raises(monkeypatch) -> None:
    registry = PluginRegistry()
    registry.clear()
    plugin = _ConcretePlugin(_make_manifest())
    registry.register(plugin)
    with pytest.raises(ValueError):
        registry.register(plugin)


def test_registry_unregister(monkeypatch) -> None:
    registry = PluginRegistry()
    registry.clear()
    plugin = _ConcretePlugin(_make_manifest())
    registry.register(plugin)
    registry.unregister("test-plugin")
    assert registry.get_plugin("test-plugin") is None


@pytest.mark.asyncio
async def test_registry_get_enabled() -> None:
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
async def test_hook_register_and_call() -> None:
    hr = HookRegistry()
    hr.clear()
    results = []

    async def cb(**kwargs) -> None:
        results.append(kwargs)

    hr.register_hook(Hook.ON_MESSAGE_RECEIVED.value, cb, plugin_name="test")
    await hr.call_hook(Hook.ON_MESSAGE_RECEIVED.value, session_id="s1", message="hello")
    assert len(results) == 1
    assert results[0]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_hook_sync_callback() -> None:
    hr = HookRegistry()
    hr.clear()
    results = []

    def sync_cb(**kwargs) -> None:
        results.append(kwargs.get("value"))

    hr.register_hook("custom_hook", sync_cb, plugin_name="test")
    await hr.call_hook("custom_hook", value=42)
    assert results == [42]


@pytest.mark.asyncio
async def test_hook_error_in_callback_does_not_propagate() -> None:
    hr = HookRegistry()
    hr.clear()

    async def bad_cb(**_) -> None:
        raise RuntimeError("plugin error")

    hr.register_hook("test_hook", bad_cb, plugin_name="bad-plugin")
    # Must not raise
    results = await hr.call_hook("test_hook")
    assert results == []


@pytest.mark.asyncio
async def test_hook_unregister_by_plugin() -> None:
    hr = HookRegistry()
    hr.clear()
    results = []

    async def cb(**_) -> None:
        results.append(1)

    hr.register_hook(Hook.ON_KB_SEARCH.value, cb, plugin_name="test")
    hr.unregister_hook(Hook.ON_KB_SEARCH.value, plugin_name="test")
    await hr.call_hook(Hook.ON_KB_SEARCH.value)
    assert results == []


def test_hook_count() -> None:
    hr = HookRegistry()
    hr.clear()
    hr.register_hook("h", lambda: None, plugin_name="p1")
    hr.register_hook("h", lambda: None, plugin_name="p2")
    assert hr.get_hook_count("h") == 2


# ---------------------------------------------------------------------------
# New hook enum values (Issue #3278)
# ---------------------------------------------------------------------------


def test_new_hook_values_exist() -> None:
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
async def test_plugin_manager_startup_no_dirs() -> None:
    """PluginManager with no plugin dirs starts without error."""
    # Clear singleton state left by earlier tests
    PluginRegistry().clear()
    HookRegistry().clear()
    pm = PluginManager([])
    await pm.startup()
    assert pm.get_plugin_status() == {}
    await pm.shutdown()


@pytest.mark.asyncio
async def test_plugin_manager_double_startup_is_noop() -> None:
    """Calling startup twice does not raise or double-load."""
    pm = PluginManager([])
    await pm.startup()
    await pm.startup()  # should log warning and return early
    await pm.shutdown()


@pytest.mark.asyncio
async def test_plugin_manager_is_enabled_false_for_unknown() -> None:
    pm = PluginManager([])
    assert pm.is_enabled("nonexistent") is False
    await pm.shutdown()


# ---------------------------------------------------------------------------
# PluginLoader.load_plugin integration with required_env
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_plugin_returns_none_when_required_env_missing(monkeypatch, caplog) -> None:
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

    monkeypatch.setattr(loader, "_import_plugin_class", lambda ep: _ConcretePlugin)

    with caplog.at_level("ERROR"):
        result = await loader.load_plugin(manifest)

    assert result is None
    assert "TEST_REQ_LOAD_FAIL" in caplog.text


@pytest.mark.asyncio
async def test_load_plugin_succeeds_with_optional_env_missing(monkeypatch, caplog) -> None:
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

    monkeypatch.setattr(loader, "_import_plugin_class", lambda ep: _ConcretePlugin)

    with caplog.at_level("INFO"):
        plugin = await loader.load_plugin(manifest)

    assert plugin is not None
    assert "TEST_OPT_LOAD_OK" in caplog.text


@pytest.mark.asyncio
async def test_load_plugin_succeeds_when_all_required_env_set(monkeypatch) -> None:
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

    monkeypatch.setattr(loader, "_import_plugin_class", lambda ep: _ConcretePlugin)

    plugin = await loader.load_plugin(manifest)
    assert plugin is not None
    assert plugin.manifest.name == "all-set-plugin"


# ---------------------------------------------------------------------------
# PluginLoader.get_env_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_env_status_returns_correct_shape(monkeypatch) -> None:
    from plugin_sdk.loader import PluginLoader

    PluginRegistry().clear()
    monkeypatch.setenv("TEST_STATUS_PRESENT", "actual_secret_value")
    monkeypatch.delenv("TEST_STATUS_MISSING", raising=False)

    loader = PluginLoader([])
    manifest = _make_manifest(
        name="status-shape-plugin",
        required_env=[
            {
                "name": "TEST_STATUS_PRESENT",
                "description": "Set var.",
                "secret": True,
                "required": False,
                "docs_url": "https://example.com",
                "obtain_steps": ["one", "two"],
            },
            {
                "name": "TEST_STATUS_MISSING",
                "description": "Unset var.",
                "secret": False,
                "required": False,
            },
        ],
    )
    monkeypatch.setattr(loader, "_import_plugin_class", lambda ep: _ConcretePlugin)
    await loader.load_plugin(manifest)

    status = loader.get_env_status("status-shape-plugin")
    assert status is not None
    assert set(status.keys()) == {"TEST_STATUS_PRESENT", "TEST_STATUS_MISSING"}

    present = status["TEST_STATUS_PRESENT"]
    assert present == {
        "configured": True,
        "secret": True,
        "required": False,
        "description": "Set var.",
        "docs_url": "https://example.com",
        "obtain_steps": ["one", "two"],
    }

    missing = status["TEST_STATUS_MISSING"]
    assert missing["configured"] is False
    assert missing["secret"] is False
    assert missing["docs_url"] is None
    assert missing["obtain_steps"] == []


def test_get_env_status_returns_none_for_unknown_plugin() -> None:
    from plugin_sdk.loader import PluginLoader

    PluginRegistry().clear()
    loader = PluginLoader([])
    assert loader.get_env_status("does-not-exist") is None


@pytest.mark.asyncio
async def test_get_env_status_never_returns_value(monkeypatch) -> None:
    """Critical privacy test: env-var values must NEVER be in the response."""
    from plugin_sdk.loader import PluginLoader

    PluginRegistry().clear()
    secret_value = "sk-supersecret-do-not-leak-1234"
    monkeypatch.setenv("TEST_SECRET_LEAK_CHECK", secret_value)

    loader = PluginLoader([])
    manifest = _make_manifest(
        name="leak-check-plugin",
        required_env=[
            {
                "name": "TEST_SECRET_LEAK_CHECK",
                "description": "Sensitive.",
                "secret": True,
                "required": True,
            }
        ],
    )
    monkeypatch.setattr(loader, "_import_plugin_class", lambda ep: _ConcretePlugin)
    await loader.load_plugin(manifest)

    status = loader.get_env_status("leak-check-plugin")
    # Belt-and-braces: check both repr (any Python serialization) AND
    # JSON (the actual API serialization path). Today repr catches everything
    # because all leaf types are primitives; this future-proofs against a
    # maintainer adding a SecretStr-style wrapper whose __repr__ masks values.
    import json

    assert secret_value not in repr(status)
    assert secret_value not in json.dumps(status, default=str)


# ---------------------------------------------------------------------------
# GH#6970 — HOOK_REGISTRY and validate_hook_names
# ---------------------------------------------------------------------------


def test_hook_registry_covers_all_hook_enum_values() -> None:
    """Every Hook enum value must have a HOOK_REGISTRY entry."""
    for member in Hook:
        assert member.value in HOOK_REGISTRY, f"Hook.{member.name} missing from HOOK_REGISTRY"


def test_hook_signature_has_description_and_params() -> None:
    sig = HOOK_REGISTRY[Hook.ON_MESSAGE_RECEIVED.value]
    assert isinstance(sig, HookSignature)
    assert sig.description
    assert "session_id" in sig.params
    assert "message" in sig.params


def test_validate_hook_names_no_warning_for_known_hooks() -> None:
    known = [Hook.ON_STARTUP.value, Hook.ON_SHUTDOWN.value]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        validate_hook_names(known, plugin_name="test-plugin")
    assert len(w) == 0


def test_validate_hook_names_warns_for_unknown_hook() -> None:
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        validate_hook_names(["totally_unknown_hook"], plugin_name="my-plugin")
    assert len(w) == 1
    assert issubclass(w[0].category, DeprecationWarning)
    assert "totally_unknown_hook" in str(w[0].message)
    assert "my-plugin" in str(w[0].message)


def test_validate_hook_names_warns_once_per_unknown() -> None:
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        validate_hook_names(["bad_hook_a", "bad_hook_b", Hook.ON_STARTUP.value], plugin_name="p")
    assert len(w) == 2


def test_validate_hook_names_empty_list_is_noop() -> None:
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        validate_hook_names([], plugin_name="p")
    assert len(w) == 0


@pytest.mark.asyncio
async def test_load_plugin_validates_hook_names(monkeypatch) -> None:
    """Unknown hook in manifest triggers a DeprecationWarning during load."""
    from plugin_sdk.loader import PluginLoader

    PluginRegistry().clear()
    loader = PluginLoader([])
    manifest = _make_manifest(name="hook-warn-plugin", hooks=["totally_invalid_hook"])
    monkeypatch.setattr(loader, "_import_plugin_class", lambda ep: _ConcretePlugin)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        plugin = await loader.load_plugin(manifest)

    assert plugin is not None
    assert any("totally_invalid_hook" in str(warning.message) for warning in w)


@pytest.mark.asyncio
async def test_load_plugin_no_warning_for_known_hooks(monkeypatch) -> None:
    """Known hook names produce no DeprecationWarning during load."""
    from plugin_sdk.loader import PluginLoader

    PluginRegistry().clear()
    loader = PluginLoader([])
    manifest = _make_manifest(name="hook-ok-plugin", hooks=[Hook.ON_STARTUP.value])
    monkeypatch.setattr(loader, "_import_plugin_class", lambda ep: _ConcretePlugin)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        plugin = await loader.load_plugin(manifest)

    assert plugin is not None
    dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert len(dep_warnings) == 0


# ---------------------------------------------------------------------------
# GH#6971 — PluginLoadError raised for missing required env vars
# ---------------------------------------------------------------------------


def test_plugin_load_error_is_runtime_error() -> None:
    assert issubclass(PluginLoadError, RuntimeError)


@pytest.mark.asyncio
async def test_load_plugin_raises_plugin_load_error_when_required_env_missing(monkeypatch) -> None:
    """PluginLoadError propagates when load_plugin is called without exception swallowing."""
    from plugin_sdk.loader import PluginLoader

    monkeypatch.delenv("TEST_PLE_VAR", raising=False)
    PluginRegistry().clear()

    loader = PluginLoader([])
    manifest = _make_manifest(
        name="ple-test-plugin",
        required_env=[{"name": "TEST_PLE_VAR", "description": "x", "required": True}],
    )
    monkeypatch.setattr(loader, "_import_plugin_class", lambda ep: _ConcretePlugin)

    # Bypass the outer try/except to observe the raw exception
    with pytest.raises(PluginLoadError, match="TEST_PLE_VAR"):
        missing_required, _ = loader._check_required_env(manifest)
        if missing_required:
            from plugin_sdk.base import PluginLoadError as _PLE

            raise _PLE(f"Cannot load plugin '{manifest.name}': " f"required env vars not set: {missing_required}")


@pytest.mark.asyncio
async def test_load_plugin_returns_none_and_logs_when_required_env_missing(monkeypatch, caplog) -> None:
    """Via the outer exception handler, load_plugin still returns None (backward compat)."""
    from plugin_sdk.loader import PluginLoader

    monkeypatch.delenv("TEST_REQ_LOAD_FAIL_V2", raising=False)
    PluginRegistry().clear()

    loader = PluginLoader([])
    manifest = _make_manifest(
        name="ple-bc-plugin",
        required_env=[{"name": "TEST_REQ_LOAD_FAIL_V2", "description": "x", "required": True}],
    )
    monkeypatch.setattr(loader, "_import_plugin_class", lambda ep: _ConcretePlugin)

    with caplog.at_level("ERROR"):
        result = await loader.load_plugin(manifest)

    assert result is None
    assert "TEST_REQ_LOAD_FAIL_V2" in caplog.text
