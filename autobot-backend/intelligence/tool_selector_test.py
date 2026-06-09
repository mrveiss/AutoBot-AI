# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for #7245 / #7246 — IntelligentAgent demo cascade.

Five reference-rot bugs prevented the `intelligence/` demos from running:

1. ``GoalCategory.NETWORK_DISCOVERY`` etc. — references to enum members the
   post-rename ``GoalCategory`` no longer has. Hard-failed
   ``OSAwareToolSelector.__init__`` with ``AttributeError: NETWORK_DISCOVERY``.
2. ``ProcessedGoal.parameters`` — field missing from the dataclass; every
   ``select_tool()`` call raised ``AttributeError``.
3. ``ToolSelection.warnings`` — field missing; every successful tool
   selection then crashed during chunk-build with ``AttributeError``.
4. ``ProcessedGoal.suggested_tools`` — wrong attribute name (canonical is
   ``suggested_commands``).
5. ``asyncio.wait_for(<async generator>, ...)`` — async generators aren't
   awaitable; raised "An asyncio.Future, a coroutine or an awaitable is
   required" on every command in ``StreamingCommandExecutor``.

These tests pin each bug so a future refactor that drops a field or renames
an enum surfaces in CI instead of in the demos at runtime.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

# Ensure autobot-backend is on path so bare `intelligence.*` imports resolve
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------------------------------------------------------------------------
# Bug 1: tool_selector references real GoalCategory members
# ---------------------------------------------------------------------------


def test_tool_selector_construction_does_not_raise() -> None:
    """``OSAwareToolSelector(...)`` must not raise AttributeError on init.

    Regression for #7245: original code referenced
    ``GoalCategory.NETWORK_DISCOVERY`` etc. on a post-rename enum that only
    exposes ``NETWORK`` / ``SECURITY`` / ``SYSTEM`` / ``MONITORING``.
    """
    from intelligence.goal_processor import GoalCategory
    from intelligence.tool_selector import OSAwareToolSelector

    class _StubDetector:
        pass

    sel = OSAwareToolSelector(_StubDetector())  # must not raise
    keys = {k for k in sel.tool_mappings.keys()}
    # All keys must be real GoalCategory members
    valid_categories = set(GoalCategory)
    assert keys.issubset(valid_categories), f"tool_mappings keys not in GoalCategory: {keys - valid_categories}"


def test_tool_selector_system_merge_preserves_all_intents() -> None:
    """The 3 system-related helpers merge into ``GoalCategory.SYSTEM`` —
    intent keys must be preserved (no collisions, no drops).
    """
    from intelligence.goal_processor import GoalCategory
    from intelligence.tool_selector import OSAwareToolSelector

    class _StubDetector:
        pass

    sel = OSAwareToolSelector(_StubDetector())
    system_intents = sorted(sel.tool_mappings[GoalCategory.SYSTEM].keys())
    expected = sorted(
        [
            # from _get_system_update_tools
            "system_update",
            "os_update",
            # from _get_system_info_tools
            "system_info",
            "disk_usage",
            "memory_info",
            "hardware_info",
            # from _get_process_management_tools
            "list_processes",
            "kill_process",
        ]
    )
    assert system_intents == expected, (
        f"merged SYSTEM intents differ from sum-of-helpers: "
        f"missing={set(expected) - set(system_intents)}, "
        f"extra={set(system_intents) - set(expected)}"
    )


# ---------------------------------------------------------------------------
# Bug 2: ProcessedGoal has the .parameters field
# ---------------------------------------------------------------------------


def test_processed_goal_has_parameters_field() -> None:
    """``goal.parameters`` is read by ``tool_selector._format_command``."""
    from autobot_shared.status_enums import RiskLevel
    from intelligence.goal_processor import GoalCategory, ProcessedGoal

    field_names = {f.name for f in dataclasses.fields(ProcessedGoal)}
    assert "parameters" in field_names, "#7245: ProcessedGoal.parameters required by tool_selector — missing"

    # Default must be an empty dict (not a shared mutable; not None)
    g = ProcessedGoal(
        original_goal="x",
        intent="x",
        explanation="x",
        category=GoalCategory.SYSTEM,
        confidence=0.5,
        risk_level=RiskLevel.LOW,
    )
    assert g.parameters == {}
    g2 = ProcessedGoal(
        original_goal="y",
        intent="y",
        explanation="y",
        category=GoalCategory.SYSTEM,
        confidence=0.5,
        risk_level=RiskLevel.LOW,
    )
    assert g.parameters is not g2.parameters, "parameters dict is shared between instances"


# ---------------------------------------------------------------------------
# Bug 3: ToolSelection has the .warnings field
# ---------------------------------------------------------------------------


def test_tool_selection_has_warnings_field() -> None:
    """``IntelligentAgent._build_tool_selection_chunks`` iterates
    ``tool_selection.warnings`` — field must exist + default to [].
    """
    from intelligence.tool_selector import ToolSelection

    field_names = {f.name for f in dataclasses.fields(ToolSelection)}
    assert "warnings" in field_names, "#7245: ToolSelection.warnings required by intelligent_agent — missing"

    sel = ToolSelection(
        primary_command="echo hi",
        fallback_commands=[],
        install_command=None,
        requires_install=False,
        explanation="t",
    )
    assert sel.warnings == []
    # Independent default-factory per instance
    sel2 = ToolSelection(
        primary_command="echo hi2",
        fallback_commands=[],
        install_command=None,
        requires_install=False,
        explanation="t",
    )
    assert sel.warnings is not sel2.warnings


# ---------------------------------------------------------------------------
# Bug 4: tool_selector reads goal.suggested_commands (NOT suggested_tools)
# ---------------------------------------------------------------------------


def test_tool_selector_uses_suggested_commands_not_suggested_tools() -> None:
    """Source-grep regression: tool_selector.py must not reference
    ``goal.suggested_tools`` (canonical attribute is ``suggested_commands``).
    """
    src = (_BACKEND / "intelligence" / "tool_selector.py").read_text(encoding="utf-8")
    assert "goal.suggested_tools" not in src, (
        "tool_selector.py references goal.suggested_tools — should be " "goal.suggested_commands (#7245 cascade)"
    )
    assert "goal.suggested_commands" in src, "tool_selector.py should reference goal.suggested_commands"


# ---------------------------------------------------------------------------
# Bug 5: streaming_executor uses async-for instead of wait_for(async-gen)
# ---------------------------------------------------------------------------


def test_streaming_executor_no_wait_for_on_async_generator() -> None:
    """Regression for #7246: ``asyncio.wait_for(self._stream_process_output(...))``
    raised "An asyncio.Future, a coroutine or an awaitable is required" because
    ``_stream_process_output`` is an async generator. The fix iterates via
    ``async for`` (in either an ``asyncio.timeout()`` block or a queue-based
    pattern). Source-grep regression to keep us out of that trap.
    """
    src = (_BACKEND / "intelligence" / "streaming_executor.py").read_text(encoding="utf-8")
    # The exact problematic pattern (no whitespace tolerance — the regression
    # was specifically `wait_for(self._stream_process_output(...)`).
    assert (
        "wait_for(\n                self._stream_process_output" not in src
    ), "streaming_executor.py reverted to wait_for() on _stream_process_output (#7246)"
    assert (
        "wait_for(self._stream_process_output" not in src
    ), "streaming_executor.py reverted to wait_for() on _stream_process_output (#7246)"
