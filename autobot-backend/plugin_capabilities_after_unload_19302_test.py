# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The capabilities endpoint reports no inherited grants after unload (#19302).

Drives the real loader and the real handler: grant, unload, reload the same
name, then read what the endpoint reports.
"""

import sys
import textwrap

import pytest
from fastapi import HTTPException

import plugin_manager
from autobot_shared.plugin_sdk.base import PluginManifest, PluginRegistry
from autobot_shared.plugin_sdk.capabilities import CapabilityChecker, PluginCapability
from autobot_shared.plugin_sdk.loader import PluginLoader

_MODULE = """
    from autobot_shared.plugin_sdk import BasePlugin

    class FixturePlugin(BasePlugin):
        async def initialize(self):
            pass

        async def shutdown(self):
            pass
"""


@pytest.fixture
def loader_and_manifest(tmp_path, monkeypatch):
    name = f"fx_cap_plugin_{id(tmp_path)}"
    (tmp_path / f"{name}.py").write_text(textwrap.dedent(_MODULE), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    manifest = PluginManifest(
        name=name,
        version="1.0.0",
        display_name="Fx",
        description="fx",
        author="mrveiss",
        entry_point=name,
        capabilities=[PluginCapability.NETWORK_OUTBOUND],
    )
    before = dict(sys.modules)
    yield PluginLoader([]), manifest
    CapabilityChecker().revoke_capabilities(name)
    PluginRegistry().unregister(name)
    for key in set(sys.modules) - set(before):
        del sys.modules[key]
    # canonicalise_plugin_sdk() REPLACES existing entries with aliases; put every replaced value back.
    for key, module in before.items():
        if sys.modules.get(key) is not module:
            sys.modules[key] = module


@pytest.mark.asyncio
async def test_unloaded_plugin_is_gone_and_a_reload_inherits_no_grants(loader_and_manifest):
    loader, manifest = loader_and_manifest
    await loader.load_plugin(manifest)
    CapabilityChecker().grant_capabilities(manifest.name, [PluginCapability.NETWORK_OUTBOUND])
    before = await plugin_manager.get_plugin_capabilities(manifest.name, admin_check=True)
    assert before.granted_capabilities == [PluginCapability.NETWORK_OUTBOUND.value]

    assert await loader.unload_plugin(manifest.name)
    with pytest.raises(HTTPException) as gone:
        await plugin_manager.get_plugin_capabilities(manifest.name, admin_check=True)
    assert gone.value.status_code == 404

    await loader.load_plugin(manifest)
    after = await plugin_manager.get_plugin_capabilities(manifest.name, admin_check=True)
    assert after.granted_capabilities == []
    assert after.pending_approval == [PluginCapability.NETWORK_OUTBOUND.value]
