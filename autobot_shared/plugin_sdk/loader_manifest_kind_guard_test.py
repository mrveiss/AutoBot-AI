# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Manifest `kind` vs class guard (#14280).

`telemetry-prompt-middleware` shipped a `plugin.json` (the field's default
`kind` is `"plugin"`) next to a class that subclassed
`middleware.base.Extension`, not `autobot_shared.plugin_sdk.base.BasePlugin`.
`ON_FULL_PROMPT_READY` — the hook the class implements — is dispatched
exclusively by `middleware.manager.ExtensionManager`; the plugin system's own
`HOOK_REGISTRY` does not even define it. `PluginLoader` discovered the
manifest, could not find a `BasePlugin` subclass in the imported module,
logged "No plugin class found in module", and moved on — silently, with no
test ever exercising the real loader against the real manifest. The
middleware never ran.

This file is the reusable half of the fix: `PluginLoader.discover_plugins`
now skips any manifest whose `kind` is not `"plugin"` (extensions and skills
are not this loader's territory), and every manifest that DOES claim
`kind="plugin"` — including every one shipped in `plugins/core-plugins/`
today — must actually resolve to a `BasePlugin` subclass. A future manifest
that regresses either direction (claims `"plugin"` while shipping a
non-`BasePlugin` class, or ships an `"extension"`/`"skill"` manifest that the
loader still tries to import) fails one of the tests below.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from autobot_shared.plugin_sdk.base import BasePlugin
from autobot_shared.plugin_sdk.loader import PluginLoader

_BASEPLUGIN_SOURCE = """
from plugin_sdk.base import BasePlugin


class FixturePlugin(BasePlugin):
    async def initialize(self):
        return None

    async def shutdown(self):
        return None
"""

# Mirrors the ORIGINAL telemetry-prompt-middleware defect: a manifest that
# claims (by omission — the field default) to be a plugin, next to a class
# that only satisfies the EXTENSION contract.
_EXTENSION_ONLY_SOURCE = """
class FixtureExtension:
    name = "fixture_extension"
    priority = 100

    async def on_full_prompt_ready(self, ctx):
        return None
"""

_MANIFEST = """{{
  "name": "{name}",
  "version": "1.0.0",
  "display_name": "{name}",
  "description": "kind-guard fixture",
  "author": "test"{kind_line},
  "entry_point": "plugins.core_plugins.{mod}.main"
}}"""


@pytest.fixture(autouse=True)
def _fresh_plugin_modules():
    """Drop cached fixture modules between tests (mirrors plugin_load_visibility_test.py)."""
    before = set(sys.modules)
    yield
    for name in set(sys.modules) - before:
        if name.startswith("plugins"):
            sys.modules.pop(name, None)


def _make_plugin(root: Path, name: str, *, kind: str | None = None, source: str = _BASEPLUGIN_SOURCE) -> Path:
    plugin_dir = root / "core-plugins" / name
    plugin_dir.mkdir(parents=True)
    kind_line = f',\n  "kind": "{kind}"' if kind is not None else ""
    mod = name.replace("-", "_")
    (plugin_dir / "plugin.json").write_text(
        _MANIFEST.format(name=name, kind_line=kind_line, mod=mod),
        encoding="utf-8",
    )
    (plugin_dir / "main.py").write_text(source, encoding="utf-8")
    return plugin_dir


class TestDiscoveryIsKindAware:
    """`discover_plugins` must only hand this loader manifests it owns."""

    def test_default_kind_plugin_is_discovered(self, tmp_path):
        _make_plugin(tmp_path, "kind-omitted-demo")
        loader = PluginLoader(plugin_dirs=[tmp_path])

        manifests = loader.discover_plugins()

        assert [m.name for m in manifests] == ["kind-omitted-demo"]

    def test_explicit_kind_plugin_is_discovered(self, tmp_path):
        _make_plugin(tmp_path, "kind-plugin-demo", kind="plugin")
        loader = PluginLoader(plugin_dirs=[tmp_path])

        manifests = loader.discover_plugins()

        assert [m.name for m in manifests] == ["kind-plugin-demo"]

    def test_kind_extension_is_skipped(self, tmp_path):
        """The shape of the original bug: this manifest must never reach
        `load_plugin`, which would only ever log "No plugin class found"."""
        _make_plugin(tmp_path, "kind-extension-demo", kind="extension", source=_EXTENSION_ONLY_SOURCE)
        loader = PluginLoader(plugin_dirs=[tmp_path])

        manifests = loader.discover_plugins()

        assert manifests == []
        assert "kind-extension-demo" not in loader._manifest_dirs

    def test_kind_skill_is_skipped(self, tmp_path):
        _make_plugin(tmp_path, "kind-skill-demo", kind="skill")
        loader = PluginLoader(plugin_dirs=[tmp_path])

        manifests = loader.discover_plugins()

        assert manifests == []


class TestAPluginKindManifestMustActuallyYieldABasePlugin:
    """A manifest that DOES claim `kind="plugin"` is not exempt from the class check.

    `kind` fixes the "wrong loader" half of the bug; it does not replace the
    "wrong class" check — a manifest can still lie.
    """

    def test_a_genuine_baseplugin_class_resolves(self, tmp_path):
        plugin_dir = _make_plugin(tmp_path, "kind-plugin-good", source=_BASEPLUGIN_SOURCE)
        loader = PluginLoader(plugin_dirs=[tmp_path])
        manifests = loader.discover_plugins()
        assert len(manifests) == 1

        cls = loader._import_plugin_class(manifests[0].entry_point, plugin_dir)

        assert cls is not None
        assert issubclass(cls, BasePlugin)

    def test_an_extension_only_class_under_a_default_plugin_kind_manifest_resolves_to_none(self, tmp_path):
        """Reproduces the original telemetry-prompt-middleware defect exactly:
        `kind` defaults to "plugin", the module ships an Extension-shaped
        class, and the loader must report "no plugin class found" (None) —
        never silently accept it as a plugin."""
        plugin_dir = _make_plugin(tmp_path, "kind-plugin-liar", source=_EXTENSION_ONLY_SOURCE)
        loader = PluginLoader(plugin_dirs=[tmp_path])
        manifests = loader.discover_plugins()
        assert len(manifests) == 1

        cls = loader._import_plugin_class(manifests[0].entry_point, plugin_dir)

        assert cls is None


class TestTheShippedTelemetryManifestNoLongerClaimsToBeAPlugin:
    """The manifest that motivated this guard (#14280)."""

    def _plugins_root(self) -> Path:
        repo_root = Path(__file__).resolve().parents[2]
        return repo_root / "plugins"

    def test_the_shipped_manifest_declares_kind_extension(self):
        import json

        manifest_path = (
            self._plugins_root() / "core-plugins" / "telemetry-prompt-middleware" / "plugin.json"
        )
        if not manifest_path.is_file():
            pytest.skip("telemetry-prompt-middleware manifest not present")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data.get("kind") == "extension"

    def test_the_real_plugin_loader_skips_it(self):
        plugins_root = self._plugins_root()
        if not (plugins_root / "core-plugins" / "telemetry-prompt-middleware").is_dir():
            pytest.skip("telemetry-prompt-middleware directory not present")

        loader = PluginLoader(plugin_dirs=[plugins_root])
        manifests = loader.discover_plugins()

        names = [m.name for m in manifests]
        assert "telemetry-prompt-middleware" not in names


class TestEveryShippedPluginKindManifestResolvesABasePlugin:
    """The generic, forward-looking sweep: whatever ships under
    `plugins/core-plugins/**/plugin.json` claiming `kind="plugin"` must
    actually resolve to a `BasePlugin` subclass through the real loader —
    the exact check that would have caught #14280 before it shipped.
    """

    def test_every_plugin_kind_manifest_yields_a_baseplugin_class(self):
        repo_root = Path(__file__).resolve().parents[2]
        plugins_root = repo_root / "plugins"
        if not (plugins_root / "core-plugins").is_dir():
            pytest.skip("core-plugins tree not present")

        loader = PluginLoader(plugin_dirs=[plugins_root])
        manifests = loader.discover_plugins()
        assert manifests, "expected at least one real core plugin to be discovered"

        failures = []
        for manifest in manifests:
            plugin_dir = loader._manifest_dirs[manifest.name]
            saved = {k: sys.modules.get(k) for k in list(sys.modules) if k.startswith("plugins")}
            try:
                cls = loader._import_plugin_class(manifest.entry_point, plugin_dir)
                if cls is None or not issubclass(cls, BasePlugin):
                    failures.append(manifest.name)
            finally:
                for key in [k for k in sys.modules if k.startswith("plugins")]:
                    sys.modules.pop(key, None)
                sys.modules.update(saved)

        assert not failures, f"manifest(s) claim kind='plugin' but no BasePlugin class was found: {failures}"
