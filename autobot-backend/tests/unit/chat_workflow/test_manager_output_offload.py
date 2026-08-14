# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tool-output offload at the CHAT seam (#13997).

#13692 built the spill and wired it only into `AgentLoop`, whose own docstring
says it is **never instantiated in production**. So on the live path it never
fired, and `read_spilled_output` — wired at the dispatch seam by #13919 — could
never resolve an anchor, because no anchor was ever created and no run was ever
bound. The capability was complete on paper and unreachable in fact.

These tests use the **real** spill module against a real temp directory. Mocking
it is what let the unreachability survive: a mocked reader proves the handler
forwards what it is given, which was never the question.
"""

import os
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from agent_loop import tool_output_spill as spill
from chat_workflow.manager import ChatWorkflowManager

_BIG = "K" * 40_000


@pytest.fixture(autouse=True)
def _spill_on(tmp_path, monkeypatch):
    monkeypatch.setattr(spill, "SPILL_ENABLED", True)
    monkeypatch.setenv("AUTOBOT_TOOL_OUTPUT_SPILL_ROOT", str(tmp_path))
    spill.bind_task(None)
    yield
    spill.bind_task(None)


def _manager() -> ChatWorkflowManager:
    return ChatWorkflowManager.__new__(ChatWorkflowManager)


def _summary(results: List[Dict[str, Any]]) -> MagicMock:
    msg = MagicMock()
    msg.type = "execution_summary"
    msg.metadata = {"execution_results": results}
    return msg


def _drain(mgr, results):
    """Run one execution-summary through the seam; return what reached history."""
    new_results: List[Dict[str, Any]] = []
    history: List[Dict[str, Any]] = []
    handled = mgr._handle_execution_summary(_summary(results), new_results, history)
    assert handled is True
    return history


class TestTheChatSeamActuallyOffloads:
    def test_an_oversized_result_is_replaced_by_an_excerpt_and_anchor(self):
        mgr = _manager()
        mgr._bind_spill_run("sess-1")

        history = _drain(mgr, [{"tool": "execute_command", "status": "success", "output": _BIG}])

        assert len(history[0]["output"]) < len(_BIG)
        assert "autobot:spill:sess-1:" in history[0]["anchor"]
        assert "read_spilled_output" in history[0]["output"], "the note must reach the model"

    def test_the_full_output_is_retrievable_through_the_anchor(self):
        """Non-lossy is the whole point. Today's per-tool truncation discards the
        remainder permanently."""
        mgr = _manager()
        mgr._bind_spill_run("sess-1")

        history = _drain(mgr, [{"tool": "execute_command", "status": "success", "output": _BIG}])
        window = spill.read_spilled_window(history[0]["anchor"])

        assert window["found"] is True
        assert window["total_chars"] == len(_BIG)

    def test_the_envelope_survives(self):
        """`status` decides error handling downstream — tool_handler counts
        `== "success"`, delegation checks `== "error"`. Replacing the whole dict
        with an excerpt would drop it."""
        mgr = _manager()
        mgr._bind_spill_run("sess-1")

        history = _drain(mgr, [{"tool": "execute_command", "status": "error", "output": _BIG}])

        assert history[0]["status"] == "error"
        assert history[0]["tool"] == "execute_command"

    def test_output_stays_a_string(self):
        """`_as_output_text` and `tool_handler` read it as one."""
        mgr = _manager()
        mgr._bind_spill_run("sess-1")

        history = _drain(mgr, [{"tool": "execute_command", "status": "success", "output": _BIG}])

        assert isinstance(history[0]["output"], str)

    def test_small_results_pass_through_untouched(self):
        mgr = _manager()
        mgr._bind_spill_run("sess-1")
        original = [{"tool": "web_search", "status": "success", "output": "short"}]

        history = _drain(mgr, original)

        assert history == original


class TestTheRunBinding:
    """#13919's last unticked box. Without a bound run the read tool returns
    `no_run_bound` on every call, which is what it did on this path."""

    def test_an_anchor_written_here_is_readable_here(self):
        mgr = _manager()
        mgr._bind_spill_run("sess-1")

        history = _drain(mgr, [{"tool": "execute_command", "status": "success", "output": _BIG}])

        assert spill.read_spilled_window(history[0]["anchor"])["found"] is True

    def test_another_conversation_cannot_read_it(self):
        """The anchor carries its session in plaintext, so scoping has to be
        enforced server-side rather than by the caller."""
        mgr = _manager()
        mgr._bind_spill_run("sess-1")
        history = _drain(mgr, [{"tool": "execute_command", "status": "success", "output": _BIG}])

        mgr._bind_spill_run("sess-2")

        assert spill.read_spilled_window(history[0]["anchor"])["found"] is False

    def test_nothing_is_written_when_no_run_is_bound(self):
        """An artifact that could never be re-read is pure cost."""
        mgr = _manager()
        spill.bind_task(None)

        history = _drain(mgr, [{"tool": "execute_command", "status": "success", "output": _BIG}])

        assert history[0]["output"] == _BIG
        assert "anchor" not in history[0]
        assert not os.listdir(os.environ["AUTOBOT_TOOL_OUTPUT_SPILL_ROOT"])


class TestTheTurnActuallyBindsTheRun:
    """Drives `_run_llm_iterations`, not the helper it calls.

    An earlier version of this file only called `_bind_spill_run` directly.
    Deleting the bind from the turn left all ten tests green — the helper was
    covered and the wiring was not, which is the same shape of gap that let this
    whole feature ship unreachable.
    """

    @pytest.mark.asyncio
    async def test_the_iteration_driver_binds_the_session(self, monkeypatch):
        from chat_workflow import manager as manager_mod
        from chat_workflow.models import LLMIterationContext

        # Cancel at the first hook so the loop exits immediately; the bind
        # happens before it, which is the point being pinned.
        async def _no_continue(*_a, **_k):
            return False

        monkeypatch.setattr(manager_mod, "_emit_before_continuation", _no_continue)

        mgr = _manager()
        mgr.MAX_CONTINUATION_ITERATIONS = 1
        mgr._log_iteration_start = lambda ctx: None
        ctx = LLMIterationContext(
            ollama_endpoint="http://127.0.0.1:11434",
            selected_model="test-model",
            session_id="sess-from-turn",
            terminal_session_id="term-1",
            used_knowledge=False,
            rag_citations=[],
            workflow_messages=[],
        )
        ctx.initial_prompt = "hello"
        ctx.context = {}

        spill.bind_task(None)
        async for _ in mgr._run_llm_iterations(MagicMock(), ctx):
            break

        assert spill.current_task_id() == "sess-from-turn"


class TestOffByDefault:
    def test_the_flag_off_leaves_the_turn_byte_identical(self, monkeypatch):
        monkeypatch.setattr(spill, "SPILL_ENABLED", False)
        mgr = _manager()
        mgr._bind_spill_run("sess-1")
        original = [{"tool": "execute_command", "status": "success", "output": _BIG}]

        history = _drain(mgr, original)

        assert history == original

    def test_a_spill_failure_keeps_the_full_output(self, monkeypatch):
        """Losing the offload is always better than losing the observation."""
        mgr = _manager()
        mgr._bind_spill_run("sess-1")
        monkeypatch.setattr(spill, "spill_execution_results", MagicMock(side_effect=RuntimeError("disk full")))
        original = [{"tool": "execute_command", "status": "success", "output": _BIG}]

        history = _drain(mgr, original)

        assert history[0]["output"] == _BIG
