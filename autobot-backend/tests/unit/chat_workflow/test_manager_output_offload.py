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


async def _drain(mgr, results):
    """Run one execution-summary through the seam; return what reached history."""
    new_results: List[Dict[str, Any]] = []
    history: List[Dict[str, Any]] = []
    handled = await mgr._handle_execution_summary(_summary(results), new_results, history)
    assert handled is True
    return history


def _real_shell_result(stdout: str) -> Dict[str, Any]:
    """A shell result as production actually emits it.

    Built by `_create_execution_result`, not hand-written: it carries
    `{command, host, stdout, stderr, return_code, status, approved}` — **no
    `output`, no `result`, no `tool`**. An earlier version of this file invented
    a `{"tool", "status", "output"}` envelope, so it could not see that
    `execute_command` — the case this offload names as its primary target —
    never spilled at all.
    """
    from chat_workflow.tool_handler import _create_execution_result

    return _create_execution_result("ls -R /", "local", {"stdout": stdout, "stderr": "", "return_code": 0})


@pytest.mark.asyncio
class TestTheChatSeamActuallyOffloads:
    async def test_an_oversized_result_is_replaced_by_an_excerpt_and_anchor(self):
        mgr = _manager()
        mgr._bind_spill_run("sess-1")

        history = await _drain(mgr, [{"tool": "execute_command", "status": "success", "output": _BIG}])

        assert len(history[0]["output"]) < len(_BIG)
        assert "autobot:spill:sess-1:" in history[0]["anchors"][0]
        assert "read_spilled_output" in history[0]["output"], "the note must reach the model"

    async def test_the_full_output_is_retrievable_through_the_anchor(self):
        """Non-lossy is the whole point. Today's per-tool truncation discards the
        remainder permanently."""
        mgr = _manager()
        mgr._bind_spill_run("sess-1")

        history = await _drain(mgr, [{"tool": "execute_command", "status": "success", "output": _BIG}])
        window = spill.read_spilled_window(history[0]["anchors"][0])

        assert window["found"] is True
        assert window["total_chars"] == len(_BIG)

    async def test_the_envelope_survives(self):
        """`status` decides error handling downstream — tool_handler counts
        `== "success"`, delegation checks `== "error"`. Replacing the whole dict
        with an excerpt would drop it."""
        mgr = _manager()
        mgr._bind_spill_run("sess-1")

        history = await _drain(mgr, [{"tool": "execute_command", "status": "error", "output": _BIG}])

        assert history[0]["status"] == "error"
        assert history[0]["tool"] == "execute_command"

    async def test_output_stays_a_string(self):
        """`_as_output_text` and `tool_handler` read it as one."""
        mgr = _manager()
        mgr._bind_spill_run("sess-1")

        history = await _drain(mgr, [{"tool": "execute_command", "status": "success", "output": _BIG}])

        assert isinstance(history[0]["output"], str)

    async def test_a_real_shell_result_is_offloaded(self):
        """The case this offload names as its primary target, and the one an
        invented fixture could not see.

        `execute_command` results carry `stdout`, not `output`, and no `tool`
        key. A key list of ("output", "result") skipped them entirely — so the
        single likeliest source of a window-consuming result was the one thing
        that never spilled.
        """
        mgr = _manager()
        mgr._bind_spill_run("sess-1")
        entry = _real_shell_result(_BIG)
        assert "output" not in entry and "tool" not in entry, "precondition: the real shape"

        history = await _drain(mgr, [entry])

        assert len(history[0]["stdout"]) < len(_BIG)
        assert "read_spilled_output" in history[0]["stdout"]
        assert spill.read_spilled_window(history[0]["anchors"][0])["total_chars"] == len(_BIG)

    async def test_a_shell_result_is_anchored_by_its_command_not_a_literal(self):
        """Shell results have no `tool` key. Falling back to the literal "tool"
        would collide anchors across unrelated commands in one session."""
        mgr = _manager()
        mgr._bind_spill_run("sess-1")

        history = await _drain(mgr, [_real_shell_result(_BIG)])

        assert "ls -R /" in history[0]["anchors"][0]

    async def test_both_stdout_and_stderr_offload(self):
        """A failing command can put megabytes in each."""
        mgr = _manager()
        mgr._bind_spill_run("sess-1")
        entry = {**_real_shell_result(_BIG), "stderr": "E" * 40_000}

        history = await _drain(mgr, [entry])

        assert len(history[0]["anchors"]) == 2
        assert len(history[0]["stdout"]) < len(_BIG)
        assert len(history[0]["stderr"]) < 40_000

    async def test_small_results_pass_through_untouched(self):
        mgr = _manager()
        mgr._bind_spill_run("sess-1")
        original = [{"tool": "web_search", "status": "success", "output": "short"}]

        history = await _drain(mgr, original)

        assert history == original


