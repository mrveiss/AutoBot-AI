# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``on_agent_execute`` and ``on_tool_call`` each have one contract: the real caller, the declaration and the real subscriber agree (#20888)."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from autobot_shared.plugin_sdk import Hook, HookRegistry
from autobot_shared.plugin_sdk.base import PluginManifest
from autobot_shared.plugin_sdk.hooks import HOOK_REGISTRY
from chat_workflow import graph_hooks
from chat_workflow.graph_hooks import _emit_agent_execute_hook
from chat_workflow.graph_tool_dispatch import emit_tool_call_hook

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


@pytest.mark.asyncio
async def test_on_tool_call_reaches_the_real_logger_plugin_once_per_call(registry, tmp_path):
    log_file = tmp_path / "events.log"
    await _load_logger_plugin(log_file).initialize()

    await emit_tool_call_hook("session-1", [{"name": "ls", "params": {"path": "/"}}, {"name": "cat", "params": {}}])

    calls = [e for e in _entries(log_file) if e["event"] == "tool_call"]
    assert [c["tool_name"] for c in calls] == ["ls", "cat"], "the plugin saw no tool_call: a contract mismatch"
    assert calls[0]["data"] == {"args": {"path": "/"}, "session_id": "session-1"}


@pytest.mark.asyncio
async def test_the_tool_call_caller_passes_exactly_what_the_declaration_names(registry):
    seen = {}

    async def capture(**kwargs):
        seen.update(kwargs)

    registry.register_hook(Hook.ON_TOOL_CALL.value, capture, plugin_name="probe")

    await emit_tool_call_hook("session-1", [{"name": "ls", "params": {}}])

    assert set(seen) == set(HOOK_REGISTRY[Hook.ON_TOOL_CALL.value].params)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hook, emit",
    [
        ("ON_AGENT_ERROR", lambda: graph_hooks._emit_planned_agent_error_hooks("s", 1, ValueError("x"))),
        ("ON_AGENT_COMPLETE", lambda: graph_hooks._emit_planned_agent_complete_hook("s", 1, "done")),
        ("ON_AGENT_EXECUTE", lambda: graph_hooks._emit_agent_execute_hook("s", 1)),
    ],
)
async def test_a_failing_lifecycle_hook_is_logged_at_warning_with_its_name(monkeypatch, hook, emit):
    """#20888 AC4: no lifecycle hook failure is debug-only; the registry itself names the failing plugin."""
    records = []
    monkeypatch.setattr(graph_hooks.logger, "warning", lambda *a, **k: records.append(a))

    async def boom(self, *a, **k):
        raise RuntimeError("registry down")

    monkeypatch.setattr(HookRegistry, "call_hook", boom)

    await emit()

    assert len(records) == 1 and hook in records[0][0]
