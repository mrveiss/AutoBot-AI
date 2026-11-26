# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The host reverses a plugin's hooks and grants on disable, unload and reload (#19302)."""

import asyncio
import sys
import textwrap

import pytest

from autobot_shared.plugin_sdk.base import PluginManifest, PluginRegistry, PluginStatus
from autobot_shared.plugin_sdk.capabilities import CapabilityChecker, PluginCapability
from autobot_shared.plugin_sdk.hooks import HookRegistry
from autobot_shared.plugin_sdk.loader import PluginLoader

_MODULE = """
    from autobot_shared.plugin_sdk import BasePlugin
    from autobot_shared.plugin_sdk.hooks import HookRegistry

    FIRED = []

    class FixturePlugin(BasePlugin):
        async def initialize(self):
            HookRegistry().register_hook("fx_hook", self.on_fire, self.manifest.name)

        async def shutdown(self):
            pass  # deliberately does not unregister

        def on_fire(self):
            FIRED.append("{marker}")
            return "{marker}"
"""


@pytest.fixture(autouse=True)
def _restore_sys_modules():
    """The loader installs dotted plugin packages and `plugin_sdk` aliases; leave sys.modules as found."""
    before = dict(sys.modules)
    yield
    for key in set(sys.modules) - set(before):
        del sys.modules[key]
    # canonicalise_plugin_sdk() REPLACES existing entries with aliases; put every replaced value back.
    for key, module in before.items():
        if sys.modules.get(key) is not module:
            sys.modules[key] = module


@pytest.fixture
def loader_and_manifest(tmp_path, monkeypatch):
    name = f"fx_plugin_{id(tmp_path)}"
    mod = tmp_path / f"{name}.py"
    mod.write_text(textwrap.dedent(_MODULE).replace("{marker}", "v1"), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    manifest = PluginManifest(
        name=name, version="1.0.0", display_name="Fx", description="fx", author="mrveiss", entry_point=name
    )
    yield PluginLoader([]), manifest, mod
    HookRegistry().unregister_plugin(name)
    CapabilityChecker().revoke_capabilities(name)
    PluginRegistry().unregister(name)
    sys.modules.pop(name, None)


async def _fire() -> list:
    return await HookRegistry().call_hook("fx_hook")


@pytest.mark.asyncio
async def test_disabled_plugin_hook_is_not_called(loader_and_manifest):
    loader, manifest, _ = loader_and_manifest
    plugin = await loader.load_plugin(manifest)
    assert await _fire() == [], "a loaded plugin that was never enabled does not fire (#19302 AC1)"
    await plugin.enable()
    assert await _fire() == ["v1"]
    await plugin.disable()
    assert plugin.status == PluginStatus.DISABLED
    assert await _fire() == []


@pytest.mark.asyncio
async def test_unload_removes_hooks_and_grants_despite_empty_shutdown(loader_and_manifest):
    loader, manifest, _ = loader_and_manifest
    await loader.load_plugin(manifest)
    CapabilityChecker().grant_capabilities(manifest.name, [PluginCapability.NETWORK_OUTBOUND])
    assert await loader.unload_plugin(manifest.name)
    assert HookRegistry().get_hook_count("fx_hook") == 0
    assert CapabilityChecker().get_granted_capabilities(manifest.name) == []


@pytest.mark.asyncio
async def test_unload_then_load_fires_each_hook_once(loader_and_manifest):
    loader, manifest, _ = loader_and_manifest
    plugin = await loader.load_plugin(manifest)
    await loader.unload_plugin(manifest.name)
    plugin = await loader.load_plugin(manifest)
    await plugin.enable()
    assert await _fire() == ["v1"]


@pytest.mark.asyncio
async def test_reload_runs_changed_code_and_keeps_grants(loader_and_manifest):
    loader, manifest, mod = loader_and_manifest
    plugin = await loader.load_plugin(manifest)
    await plugin.enable()
    CapabilityChecker().grant_capabilities(manifest.name, [PluginCapability.NETWORK_OUTBOUND])
    await asyncio.to_thread(mod.write_text, textwrap.dedent(_MODULE).replace("{marker}", "v2"), encoding="utf-8")
    assert await loader.reload_plugin(manifest.name)
    assert await _fire() == ["v2"]
    assert CapabilityChecker().get_granted_capabilities(manifest.name) == [PluginCapability.NETWORK_OUTBOUND]
    assert PluginRegistry().get_plugin(manifest.name).status == PluginStatus.ENABLED


@pytest.mark.asyncio
async def test_failed_reload_keeps_the_old_module_importable(loader_and_manifest):
    loader, manifest, mod = loader_and_manifest
    await loader.load_plugin(manifest)
    old = sys.modules[manifest.entry_point]
    await asyncio.to_thread(mod.write_text, "raise RuntimeError('broken')\n", encoding="utf-8")
    assert not await loader.reload_plugin(manifest.name)
    assert sys.modules[manifest.entry_point] is old
