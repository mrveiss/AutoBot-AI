# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``on_agent_execute`` has one contract: the real caller, the declaration and the real subscriber agree (#20888)."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from autobot_shared.plugin_sdk import Hook, HookRegistry
from autobot_shared.plugin_sdk.base import PluginManifest
from autobot_shared.plugin_sdk.hooks import HOOK_REGISTRY
from chat_workflow.graph_hooks import _emit_agent_execute_hook

_LOGGER_PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "core-plugins" / "logger-plugin" / "main.py"


def _load_logger_plugin(log_file: Path):
    """The real logger plugin, loaded by path (it is not on sys.path as a package)."""
    spec = importlib.util.spec_from_file_location("logger_plugin_main_20888", _LOGGER_PLUGIN)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    manifest = PluginManifest(
        name="logger-plugin",
        version="1.0.0",
        display_name="Logger",
        description="d",
        author="mrveiss",
        entry_point="main",
    )
    return module.LoggerPlugin(manifest, {"log_file": str(log_file)})


def _entries(log_file: Path) -> list:
    return [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def registry():
    hooks = HookRegistry()
    hooks.clear()
    yield hooks
    hooks.clear()
    sys.modules.pop("logger_plugin_main_20888", None)


@pytest.mark.asyncio
async def test_the_real_caller_reaches_the_real_logger_plugin(registry, tmp_path):
    log_file = tmp_path / "events.log"
    plugin = _load_logger_plugin(log_file)
    await plugin.initialize()

    await _emit_agent_execute_hook("session-1", 3)

    executed = [e for e in _entries(log_file) if e["event"] == "agent_execute"]
    assert len(executed) == 1, "the plugin wrote no agent_execute entry: the call failed on a contract mismatch"
    assert executed[0]["agent_name"] == "chat_workflow"
    assert executed[0]["data"] == {"session_id": "session-1", "iteration": 3}


@pytest.mark.asyncio
async def test_the_caller_passes_exactly_what_the_declaration_names(registry):
    seen = {}

    async def capture(**kwargs):
        seen.update(kwargs)

    registry.register_hook(Hook.ON_AGENT_EXECUTE.value, capture, plugin_name="probe")

    await _emit_agent_execute_hook("session-1", 1)

    assert set(seen) == set(HOOK_REGISTRY[Hook.ON_AGENT_EXECUTE.value].params)
