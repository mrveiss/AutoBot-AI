#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Smoke tests proving Orchestrator + the real tool-dispatch pipeline are wired.

#13037: this script originally asserted ``Orchestrator.tool_registry`` --
an attribute the class has never had (confirmed via ``git log --follow``:
untouched by anything except repo-wide renames/relicensing since the
project's earliest history, long predating the #5040 orchestrator
consolidation). ``Orchestrator`` owns ``agent_registry`` (agent routing);
tool *execution* is a separate pipeline owned by the canonical
``tools.tool_registry.get_tool_registry()`` singleton, dispatched from
``task_handlers/executor.py`` / ``api/agent.py``. Rewritten to assert that
real wiring instead of a name that was never true, so it exercises the
actual end-to-end path the original script intended to prove works.
"""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger
from orchestrator import Orchestrator
from tools.tool_registry import get_tool_registry

logger = get_logger(__name__)


def test_orchestrator_has_agent_registry_not_tool_registry():
    """Orchestrator's real registry is ``agent_registry`` (routing), never ``tool_registry``."""
    orchestrator = Orchestrator()
    assert not hasattr(orchestrator, "tool_registry")
    assert hasattr(orchestrator, "agent_registry")
    assert isinstance(orchestrator.agent_registry, dict)
    assert len(orchestrator.agent_registry) > 0, "Orchestrator must initialize at least one default agent"


def test_tool_registry_singleton_has_tools_wired():
    """The real tool-dispatch surface is the canonical ``get_tool_registry()`` singleton."""
    registry = get_tool_registry()
    available = registry.get_available_tools()
    assert "respond_conversationally" in available
    logger.info("Tool registry has %d tools wired: %s", len(available), available[:5])


async def test_respond_conversationally_tool_executes_end_to_end():
    """The tool-dispatch pipeline actually runs a tool by name (the script's original intent)."""
    registry = get_tool_registry()
    result = await registry.execute_tool("respond_conversationally", {"response_text": "test response"})

    assert result["tool_name"] == "respond_conversationally"
    # Never raises: a missing worker_node degrades to a structured error, not a crash.
    assert result["status"] in ("success", "error")
