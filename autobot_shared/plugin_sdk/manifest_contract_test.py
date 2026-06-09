# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for ManifestContract Protocol and UnifiedRegistry (GH#7369)."""

import warnings
from dataclasses import dataclass

import pytest

from plugin_sdk.manifest_contract import ManifestContract
from plugin_sdk.unified_registry import get_unified_registry

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_registry():
    """Isolate each test by clearing the singleton registry."""
    registry = get_unified_registry()
    registry.clear()
    yield
    registry.clear()


@dataclass
class _FakeManifest:
    name: str
    version: str
    description: str
    kind: str


def _plugin_manifest():
    from plugin_sdk.base import PluginManifest

    return PluginManifest(
        name="my_plugin",
        version="1.0.0",
        display_name="My Plugin",
        description="A test plugin",
        author="tester",
        entry_point="plugins.my_plugin.main",
    )


# ---------------------------------------------------------------------------
# ManifestContract structural subtype checks
# ---------------------------------------------------------------------------


class TestManifestContractProtocol:
    def test_fake_dataclass_satisfies_protocol(self) -> None:
        m = _FakeManifest(name="x", version="1.0.0", description="d", kind="skill")
        assert isinstance(m, ManifestContract)

    def test_plugin_manifest_satisfies_protocol(self) -> None:
        m = _plugin_manifest()
        assert isinstance(m, ManifestContract)

    def test_extension_manifest_satisfies_protocol(self) -> None:
        from plugin_sdk.extension_manifest import ExtensionManifest

        m = ExtensionManifest(name="ext", version="0.1.0", description="an ext")
        assert isinstance(m, ManifestContract)

    def test_object_missing_field_fails_protocol(self) -> None:
        class Bad:
            name = "x"
            version = "1.0.0"
            description = "d"
            # missing kind

        assert not isinstance(Bad(), ManifestContract)

    def test_plain_dict_fails_protocol(self) -> None:
        assert not isinstance({"name": "x", "version": "1", "description": "d", "kind": "skill"}, ManifestContract)


# ---------------------------------------------------------------------------
# UnifiedRegistry
# ---------------------------------------------------------------------------


class TestUnifiedRegistry:
    def test_singleton(self) -> None:
        a = get_unified_registry()
        b = get_unified_registry()
        assert a is b

    def test_register_and_get(self) -> None:
        reg = get_unified_registry()
        m = _FakeManifest(name="alpha", version="1.0.0", description="d", kind="skill")
        reg.register(m)
        assert reg.get("alpha") is m

    def test_get_missing_returns_none(self) -> None:
        reg = get_unified_registry()
        assert reg.get("nonexistent") is None

    def test_list_all_sorted(self) -> None:
        reg = get_unified_registry()
        for n in ("zebra", "apple", "mango"):
            reg.register(_FakeManifest(name=n, version="1.0.0", description="", kind="plugin"))
        names = [m.name for m in reg.list_all()]
        assert names == ["apple", "mango", "zebra"]

    def test_register_replaces_existing(self) -> None:
        reg = get_unified_registry()
        old = _FakeManifest(name="foo", version="1.0.0", description="old", kind="skill")
        new = _FakeManifest(name="foo", version="2.0.0", description="new", kind="skill")
        reg.register(old)
        reg.register(new)
        assert reg.get("foo") is new
        assert len(reg.list_all()) == 1

    def test_register_rejects_non_contract(self) -> None:
        reg = get_unified_registry()

        class Bad:
            pass

        with pytest.raises(TypeError):
            reg.register(Bad())  # type: ignore

    def test_accepts_plugin_manifest(self) -> None:
        reg = get_unified_registry()
        m = _plugin_manifest()
        reg.register(m)
        assert reg.get("my_plugin") is m

    def test_accepts_extension_manifest(self) -> None:
        from plugin_sdk.extension_manifest import ExtensionManifest

        reg = get_unified_registry()
        m = ExtensionManifest(name="my_ext", version="0.1.0", description="ext")
        reg.register(m)
        assert reg.get("my_ext") is m

    def test_unregister_removes_entry(self) -> None:
        reg = get_unified_registry()
        m = _FakeManifest(name="to_remove", version="1.0.0", description="d", kind="plugin")
        reg.register(m)
        assert reg.get("to_remove") is m
        result = reg.unregister("to_remove")
        assert result is True
        assert reg.get("to_remove") is None
        assert len(reg.list_all()) == 0

    def test_unregister_missing_returns_false(self) -> None:
        reg = get_unified_registry()
        assert reg.unregister("nonexistent") is False


# ---------------------------------------------------------------------------
# Backward-compat: old skill manifests without `kind` load without error
# ---------------------------------------------------------------------------


def _load_manifest_parser():
    """Load manifest_parser directly, bypassing the skills package and config init.

    autobot_shared.logging_manager.get_logger triggers a config→logging→config
    circular-import deadlock in test environments without a running service stack.
    We stub the module-level logger before exec_module to prevent that hang.
    """
    import importlib.util
    import logging
    import sys
    import types
    from pathlib import Path

    # Stub autobot_shared.logging_manager so get_logger returns a stdlib logger.
    _lm_stub = types.ModuleType("autobot_shared.logging_manager")
    _lm_stub.get_logger = lambda name, *a, **kw: logging.getLogger(name)
    sys.modules.setdefault("autobot_shared.logging_manager", _lm_stub)

    mp_path = Path(__file__).parent.parent.parent / "autobot-backend" / "skills" / "manifest_parser.py"
    mod_name = "_manifest_parser_isolated"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, mp_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestManifestParserBackwardCompat:
    def test_manifest_without_kind_loads_with_warning(self) -> None:
        mp = _load_manifest_parser()

        skill_md = "---\nname: my_skill\nversion: 1.0.0\ndescription: test\nentrypoint: main.py\n---\n"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = mp.parse_manifest(skill_md)
        assert result["kind"] == "skill"
        deprecation_warns = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecation_warns) == 1
        assert "kind" in str(deprecation_warns[0].message)

    def test_manifest_with_kind_no_warning(self) -> None:
        mp = _load_manifest_parser()

        skill_md = "---\nname: my_skill\nversion: 1.0.0\ndescription: test\nentrypoint: main.py\nkind: skill\n---\n"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = mp.parse_manifest(skill_md)
        assert result["kind"] == "skill"
        deprecation_warns = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(deprecation_warns) == 0
