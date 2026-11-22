# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The host removes and gates a plugin's tools: only ENABLED plugins expose them (#19302)."""

import sys
import textwrap

import pytest

from autobot_shared.plugin_sdk.base import PluginManifest, PluginRegistry
from autobot_shared.plugin_sdk.loader import PluginLoader
from autobot_shared.tool_sdk.registry import ToolNotFoundError, get_tool_registry

_MODULE = """
    from autobot_shared.plugin_sdk import BasePlugin
    from autobot_shared.tool_sdk.base import BaseTool, ToolMetadata, ToolPermission, ToolResult
    from autobot_shared.tool_sdk.registry import get_tool_registry

    class FxTool(BaseTool):
        metadata = ToolMetadata(name="{tool}", description="fx", permission=ToolPermission.PUBLIC)
        input_schema = {{"type": "object", "properties": {{}}, "required": []}}

        async def execute(self, validated_input):
            return ToolResult(success=True, data="ran")

    class FixturePlugin(BasePlugin):
        async def initialize(self):
            get_tool_registry().register(FxTool)

        async def shutdown(self):
            pass  # deliberately does not unregister
"""


@pytest.fixture(autouse=True)
def _restore_sys_modules():
    before = dict(sys.modules)
    yield
    for key in set(sys.modules) - set(before):
        del sys.modules[key]
    for key, module in before.items():
        if sys.modules.get(key) is not module:
            sys.modules[key] = module


@pytest.fixture
def loaded(tmp_path, monkeypatch):
    name = f"fx_tool_plugin_{id(tmp_path)}"
    tool = f"{name}_tool"
    (tmp_path / f"{name}.py").write_text(textwrap.dedent(_MODULE).format(tool=tool), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    manifest = PluginManifest(
        name=name, version="1.0.0", display_name="Fx", description="fx", author="mrveiss", entry_point=name
    )
    yield PluginLoader([]), manifest, tool
    get_tool_registry().unregister_plugin(name)
    PluginRegistry().unregister(name)


def _listed(tool: str) -> bool:
    return any(m.name == tool for m in get_tool_registry().list_tools())


@pytest.mark.asyncio
async def test_unload_removes_tool_despite_empty_shutdown(loaded):
    loader, manifest, tool = loaded
    plugin = await loader.load_plugin(manifest)
    assert not _listed(tool), "a loaded plugin that is not enabled must not expose its tool"
    await plugin.enable()
    assert _listed(tool)
    assert await loader.unload_plugin(manifest.name)
    assert not _listed(tool)
    with pytest.raises(ToolNotFoundError):
        get_tool_registry().get(tool)


@pytest.mark.asyncio
async def test_disabled_plugin_tool_cannot_be_called_and_returns_on_enable(loaded):
    loader, manifest, tool = loaded
    plugin = await loader.load_plugin(manifest)
    await plugin.enable()
    registry = get_tool_registry()
    assert (await registry.execute(tool, {})).data == "ran"
    await plugin.disable()
    assert not _listed(tool)
    with pytest.raises(ToolNotFoundError):
        await registry.execute(tool, {})
    await plugin.enable()
    assert (await registry.execute(tool, {})).data == "ran"


@pytest.mark.asyncio
async def test_reload_reregisters_tool_once(loaded):
    loader, manifest, tool = loaded
    plugin = await loader.load_plugin(manifest)
    await plugin.enable()
    assert await loader.reload_plugin(manifest.name)
    assert sum(1 for m in get_tool_registry().list_tools() if m.name == tool) == 1
