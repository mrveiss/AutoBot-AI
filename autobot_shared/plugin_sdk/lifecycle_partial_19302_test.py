# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failed load, a raising shutdown() and an unnamed or foreign registration leave nothing behind (#19302)."""

import sys
import textwrap

import pytest

from autobot_shared.plugin_sdk import loader as loader_module
from autobot_shared.plugin_sdk.base import PluginManifest, PluginRegistry
from autobot_shared.plugin_sdk.hooks import HookRegistry, is_plugin_active
from autobot_shared.plugin_sdk.lifecycle import enable_attributed
from autobot_shared.plugin_sdk.loader import PluginLoader
from autobot_shared.plugin_sdk.registry import get_registry
from autobot_shared.tool_sdk.registry import get_tool_registry

_MODULE = """
    from autobot_shared.plugin_sdk import BasePlugin
    from autobot_shared.plugin_sdk.hooks import HookRegistry
    from autobot_shared.tool_sdk.base import BaseTool, ToolMetadata, ToolPermission, ToolResult
    from autobot_shared.tool_sdk.registry import get_tool_registry

    class PartTool(BaseTool):
        metadata = ToolMetadata(name="{name}_tool", description="fx", permission=ToolPermission.PUBLIC)
        input_schema = {{"type": "object", "properties": {{}}, "required": []}}

        async def execute(self, validated_input):
            return ToolResult(success=True, data="ran")

    class P(BasePlugin):
        async def initialize(self):
            {initialize}

        async def enable(self):
            await super().enable()
            {enable}

        async def shutdown(self):
            {shutdown}
"""
_HOOK = 'HookRegistry().register_hook("part_hook", lambda: 1, {who})'


@pytest.fixture(autouse=True)
def _restore_sys_modules():
    before = dict(sys.modules)
    yield
    for key in set(sys.modules) - set(before):
        del sys.modules[key]
    # canonicalise_plugin_sdk() REPLACES existing entries with aliases; put every replaced value back.
    for key, module in before.items():
        if sys.modules.get(key) is not module:
            sys.modules[key] = module


def _plugin(tmp_path, monkeypatch, *, initialize="pass", enable="pass", shutdown="pass"):
    name = f"part_plugin_{id(tmp_path)}"
    code = textwrap.dedent(_MODULE).format(name=name, initialize=initialize, enable=enable, shutdown=shutdown)
    (tmp_path / f"{name}.py").write_text(code, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    manifest = PluginManifest(
        name=name, version="1.0.0", display_name="P", description="p", author="mrveiss", entry_point=name
    )
    return PluginLoader([]), manifest


@pytest.fixture(autouse=True)
def _clean():
    yield
    HookRegistry().unregister_hook("part_hook")


@pytest.mark.asyncio
async def test_a_raising_initialize_leaves_no_hook_or_tool(tmp_path, monkeypatch):
    init = (
        _HOOK.format(who="None")
        + '\n        get_tool_registry().register(PartTool)\n        raise RuntimeError("boom")'
    )
    loader, manifest = _plugin(tmp_path, monkeypatch, initialize=init)
    assert await loader.load_plugin(manifest) is None
    assert HookRegistry().get_hook_count("part_hook") == 0
    assert not any(m.name == f"{manifest.name}_tool" for m in get_tool_registry().list_tools())


@pytest.mark.asyncio
async def test_a_raising_shutdown_still_reverses_registrations(tmp_path, monkeypatch):
    init = _HOOK.format(who="None") + "\n        get_tool_registry().register(PartTool)"
    loader, manifest = _plugin(tmp_path, monkeypatch, initialize=init, shutdown='raise RuntimeError("boom")')
    plugin = await loader.load_plugin(manifest)
    await plugin.enable()
    assert not await loader.unload_plugin(manifest.name)
    assert HookRegistry().get_hook_count("part_hook") == 0
    assert not any(m.name == f"{manifest.name}_tool" for m in get_tool_registry().list_tools())
    assert PluginRegistry().get_plugin(manifest.name) is None, "a raising shutdown() must not strand the plugin"
    assert get_registry().get(manifest.name) is None


@pytest.mark.asyncio
async def test_an_unnamed_hook_is_attributed_to_its_plugin(tmp_path, monkeypatch):
    loader, manifest = _plugin(tmp_path, monkeypatch, initialize=_HOOK.format(who="None"))
    plugin = await loader.load_plugin(manifest)
    await plugin.enable()
    assert await HookRegistry().call_hook("part_hook") == [1]
    await plugin.disable()
    assert await HookRegistry().call_hook("part_hook") == [], "attributed, so a disabled plugin's hook is silenced"
    assert not is_plugin_active(manifest.name)
    await loader.unload_plugin(manifest.name)


@pytest.mark.asyncio
async def test_a_hook_under_another_plugins_name_fails_the_load(tmp_path, monkeypatch):
    loader, manifest = _plugin(tmp_path, monkeypatch, initialize=_HOOK.format(who='"some_other_plugin"'))
    assert await loader.load_plugin(manifest) is None
    assert HookRegistry().get_hook_count("part_hook") == 0


@pytest.mark.asyncio
async def test_a_tool_registered_from_enable_is_attributed_and_reversed(tmp_path, monkeypatch):
    loader, manifest = _plugin(tmp_path, monkeypatch, enable="get_tool_registry().register(PartTool)")
    plugin = await loader.load_plugin(manifest)
    await enable_attributed(plugin)
    assert any(m.name == f"{manifest.name}_tool" for m in get_tool_registry().list_tools())
    assert await loader.unload_plugin(manifest.name)
    assert not any(m.name == f"{manifest.name}_tool" for m in get_tool_registry().list_tools())


@pytest.mark.asyncio
async def test_a_failing_unified_registration_leaves_nothing_half_registered(tmp_path, monkeypatch):
    init = _HOOK.format(who="None")
    loader, manifest = _plugin(tmp_path, monkeypatch, initialize=init)

    class RefusingRegistry:
        def register(self, manifest):
            raise ValueError("already registered")

        def unregister(self, name):
            return False

    monkeypatch.setattr(loader_module, "get_registry", lambda: RefusingRegistry())
    assert await loader.load_plugin(manifest) is None
    assert PluginRegistry().get_plugin(manifest.name) is None
    assert HookRegistry().get_hook_count("part_hook") == 0
