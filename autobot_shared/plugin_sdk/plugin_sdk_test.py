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
    manifest = _make_manifest(required_env=[{"name": "TEST_EMPTY_VAR", "description": "x", "required": True}])
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

    monkeypatch.setattr(loader, "_import_plugin_class", lambda ep: _ConcretePlugin)

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

    monkeypatch.setattr(loader, "_import_plugin_class", lambda ep: _ConcretePlugin)

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

    monkeypatch.setattr(loader, "_import_plugin_class", lambda ep: _ConcretePlugin)

    plugin = await loader.load_plugin(manifest)
    assert plugin is not None
    assert plugin.manifest.name == "all-set-plugin"


# ---------------------------------------------------------------------------
# PluginLoader.get_env_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_env_status_returns_correct_shape(monkeypatch):
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


def test_get_env_status_returns_none_for_unknown_plugin():
    from plugin_sdk.loader import PluginLoader

    PluginRegistry().clear()
    loader = PluginLoader([])
    assert loader.get_env_status("does-not-exist") is None


@pytest.mark.asyncio
async def test_get_env_status_never_returns_value(monkeypatch):
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
# PluginManager.is_started property (Issue #6970)
# ---------------------------------------------------------------------------


def test_plugin_manager_is_started_false_before_startup():
    pm = PluginManager(plugin_dirs=[])
    assert pm.is_started is False


@pytest.mark.asyncio
async def test_plugin_manager_is_started_true_after_startup():
    pm = PluginManager(plugin_dirs=[])
    await pm.startup()
    assert pm.is_started is True
    await pm.shutdown()


@pytest.mark.asyncio
async def test_plugin_manager_is_started_false_after_shutdown():
    pm = PluginManager(plugin_dirs=[])
    await pm.startup()
    await pm.shutdown()
    assert pm.is_started is False


# ---------------------------------------------------------------------------
# Hook enum extension-point values (Issue #6970)
# ---------------------------------------------------------------------------


def test_hook_api_router_register_value():
    assert Hook.API_ROUTER_REGISTER.value == "api_router_register"


def test_hook_celery_task_register_value():
    assert Hook.CELERY_TASK_REGISTER.value == "celery_task_register"


def test_hook_extension_points_distinct_from_event_hooks():
    """Extension-point hooks are separate enum members; not aliases of CUSTOM."""
    assert Hook.API_ROUTER_REGISTER is not Hook.CUSTOM
    assert Hook.CELERY_TASK_REGISTER is not Hook.CUSTOM
    assert Hook.API_ROUTER_REGISTER != Hook.CELERY_TASK_REGISTER


# ---------------------------------------------------------------------------
# BasePlugin.register_extension_point (Issue #6970)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_extension_point_accepts_async_handler():
    from plugin_sdk.hooks import Hook, HookRegistry

    HookRegistry().clear()
    PluginRegistry().clear()
    plugin = _ConcretePlugin(_make_manifest(name="ep-async-plugin"))

    async def my_handler(app):
        pass

    plugin.register_extension_point(Hook.API_ROUTER_REGISTER, my_handler)
    assert HookRegistry().get_hook_count(Hook.API_ROUTER_REGISTER.value) == 1


def test_register_extension_point_rejects_sync_handler():
    from plugin_sdk.hooks import Hook, HookRegistry

    HookRegistry().clear()
    PluginRegistry().clear()
    plugin = _ConcretePlugin(_make_manifest(name="ep-sync-plugin"))

    def my_sync_handler(app):
        pass

    with pytest.raises(TypeError) as exc_info:
        plugin.register_extension_point(Hook.API_ROUTER_REGISTER, my_sync_handler)
    assert "ep-sync-plugin" in str(exc_info.value)
    assert "api_router_register" in str(exc_info.value)
    assert HookRegistry().get_hook_count(Hook.API_ROUTER_REGISTER.value) == 0


@pytest.mark.asyncio
async def test_register_extension_point_records_plugin_name():
    from plugin_sdk.hooks import Hook, HookRegistry

    HookRegistry().clear()
    PluginRegistry().clear()
    plugin = _ConcretePlugin(_make_manifest(name="ep-name-test"))

    async def my_handler(app):
        pass

    plugin.register_extension_point(Hook.API_ROUTER_REGISTER, my_handler)
    handlers = HookRegistry()._hooks[Hook.API_ROUTER_REGISTER.value]
    assert handlers[0]["plugin_name"] == "ep-name-test"


