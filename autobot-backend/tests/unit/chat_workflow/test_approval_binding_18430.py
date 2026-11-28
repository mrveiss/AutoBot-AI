# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A person's yes in the chat interrupt belongs to the calls they were shown, in the batch it was given (#18430).

The decision used to live in checkpointed state forever, cover the whole batch while the interrupt showed only
the first call, and so approve every later line-2 action in the session. Three things are pinned here:
the interrupt shows every call and binds the yes to their fingerprints; a new plan and a new turn start with no
decision; and the dispatch seam holds anything outside the bound set.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.ai_lines import AiLine
from chat_workflow.approval_binding import ai_line_calls_shown, bind_decision
from services.ai_line_enforcement import shown_call_fingerprint
from tests.unit.chat_workflow.test_ai_line_support import arun_guard

KEY_A = "sk-live-abcdef1234567890"  # pragma: allowlist secret
KEY_B = "sk-live-OTHER-1234567890"  # pragma: allowlist secret
SEND_A = {"name": "crm", "params": {"action": "send", "to": "a", "api_key": KEY_A}}
SEND_B = {"name": "crm", "params": {"action": "send", "to": "b"}}
LINES = {"crm:send": AiLine.DRAFT_THEN_SEND}


def _graph():
    try:
        import chat_workflow.graph as graph
    except ImportError as exc:
        pytest.skip(f"chat_workflow not importable here: {exc}")
    return graph


def test_the_bound_set_is_the_fingerprints_of_exactly_the_shown_calls():
    decision = bind_decision({"approved": True, "reason": "ok"}, [SEND_A, SEND_B])
    assert decision["approved"] is True
    assert decision["bound"] == [
        shown_call_fingerprint("crm", SEND_A["params"]),
        shown_call_fingerprint("crm", SEND_B["params"]),
    ]


def test_the_clients_resume_payload_cannot_choose_what_is_bound():
    decision = bind_decision({"approved": True, "bound": ["forged"], "approved_fingerprints": ["forged"]}, [SEND_B])
    assert "forged" not in decision["bound"] and len(decision["bound"]) == 1


@pytest.mark.parametrize("answer", [{"approved": False}, {}, None, "yes", {"approved": "true"}, {"approved": 1}])
def test_anything_but_a_literal_yes_binds_nothing(answer):
    assert bind_decision(answer, [SEND_A])["bound"] == []


def test_the_fingerprint_is_of_the_raw_params_not_the_redacted_ones():
    """Two calls differing only in a masked credential are different calls."""
    other = {
        "name": "crm",
        "params": {**SEND_A["params"], "api_key": KEY_B},
    }
    assert shown_call_fingerprint("crm", SEND_A["params"]) != shown_call_fingerprint("crm", other["params"])
    assert KEY_A not in str(ai_line_calls_shown([SEND_A]))


def test_the_interrupt_lists_every_call_that_needs_a_person():
    shown = ai_line_calls_shown([SEND_A, SEND_B])
    assert [c["tool"] for c in shown] == ["crm", "crm"] and shown[1]["params"]["to"] == "b"


@pytest.mark.asyncio
async def test_request_approval_shows_every_call_and_binds_the_yes_to_them():
    graph = _graph()
    seen = {}

    def fake_interrupt(payload):
        seen["payload"] = payload
        return {"approved": True, "reason": ""}

    state = {
        "tool_calls": [dict(SEND_A, needs_approval=True), dict(SEND_B, needs_approval=True), {"name": "get_text"}],
        "session_id": "s",
        "terminal_session_id": "t",
    }
    with patch.object(graph, "interrupt", fake_interrupt):
        out = await graph.request_approval(state, {"configurable": {}})
    assert [c["params"]["to"] for c in seen["payload"]["metadata"]["calls"]] == ["a", "b"]
    assert len(out["approval_decision"]["bound"]) == 2


@pytest.mark.asyncio
async def test_a_batch_with_nothing_to_approve_clears_a_stale_decision():
    graph = _graph()
    out = await graph.request_approval(
        {"tool_calls": [{"name": "get_text"}], "approval_decision": {"approved": True}}, {}
    )
    assert out["approval_decision"] is None


@pytest.mark.asyncio
async def test_a_new_plan_starts_with_no_decision():
    """A second batch after a yes must not inherit it: the planner resets the decision for every batch."""
    graph = _graph()
    ctx = MagicMock(requires_approval_before=[], context={})
    stale = {"approved": True, "reason": "", "bound": [shown_call_fingerprint("crm", SEND_B["params"])]}
    plan = AsyncMock(return_value=([], "r", [dict(SEND_B)], False))
    with (
        patch.object(graph, "_run_llm_iteration_plan", plan),
        patch.object(graph, "_emit_planned_agent_complete_hook", AsyncMock()),
        patch.object(graph, "_tool_call_needs_approval", AsyncMock(return_value=True)),
    ):
        out = await graph._generate_response_planned(
            {"session_id": "s", "approval_decision": stale}, MagicMock(), ctx, 2, [], None, "step", 0.0
        )
    assert out["approval_decision"] is None and out["tool_calls"][0]["needs_approval"] is True


@pytest.mark.asyncio
async def test_a_new_turn_starts_clean():
    graph = _graph()
    manager = MagicMock()
    manager._initialize_chat_session = AsyncMock(return_value=(MagicMock(), "term", False))
    manager._persist_user_message = AsyncMock()
    out = await graph.initialize_session(
        {"session_id": "s", "user_message": "hi", "approval_decision": {"approved": True}},
        {"configurable": {"manager": manager}},
    )
    assert out["approval_decision"] is None and out["pending_approval"] is None


@pytest.mark.asyncio
async def test_a_second_batch_after_a_yes_is_held_again_and_a_call_not_shown_is_not_approved():
    first = bind_decision({"approved": True}, [SEND_A])
    graph = _graph()
    ctx_first = graph._build_llm_iteration_context(_state(first))
    # Batch 1: the shown call passes line 2; a call that was NOT shown is held.
    ok, _ = await arun_guard(dict(SEND_A), ctx_first, [], stored=LINES)
    unseen, _ = await arun_guard(dict(SEND_B), ctx_first, [], stored=LINES)
    assert ok is None and unseen.type == "approval_required"
    # Batch 2: the planner reset the decision, so even the identical call is held again.
    ctx_second = graph._build_llm_iteration_context(_state(None))
    again, _ = await arun_guard(dict(SEND_A), ctx_second, [], stored=LINES)
    assert again.type == "approval_required"


def _state(decision):
    return {
        "session_id": "s",
        "terminal_session_id": "t",
        "user_message": "m",
        "context": {"verified_company_id": "00000000-0000-0000-0000-000000004530"},
        "llm_params": {
            "ollama_endpoint": "http://x",
            "selected_model": "m",
            "system_prompt": "s",
            "initial_prompt": "p",
        },
        "approval_decision": decision,
    }
