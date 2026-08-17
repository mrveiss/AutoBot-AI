# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tool-output offload on the approval-gate resume path (#14242).

With ``AUTOBOT_CHAT_APPROVAL_GATE`` on (GH#11202), ``generate_response`` plans
tool calls without dispatching them and defers dispatch to the graph's
``execute_tools`` node. That node calls ``manager._process_tool_calls``
directly and builds its own ``exec_history`` — bypassing
``_process_tool_results``/``_handle_execution_summary``, which is where #13997
hooks the #13692 spill. So the offload never ran on a resume, whatever
``AUTOBOT_TOOL_OUTPUT_SPILL`` was set to.

Fixing that exposed a second bug in the same lines: the "track execution
results" check read ``isinstance(item, dict)`` on the yielded
``WorkflowMessage`` itself, which is never a dict (only its ``.to_dict()``
form, already computed into ``msg_dict``, is) — so it never matched, and
``exec_history`` silently stayed whatever ``state["execution_history"]``
already held. New tool results never reached it at all, offloaded or not.
Both are fixed together because the second bug is what made the first one
untestable: there was nothing to offload.

``chat_workflow.graph`` is imported inside each test (not at module scope),
matching ``streamed_reply_persistence_test.py`` — it pulls in
``langgraph``/``langchain_core``, present in CI but not guaranteed in every
dev shell.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from agent_loop import tool_output_spill as spill
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.tool_handler import ToolHandlerMixin

pytestmark = pytest.mark.asyncio

SESSION_ID = "sess-14242"
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


def _state(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "session_id": SESSION_ID,
        "terminal_session_id": "term-1",
        "user_message": "do the thing",
        "context": {},
        "llm_params": {"ollama_endpoint": "http://127.0.0.1:11434", "selected_model": "test-model"},
        "tool_calls": [{"name": "bash", "params": {"command": "ls"}}],
        "execution_history": [],
        "iteration_count": 1,
        "workflow_messages": [],
    }
    base.update(overrides)
    return base


def _config(manager: ChatWorkflowManager) -> Dict[str, Any]:
    return {"configurable": {"manager": manager, "stream_callback": None}}


def _fake_dispatch(results: List[Dict[str, Any]]):
    """Shaped exactly like ``manager._process_tool_calls``.

    Built through the REAL ``ToolHandlerMixin._build_execution_summary``, not a
    hand-written ``WorkflowMessage`` — the fixture is the same wrapping-event
    shape production actually yields (``metadata.execution_results`` holding
    the flat per-tool list).
    """

    async def _gen(*_args: Any, **_kwargs: Any):
        handler = ToolHandlerMixin()
        yield handler._build_execution_summary(results)
        yield (False, None)

    return _gen


class TestExecutionHistoryActuallyAccumulates:
    """The bug under the bug: without this, nothing reaches the offload."""

    async def test_a_dispatched_result_reaches_execution_history(self, monkeypatch):
        from chat_workflow import graph as graph_mod

        mgr = _manager()
        original = [{"tool": "bash", "status": "success", "output": "ok"}]
        monkeypatch.setattr(mgr, "_process_tool_calls", _fake_dispatch(original))

        out = await graph_mod.execute_tools(_state(), _config(mgr))

        assert out["execution_history"] == original


class TestTheApprovalGateResumeOffloads:
    async def test_oversized_output_is_offloaded_with_excerpt_and_anchor(self, monkeypatch):
        from chat_workflow import graph as graph_mod

        mgr = _manager()
        monkeypatch.setattr(
            mgr,
            "_process_tool_calls",
            _fake_dispatch([{"tool": "bash", "status": "success", "output": _BIG}]),
        )

        out = await graph_mod.execute_tools(_state(), _config(mgr))

        entry = out["execution_history"][0]
        assert len(entry["output"]) < len(_BIG)
        assert entry["anchors"][0].startswith(f"autobot:spill:{SESSION_ID}:")
        assert "read_spilled_output" in entry["output"]

    async def test_the_full_output_is_retrievable_through_the_anchor(self, monkeypatch):
        from chat_workflow import graph as graph_mod

        mgr = _manager()
        monkeypatch.setattr(
            mgr,
            "_process_tool_calls",
            _fake_dispatch([{"tool": "bash", "status": "success", "output": _BIG}]),
        )

        out = await graph_mod.execute_tools(_state(), _config(mgr))
        window = spill.read_spilled_window(out["execution_history"][0]["anchors"][0])

        assert window["found"] is True
        assert window["total_chars"] == len(_BIG)

    async def test_small_results_pass_through_untouched(self, monkeypatch):
        from chat_workflow import graph as graph_mod

        mgr = _manager()
        original = [{"tool": "bash", "status": "success", "output": "short"}]
        monkeypatch.setattr(mgr, "_process_tool_calls", _fake_dispatch(original))

        out = await graph_mod.execute_tools(_state(), _config(mgr))

        assert out["execution_history"] == original

    async def test_the_flag_off_leaves_the_turn_untouched(self, monkeypatch):
        from chat_workflow import graph as graph_mod

        monkeypatch.setattr(spill, "SPILL_ENABLED", False)
        mgr = _manager()
        original = [{"tool": "bash", "status": "success", "output": _BIG}]
        monkeypatch.setattr(mgr, "_process_tool_calls", _fake_dispatch(original))

        out = await graph_mod.execute_tools(_state(), _config(mgr))

        assert out["execution_history"] == original
