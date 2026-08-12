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
from unittest.mock import AsyncMock, patch

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


class TestAgainstTheRealReader:
    """No mock. Every other test here stubs `read_spilled_window`, which only
    proves the handler forwards whatever the reader returns — the uninteresting
    half. The production question is what the reader returns *at this seam*, and
    mocking it hides the answer.

    It returns `no_run_bound`, always: `bind_task` is called only from
    `agent_loop/loop.py`, and `AgentLoop` is documented as never instantiated in
    production. Pinned here so the day the chat seam starts binding a run, this
    test changes and says so.
    """

    @pytest.mark.asyncio
    async def test_an_unbound_chat_turn_cannot_read_anything(self):
        from agent_loop import tool_output_spill as spill

        spill.bind_task(None)  # the state a real chat turn is in
        results = []

        msgs = await _dispatch(
            {"name": "read_spilled_output", "params": {"anchor": "autobot:spill:r:bash:deadbeef"}},
            results,
        )

        assert results[0]["status"] == "no_run_bound", (
            "if this now returns something else, the chat seam has started binding a run — "
            "update #13919's remaining scope"
        )
        assert any("Do not retry" in str(getattr(m, "content", "")) for m in msgs)


class TestTheNoteAndTheDispatchKeyCannotDrift:
    def test_the_tool_named_in_the_spill_excerpt_is_dispatchable(self):
        """The literal in the excerpt note and the dispatch key are asserted
        independently in two suites, so renaming one leaves both green while the
        note points at nothing. That drift is exactly how this issue was closed
        falsely twice. This ties them together."""
        import re

        from agent_loop.tool_output_spill import _excerpt_payload
        from chat_workflow.tool_handler import _UNIFORM_BUILTIN_TOOLS

        note = _excerpt_payload("autobot:spill:r:bash:d", "bash", "x" * 100)["note"]
        named = re.search(r"Read the full output with the (\w+) tool", note)

        assert named, f"the excerpt note no longer names a tool: {note!r}"
        assert named.group(1) in _UNIFORM_BUILTIN_TOOLS, (
            f"the note tells the model to call {named.group(1)!r}, " "which the production dispatch seam cannot route"
        )


class TestTheModelIsToldToStopRetrying:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("window", "expected"),
        [
            ({"found": False, "anchor": "a", "reason": "no_run_bound"}, "no_run_bound"),
            ({"found": False, "anchor": "a", "reason": "not_found"}, "not_found"),
            # Note: `invalid_window` cannot be produced by a production dispatch
            # — the schema types offset/limit as "integer" and the shared #4529
            # gate rejects anything else before this handler runs. It is kept as
            # defence-in-depth (validate_tool_arguments returns None if the
            # jsonschema import fails), so this case documents the branch rather
            # than covering a live path.
            ({"found": False, "anchor": "a", "reason": "invalid_window"}, "invalid_window"),
        ],
        ids=["unbound-run", "missing-artifact", "bad-arguments-defence-in-depth"],
    )
    async def test_a_miss_is_reported_with_its_reason(self, window, expected):
        """An unbound run and a missing artifact need different responses, and
        neither should read as a transient failure worth retrying."""
        results = []

        with patch("agent_loop.tool_output_spill.read_spilled_window", return_value=window):
            msgs = await _dispatch({"name": "read_spilled_output", "params": {"anchor": "a"}}, results)

        assert results[0]["status"] == expected
        content = " ".join(str(getattr(m, "content", "")) for m in msgs)
        if expected == "invalid_window":
            # Self-correctable: telling the model to abandon the anchor over a
            # bad integer would lose recoverable output.
            assert "Retry this anchor" in content
        else:
            assert "Do not retry" in content

    @pytest.mark.asyncio
    async def test_a_miss_with_no_stated_reason_is_not_declared_permanent(self):
        """#13991 review: the default used to be "Do not retry this anchor."

        ``read_spilled`` swallows every exception into ``None``, and a cross-run
        refusal returns ``None`` too — so a reasonless miss covers a truncated
        artifact caught mid-write, a transient OSError, a PermissionError and a
        run-scope refusal. In all four the output is still on disk. Issuing a
        permanent verdict on a cause nobody established is the exact defect this
        seam exists to stop reproducing.
        """
        results = []
        window = {"found": False, "anchor": "a"}  # no "reason" key at all

        with patch("agent_loop.tool_output_spill.read_spilled_window", return_value=window):
            msgs = await _dispatch({"name": "read_spilled_output", "params": {"anchor": "a"}}, results)

        assert results[0]["status"] == "unknown", "a reasonless miss must not be labelled not_found"
        content = " ".join(str(getattr(m, "content", "")) for m in msgs)
        assert "Do not retry" not in content
        assert "transient" in content


class TestTheArtifactIsReadOffTheEventLoop:
    """#13991 review: ``read_spilled_window`` reads and json-parses the WHOLE
    artifact — up to ``SPILL_MAX_ARTIFACT_CHARS``, 5,000,000 — before slicing out
    at most 8,000 chars. Called inline it stalls every other coroutine in the
    process once per page, and paging a 5 MB artifact at the window cap is 625
    such calls. CLAUDE.md: never add sync calls to async paths. The write side
    already took this decision — ``spill_results_async`` exists for the same
    reason.
    """

    @pytest.mark.asyncio
    async def test_the_reader_is_handed_to_a_thread_not_awaited_inline(self):
        from agent_loop.tool_output_spill import read_spilled_window

        results = []
        window = {"found": True, "anchor": "a", "content": "x", "offset": 0, "has_more": False, "total_chars": 1}

        # Only to_thread is patched, so the first argument is the real function
        # object — identity, not a name string a rename would leave passing.
        with patch("asyncio.to_thread", new=AsyncMock(return_value=window)) as to_thread:
            await _dispatch({"name": "read_spilled_output", "params": {"anchor": "a"}}, results)

        to_thread.assert_awaited_once()
        assert to_thread.await_args.args[0] is read_spilled_window
        assert results[0]["status"] == "success"


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