def test_register_extension_point_rejects_non_hook_argument():
    """Plain string hook name (not Hook enum) is rejected with TypeError."""
    from plugin_sdk.hooks import HookRegistry

    HookRegistry().clear()
    PluginRegistry().clear()
    plugin = _ConcretePlugin(_make_manifest(name="ep-bad-hook-type"))

    async def my_handler(app):
        pass

    with pytest.raises(TypeError) as exc_info:
        plugin.register_extension_point("api_router_register", my_handler)
    assert "Hook enum" in str(exc_info.value)
    assert "ep-bad-hook-type" in str(exc_info.value)


def test_register_extension_point_rejects_event_style_hook():
    """ON_STARTUP and other event-style hooks are rejected with TypeError."""
    from plugin_sdk.hooks import Hook, HookRegistry

    HookRegistry().clear()
    PluginRegistry().clear()
    plugin = _ConcretePlugin(_make_manifest(name="ep-event-hook"))

    async def my_handler():
        pass

    with pytest.raises(TypeError) as exc_info:
        plugin.register_extension_point(Hook.ON_STARTUP, my_handler)
    assert "not an extension-point hook" in str(exc_info.value)
    assert "ep-event-hook" in str(exc_info.value)


@pytest.mark.asyncio
async def test_register_extension_point_accepts_bound_async_method():
    """Bound async methods (typical plugin handler pattern) are accepted."""
    from plugin_sdk.hooks import Hook, HookRegistry

    HookRegistry().clear()
    PluginRegistry().clear()

    class _MyPlugin(_ConcretePlugin):
        async def my_async_method(self, app):
            return "called"

    plugin = _MyPlugin(_make_manifest(name="ep-bound-method"))
    plugin.register_extension_point(Hook.API_ROUTER_REGISTER, plugin.my_async_method)
    assert HookRegistry().get_hook_count(Hook.API_ROUTER_REGISTER.value) == 1


@pytest.mark.asyncio
async def test_register_extension_point_accepts_partial_of_async():
    """functools.partial wrapping an async function is accepted."""
    import functools

    from plugin_sdk.hooks import Hook, HookRegistry

    HookRegistry().clear()
    PluginRegistry().clear()
    plugin = _ConcretePlugin(_make_manifest(name="ep-partial"))

    async def my_async_handler(extra_arg, app):
        pass

    bound = functools.partial(my_async_handler, "extra")
    plugin.register_extension_point(Hook.API_ROUTER_REGISTER, bound)
    assert HookRegistry().get_hook_count(Hook.API_ROUTER_REGISTER.value) == 1


# ---------------------------------------------------------------------------
# PluginManager.dispatch_extension_point (Issue #6970)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_extension_point_invokes_async_handler():
    from plugin_sdk.hooks import Hook, HookRegistry

    HookRegistry().clear()
    PluginRegistry().clear()
    pm = PluginManager(plugin_dirs=[])

    plugin = _ConcretePlugin(_make_manifest(name="dep-async-plugin"))
    PluginRegistry().register(plugin)

    invoked = []

    async def handler(arg):
        invoked.append(arg)

    HookRegistry().register_hook(
        Hook.API_ROUTER_REGISTER.value, handler, plugin_name="dep-async-plugin"
    )

    await pm.dispatch_extension_point(Hook.API_ROUTER_REGISTER, "test-arg")
    assert invoked == ["test-arg"]


@pytest.mark.asyncio
async def test_dispatch_extension_point_marks_failing_plugin_error_and_continues():
    """Two plugins; first raises in handler. Second still fires. First is ERROR."""
    from plugin_sdk.hooks import Hook, HookRegistry

    HookRegistry().clear()
    PluginRegistry().clear()
    pm = PluginManager(plugin_dirs=[])

    p1 = _ConcretePlugin(_make_manifest(name="dep-fail"))
    p2 = _ConcretePlugin(_make_manifest(name="dep-ok"))
    PluginRegistry().register(p1)
    PluginRegistry().register(p2)
    await p1.enable()
    await p2.enable()

    invoked = []

    async def fail_handler(arg):
        raise RuntimeError("intentional handler failure")

    async def ok_handler(arg):
        invoked.append(arg)

    HookRegistry().register_hook(
        Hook.API_ROUTER_REGISTER.value, fail_handler, plugin_name="dep-fail"
    )
    HookRegistry().register_hook(
        Hook.API_ROUTER_REGISTER.value, ok_handler, plugin_name="dep-ok"
    )

    await pm.dispatch_extension_point(Hook.API_ROUTER_REGISTER, "x")

    assert invoked == ["x"]  # second plugin's handler still ran
    assert p1.status == PluginStatus.ERROR
    assert p2.status == PluginStatus.ENABLED


