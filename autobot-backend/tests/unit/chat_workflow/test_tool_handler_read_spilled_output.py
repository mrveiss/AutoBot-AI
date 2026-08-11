# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`read_spilled_output` at the PRODUCTION dispatch seam (#13919).

#13692 spills oversized tool output and leaves an excerpt whose note tells the
model to call `read_spilled_output`. #13754 made that tool dispatchable through
`ToolRegistry.execute_tool` — and closed on evidence from `tool_registry.py`.

But `ToolRegistry.execute_tool` has **no production callers**. Every real tool
call funnels through `_dispatch_tool_call`, which knew nothing about the tool,
so an agent obeying the note landed in `_build_unknown_tool_error` and burned
its invalid-call budget. The capability was "delivered" twice while remaining
unreachable.

These tests therefore drive `_dispatch_tool_call` — the seam the code actually
runs through — not the registry.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from chat_workflow.tool_handler import ToolHandlerMixin

_DISPATCH_ARGS = {
    "session_id": "sess-1",
    "terminal_session_id": "term-1",
    "ollama_endpoint": "http://127.0.0.1:11434",
    "selected_model": "test-model",
}


def _mixin() -> ToolHandlerMixin:
    mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)
    mixin._enforce_forbidden_work = lambda *a, **k: None
    mixin._enforce_config_protection = lambda *a, **k: None
    mixin._enforce_fact_forcing = lambda *a, **k: None
    mixin._enforce_work_item_approval = lambda *a, **k: None
    return mixin


async def _dispatch(tool_call: dict, results: list, ctx=None) -> list:
    return [
        msg
        async for msg in _mixin()._dispatch_tool_call(
            tool_call,
            execution_results=results,
            additional_response_parts=[],
            ctx=ctx,
            **_DISPATCH_ARGS,
        )
    ]


_WINDOW = {
    "found": True,
    "anchor": "autobot:spill:run-1:bash:deadbeef",
    "offset": 0,
    "limit": 2000,
    "total_chars": 40000,
    "content": "the full output, windowed",
    "has_more": True,
}


class TestTheSeamRoutesIt:
    @pytest.mark.asyncio
    async def test_a_valid_anchor_returns_the_window(self):
        results = []

        with patch("agent_loop.tool_output_spill.read_spilled_window", return_value=_WINDOW):
            msgs = await _dispatch(
                {"name": "read_spilled_output", "params": {"anchor": _WINDOW["anchor"]}},
                results,
            )

        assert results and results[0]["status"] == "success"
        assert results[0]["output"] == "the full output, windowed"
        assert any("windowed" in str(getattr(m, "content", "")) for m in msgs)

    @pytest.mark.asyncio
    async def test_it_does_not_burn_the_invalid_call_budget(self):
        """The acceptance criterion.

        An unknown tool increments `consecutive_invalid_tool_calls`; a routed
        one resets it. Before this fix, an agent following the excerpt's own
        instruction was penalised for doing so.
        """
        ctx = SimpleNamespace(consecutive_invalid_tool_calls=2, context={})
        results = []

        with patch("agent_loop.tool_output_spill.read_spilled_window", return_value=_WINDOW):
            await _dispatch(
                {"name": "read_spilled_output", "params": {"anchor": _WINDOW["anchor"]}},
                results,
                ctx=ctx,
            )

        assert ctx.consecutive_invalid_tool_calls == 0

    @pytest.mark.asyncio
    async def test_an_unknown_tool_still_increments_it(self):
        """The case that must STAY caught — a fix that resets the counter for
        everything would be worse than the bug."""
        ctx = SimpleNamespace(consecutive_invalid_tool_calls=2, context={})
        results = []

        await _dispatch({"name": "definitely_not_a_tool", "params": {}}, results, ctx=ctx)

        assert ctx.consecutive_invalid_tool_calls == 3


class TestTheModelIsToldToStopRetrying:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("window", "expected"),
        [
            ({"found": False, "anchor": "a", "reason": "no_run_bound"}, "no_run_bound"),
            ({"found": False, "anchor": "a"}, "not_found"),
        ],
        ids=["unbound-run", "missing-artifact"],
    )
    async def test_a_miss_is_reported_with_its_reason(self, window, expected):
        """An unbound run and a missing artifact need different responses, and
        neither should read as a transient failure worth retrying."""
        results = []

        with patch("agent_loop.tool_output_spill.read_spilled_window", return_value=window):
            msgs = await _dispatch({"name": "read_spilled_output", "params": {"anchor": "a"}}, results)

        assert results[0]["status"] == expected
        assert any("Do not retry" in str(getattr(m, "content", "")) for m in msgs)


class TestSchemaValidationApplies:
    @pytest.mark.asyncio
    async def test_a_call_without_an_anchor_is_rejected_before_execution(self):
        """Membership in the uniform set means the shared #4529 gate runs. A
        schema-less member would skip validation silently."""
        results = []

        with patch("agent_loop.tool_output_spill.read_spilled_window") as reader:
            await _dispatch({"name": "read_spilled_output", "params": {}}, results)

        reader.assert_not_called()
        assert results and results[0].get("schema_validation_failed") is True
