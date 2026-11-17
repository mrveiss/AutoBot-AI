# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The host reverses a plugin's hooks and grants on disable, unload and reload (#19302)."""

import asyncio
import sys
import textwrap

import pytest

from plugin_sdk.base import PluginManifest, PluginRegistry, PluginStatus
from plugin_sdk.capabilities import CapabilityChecker, PluginCapability
from plugin_sdk.hooks import HookRegistry
from plugin_sdk.loader import PluginLoader

_MODULE = """
    from plugin_sdk import BasePlugin
    from plugin_sdk.hooks import HookRegistry

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
