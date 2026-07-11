# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11552: the graph's _build_llm_iteration_context must thread the request
context (company_id/user_id) into ctx.context, so company-scoped tools (e.g.
the LLC CEO-chat tools, #11501) can resolve company_id in the GRAPH path — the
legacy _create_llm_iteration_context already did; the graph path dropped it.

Imports the real helper; skips where the heavy chat_workflow chain can't load
(runs in CI).
"""

from __future__ import annotations

import pytest


def _build():
    try:
        from chat_workflow.graph import _build_llm_iteration_context
    except ImportError as exc:  # env-dependent chain; a real regression still fails
        pytest.skip(f"chat_workflow not importable here: {exc}")
    return _build_llm_iteration_context


def _state(context):
    return {
        "session_id": "t1",
        "terminal_session_id": "term1",
        "user_message": "Create a task",
        "context": context,
        "llm_params": {
            "ollama_endpoint": "http://x/api/generate",
            "selected_model": "m",
            "system_prompt": "s",
            "initial_prompt": "p",
        },
        "used_knowledge": False,
        "rag_citations": [],
        "execution_history": [],
    }


def test_context_threaded_into_iteration_context():
    build = _build()
    ctx = build(_state({"company_id": "co-123", "user_id": "u-9"}))
    assert ctx.context.get("company_id") == "co-123"
    assert ctx.context.get("user_id") == "u-9"


def test_missing_context_is_empty_not_crash():
    build = _build()
    ctx = build(_state({}))
    assert ctx.context == {}
    ctx2 = build(_state(None))
    assert ctx2.context == {}


def test_shallow_copy_isolates_graph_state():
    """#11552 review: the seam mutates ctx.context in place (delegations,
    fact-forcing scratch) — that must NOT corrupt the persisted graph
    state["context"]."""
    build = _build()
    state = _state({"company_id": "co-1"})
    ctx = build(state)
    ctx.context["delegations_this_turn"] = 3  # simulate an in-seam write
    assert "delegations_this_turn" not in state["context"]  # original untouched