@pytest.mark.asyncio
async def test_dispatch_extension_point_handles_no_registered_handlers():
    from plugin_sdk.hooks import Hook, HookRegistry

    HookRegistry().clear()
    pm = PluginManager(plugin_dirs=[])
    # Should not raise; no-op
    await pm.dispatch_extension_point(Hook.API_ROUTER_REGISTER, "x")


@pytest.mark.asyncio
async def test_dispatch_extension_point_does_not_affect_call_hook_semantics():
    """Verify event-style hooks are unaffected: a raising handler does NOT mark plugin ERROR."""
    from plugin_sdk.hooks import Hook, HookRegistry

    HookRegistry().clear()
    PluginRegistry().clear()
    pm = PluginManager(plugin_dirs=[])

    plugin = _ConcretePlugin(_make_manifest(name="event-fail"))
    PluginRegistry().register(plugin)
    await plugin.enable()

    async def fail_handler():
        raise RuntimeError("intentional")

    HookRegistry().register_hook(
        Hook.ON_KB_DOCUMENT_ADDED.value, fail_handler, plugin_name="event-fail"
    )

    # call_hook (the event-style dispatch) should swallow + log; NOT mark ERROR
    await HookRegistry().call_hook(Hook.ON_KB_DOCUMENT_ADDED.value)

    # Plugin status remains ENABLED — extension-point semantics not applied here
    assert plugin.status == PluginStatus.ENABLED


@pytest.mark.asyncio
async def test_dispatch_extension_point_forwards_args_and_kwargs():
    from plugin_sdk.hooks import Hook, HookRegistry

    HookRegistry().clear()
    PluginRegistry().clear()
    pm = PluginManager(plugin_dirs=[])

    plugin = _ConcretePlugin(_make_manifest(name="args-test"))
    PluginRegistry().register(plugin)

    received = {}

    async def handler(a, b, c=None):
        received["a"] = a
        received["b"] = b
        received["c"] = c

    HookRegistry().register_hook(
        Hook.API_ROUTER_REGISTER.value, handler, plugin_name="args-test"
    )

    await pm.dispatch_extension_point(Hook.API_ROUTER_REGISTER, 1, 2, c=3)
    assert received == {"a": 1, "b": 2, "c": 3}


@pytest.mark.asyncio
async def test_dispatch_extension_point_rejects_event_style_hook():
    """ValueError if caller passes an event-style hook (e.g. ON_STARTUP)."""
    from plugin_sdk.hooks import Hook, HookRegistry

    HookRegistry().clear()
    PluginRegistry().clear()
    pm = PluginManager(plugin_dirs=[])

    with pytest.raises(ValueError) as exc_info:
        await pm.dispatch_extension_point(Hook.ON_STARTUP)
    assert "extension-point hook" in str(exc_info.value)
    assert "on_startup" in str(exc_info.value)


@pytest.mark.asyncio
async def test_dispatch_extension_point_safe_under_handler_mutation():
    """Defensive copy: a handler that registers a NEW handler during dispatch
    does not cause list-changed-size or skipped/duplicate calls."""
    from plugin_sdk.hooks import Hook, HookRegistry

    HookRegistry().clear()
    PluginRegistry().clear()
    pm = PluginManager(plugin_dirs=[])

    plugin = _ConcretePlugin(_make_manifest(name="mut-test"))
    PluginRegistry().register(plugin)

    invoked = []

    async def added_during_dispatch():
        invoked.append("added")

    async def first_handler():
        invoked.append("first")
        # Register a second handler mid-dispatch (does NOT fire this round
        # because we operate on a defensive copy of the original handler list)
        HookRegistry().register_hook(
            Hook.API_ROUTER_REGISTER.value,
            added_during_dispatch,
            plugin_name="mut-test",
        )

    HookRegistry().register_hook(
        Hook.API_ROUTER_REGISTER.value, first_handler, plugin_name="mut-test"
    )

    await pm.dispatch_extension_point(Hook.API_ROUTER_REGISTER)
    # Only the first handler ran during this dispatch
    assert invoked == ["first"]
