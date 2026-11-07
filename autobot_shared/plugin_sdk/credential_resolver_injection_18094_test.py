# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PluginLoader injects a per-plugin scoped credential resolver before initialize() (#18094)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from autobot_shared.plugin_sdk.loader import PluginLoader
from autobot_shared.plugin_sdk.plugin_manager import PluginManager

_PLUGINS = Path(__file__).resolve().parents[2] / "plugins" / "core-plugins"
_NAME = "image-generation-plugin"


@pytest.fixture(autouse=True)
def _restore_sys_modules():
    """The loader installs the dotted plugin packages; leave sys.modules as found."""
    before = dict(sys.modules)
    yield
    for key in set(sys.modules) - set(before):
        del sys.modules[key]
    # canonicalise_plugin_sdk() REPLACES existing `plugin_sdk.*` entries with aliases of the
    # canonical modules; a key-set diff misses those, so put every replaced value back too.
    for key, module in before.items():
        if sys.modules.get(key) is not module:
            sys.modules[key] = module


async def _load(loader: PluginLoader, name: str):
    manifest = next(m for m in loader.discover_plugins() if m.name == name)
    return await loader.load_plugin(manifest)


@pytest.mark.asyncio
async def test_the_named_plugin_gets_its_resolver_before_initialize() -> None:
    def resolver(name: str) -> str:
        return "sentinel-via-resolver"

    loader = PluginLoader([_PLUGINS], {_NAME: resolver}, [_PLUGINS])
    plugin = await _load(loader, _NAME)
    try:
        assert plugin is not None and plugin.credential_resolver is resolver
        tool_module = next(
            m for k, m in sys.modules.items() if k.endswith("image_generation_plugin.tools.generate_image")
        )
        assert tool_module.read_provider_key("FLUX_API_KEY") == "sentinel-via-resolver"
    finally:
        if plugin is not None:
            await loader.unload_plugin(_NAME)


@pytest.mark.asyncio
async def test_a_plugin_without_a_mapping_gets_none() -> None:
    loader = PluginLoader([_PLUGINS], {"some-other-plugin": lambda name: "x"}, [_PLUGINS])
    plugin = await _load(loader, _NAME)
    try:
        assert plugin is not None and plugin.credential_resolver is None
    finally:
        if plugin is not None:
            await loader.unload_plugin(_NAME)


def test_the_manager_forwards_the_mapping_to_its_loader() -> None:
    mapping = {_NAME: lambda name: ""}
    manager = PluginManager([_PLUGINS], mapping, [_PLUGINS])
    assert manager._loader.credential_resolvers is mapping
    assert manager._loader.trusted_roots == [_PLUGINS]
    assert PluginManager([_PLUGINS])._loader.credential_resolvers == {}