@pytest.mark.asyncio
class TestTheRunBinding:
    """#13919's last unticked box. Without a bound run the read tool returns
    `no_run_bound` on every call, which is what it did on this path."""

    async def test_an_anchor_written_here_is_readable_here(self):
        mgr = _manager()
        mgr._bind_spill_run("sess-1")

        history = await _drain(mgr, [{"tool": "execute_command", "status": "success", "output": _BIG}])

        assert spill.read_spilled_window(history[0]["anchors"][0])["found"] is True

    async def test_another_conversation_cannot_read_it(self):
        """The anchor carries its session in plaintext, so scoping has to be
        enforced server-side rather than by the caller."""
        mgr = _manager()
        mgr._bind_spill_run("sess-1")
        history = await _drain(mgr, [{"tool": "execute_command", "status": "success", "output": _BIG}])

        mgr._bind_spill_run("sess-2")

        assert spill.read_spilled_window(history[0]["anchors"][0])["found"] is False

    async def test_nothing_is_written_when_no_run_is_bound(self):
        """An artifact that could never be re-read is pure cost."""
        mgr = _manager()
        spill.bind_task(None)

        history = await _drain(mgr, [{"tool": "execute_command", "status": "success", "output": _BIG}])

        assert history[0]["output"] == _BIG
        assert "anchors" not in history[0]
        assert not os.listdir(os.environ["AUTOBOT_TOOL_OUTPUT_SPILL_ROOT"])


@pytest.mark.asyncio
class TestTheTurnActuallyBindsTheRun:
    """Drives `_run_continuation_loop_iteration` — the seam BOTH paths use.

    The bind was first placed in `_run_llm_iterations`, and this test drove that
    function, so it passed while the feature stayed dead in production: the
    LangGraph path (the default) calls `_run_continuation_loop_iteration`
    directly and bypasses that wrapper entirely. The file's own #11612 docstring
    says so, about the identical mistake made once before with the
    lightweight-mode ContextVar.

    So this test targets the method the graph path actually calls. Driving the
    wrapper would pass for a feature that never runs.
    """

    async def test_the_shared_seam_binds_the_session(self):
        from chat_workflow.models import LLMIterationContext

        mgr = _manager()
        mgr.MAX_CONTINUATION_ITERATIONS = 1

        async def _one_item(*_a, **_k):
            yield (None, False, None)

        mgr._run_continuation_iteration = _one_item
        ctx = LLMIterationContext(
            ollama_endpoint="http://127.0.0.1:11434",
            selected_model="test-model",
            session_id="sess-from-turn",
            terminal_session_id="term-1",
            used_knowledge=False,
            rag_citations=[],
            workflow_messages=[],
        )
        ctx.context = {}

        spill.bind_task(None)
        async for _ in mgr._run_continuation_loop_iteration(MagicMock(), "prompt", 1, ctx):
            pass

        assert spill.current_task_id() == "sess-from-turn"


@pytest.mark.asyncio
class TestOffByDefault:
    async def test_the_flag_off_leaves_the_turn_byte_identical(self, monkeypatch):
        monkeypatch.setattr(spill, "SPILL_ENABLED", False)
        mgr = _manager()
        mgr._bind_spill_run("sess-1")
        original = [{"tool": "execute_command", "status": "success", "output": _BIG}]

        history = await _drain(mgr, original)

        assert history == original

    async def test_a_spill_failure_keeps_the_full_output(self, monkeypatch):
        """Losing the offload is always better than losing the observation."""
        mgr = _manager()
        mgr._bind_spill_run("sess-1")
        monkeypatch.setattr(spill, "spill_execution_results", MagicMock(side_effect=RuntimeError("disk full")))
        original = [{"tool": "execute_command", "status": "success", "output": _BIG}]

        history = await _drain(mgr, original)

        assert history[0]["output"] == _BIG
