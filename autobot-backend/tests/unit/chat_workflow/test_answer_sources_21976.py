# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An answer carries proof of how it was reached (#21976): its steps as sources, and a check of the values it quotes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from async_chat_workflow import WorkflowMessage
from chat_history.messages import MessagesMixin
from chat_workflow.answer_sources import build_answer_sources, check_quoted_values, proof_message
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.step_evidence import begin_step, safe_args, value_literals

ANSWER = "It is overcast, 34°F (1°C)."
SEARCH_OUTPUT = "[1] Riga weather https://weather.example/riga\nOvercast, 1°C"


def _executed(tool, params, results):
    """Run *results* through the real stamping a dispatch performs for one call."""
    step = begin_step()
    step.finish(results, {"name": tool, "params": params})
    return results


def _search():
    return _executed(
        "web_search",
        {"query": "weather in Riga"},
        [{"tool": "web_search", "status": "success", "output": SEARCH_OUTPUT}],
    )


def _uname(output="6.18.33.2-microsoft-standard-WSL2"):
    return _executed(
        "execute_command",
        {"command": "uname -r", "host": "main"},
        [{"command": "uname -r", "host": "main", "stdout": output, "return_code": 0, "status": "success"}],
    )


def test_web_search_step_is_one_source_with_tool_args_urls_step_id_and_time():
    (source,) = build_answer_sources(_search(), [], False, "model-a")
    assert source["type"] == "web_search"
    assert source["metadata"]["tool"] == "web_search"
    assert source["metadata"]["args"] == {"query": "weather in Riga"}
    assert source["metadata"]["origin"]["urls"] == ["https://weather.example/riga"]
    assert source["url"] == "https://weather.example/riga"
    assert source["step_id"] and source["metadata"]["started_at"] <= source["metadata"]["ended_at"]


def test_navigate_step_records_the_page_url():
    results = _executed(
        "navigate", {"url": "https://weather.example/riga"}, [{"tool": "navigate", "status": "success", "output": "x"}]
    )
    (source,) = build_answer_sources(results, [], False, "m")
    assert source["type"] == "web_page" and source["url"] == "https://weather.example/riga"


def test_command_step_records_host_command_and_exit_code():
    (source,) = build_answer_sources(_uname(), [], False, "m")
    origin = source["metadata"]["origin"]
    assert (origin["host"], origin["command"], origin["return_code"]) == ("main", "uname -r", 0)
    assert source["type"] == "system_state"


def test_a_refused_step_and_the_respond_tool_are_no_sources():
    refused = _executed("execute_command", {"command": "rm x"}, [{"tool": "execute_command", "status": "error"}])
    answer = _executed("respond", {"text": "hi"}, [{"tool": "respond", "status": "success", "output": "hi"}])
    assert build_answer_sources(refused + answer, [], False, "m")[0]["type"] == "llm_training"


def test_a_tool_turn_never_claims_training_data():
    types = [s["type"] for s in build_answer_sources(_search(), [], False, "m")]
    assert "llm_training" not in types


def test_a_knowledge_turn_never_claims_training_data():
    kb = [{"id": "c1", "title": "Runbook", "source": "kb/r.md", "score": 0.9}]
    types = [s["type"] for s in build_answer_sources([], kb, True, "m")]
    assert types == ["knowledge_base"]


def test_a_turn_with_no_tool_and_no_knowledge_has_exactly_one_training_source():
    sources = build_answer_sources([], [], False, "model-a")
    assert [s["type"] for s in sources] == ["llm_training"] and sources[0]["model"] == "model-a"


FAKE_TOKEN = "notarealtokenvalue"  # pragma: allowlist secret
FAKE_KEY = "sk-notarealkey"  # pragma: allowlist secret


def test_arguments_pass_the_canonical_redactor():
    args = safe_args({"command": f"curl -H 'Authorization: Bearer {FAKE_TOKEN}' x", "api_key": FAKE_KEY, "n": 1})
    assert FAKE_TOKEN not in str(args) and FAKE_KEY not in str(args) and args["n"] == 1


def test_the_uname_case_shows_the_wrong_value_as_unproven():
    proof = check_quoted_values("The kernel is 5.18.33.2-microsoft-standard-WSL2.", _uname(), "what kernel", [])
    assert proof["unproven"] == ["5.18.33.2"]
    assert "WSL2" in proof["found"]


def test_a_matching_value_is_found_in_its_step():
    history = _uname()
    proof = check_quoted_values("It is 6.18.33.2.", history, "q", [])
    assert proof["unproven"] == [] and proof["found"] == {"6.18.33.2": history[0]["step"]["id"]}


def test_a_computed_value_is_unproven():
    proof = check_quoted_values(
        "It is 41°F.", _executed("web_search", {}, [{"status": "success", "output": "5°C"}]), "", []
    )
    assert proof["unproven"] == ["41°F"]


def test_a_value_survives_the_offload_of_its_output():
    history = _uname()
    history[0]["stdout"] = "[output offloaded: anchor 1]"  # what the spill leaves in the result
    assert check_quoted_values("It is 6.18.33.2.", history, "", [])["unproven"] == []


def test_no_tool_step_means_no_proof_block():
    assert check_quoted_values("It is 41°F.", [], "", []) is None


def test_value_literals_split_like_the_kernel_string():
    assert value_literals("6.18.33.2-microsoft-standard-WSL2, see https://a.example/x.") == [
        "https://a.example/x",
        "6.18.33.2",
        "WSL2",
    ]


# --- the stream carries what is stored -------------------------------------------------------------------------


def _persist(history, answer=ANSWER, rag=None):
    chat_mgr = SimpleNamespace(_build_message_dict=lambda *a, **k: MessagesMixin._build_message_dict(None, *a, **k))
    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    respond = WorkflowMessage(
        type="response", content=answer, metadata={"message_type": "respond_tool", "iteration": 1}
    )
    batch = manager._build_persist_batch(
        chat_mgr, [respond], [f"{answer} <TOOL_CALL name=\"respond\" params='{{\"text\":\"x\"}}'>d</TOOL_CALL>"],
        "model-a", rag, bool(rag), "turn-1", history, "weather?",
    )  # fmt: skip
    return batch, respond


def test_the_stored_answer_has_the_sources_the_stream_carries():
    batch, respond = _persist(_search())
    (stored,) = [e for e in batch if e["sender"] == "assistant"]
    live = proof_message(stored)
    assert stored["sources"] == live.metadata["citations"] == stored["metadata"]["citations"]
    assert stored["sources"][0]["type"] == "web_search"
    assert live.id == live.metadata["message_id"] == respond.id
    assert live.content == stored["text"] and live.metadata["message_type"] == "respond_tool"


def test_the_stored_answer_lists_its_unproven_value():
    batch, _ = _persist(_search())
    (stored,) = [e for e in batch if e["sender"] == "assistant"]
    assert stored["metadata"]["proof"]["unproven"] == ["34°F"]


@pytest.mark.parametrize("history", [[]])
def test_a_no_tool_turn_is_stored_with_the_training_label(history):
    batch, _ = _persist(history)
    (stored,) = [e for e in batch if e["sender"] == "assistant"]
    assert [s["type"] for s in stored["sources"]] == ["llm_training"]
    assert "proof" not in stored["metadata"]


@pytest.mark.asyncio
async def test_the_graph_path_streams_the_proof_it_persisted(monkeypatch):
    """The graph's persist node has the stream callback; it must hand the answer's proof to it (#21976)."""
    from unittest.mock import AsyncMock

    from chat_workflow import graph as graph_mod

    proof = WorkflowMessage(type="response", content="a", metadata={"citations": []})
    manager = SimpleNamespace(
        get_or_create_session=AsyncMock(return_value=object()),
        _persist_conversation=AsyncMock(),
        _persist_workflow_messages=AsyncMock(return_value=proof),
    )
    sent = []
    config = {"configurable": {"manager": manager, "stream_callback": sent.append}}
    state = {"session_id": "s", "user_message": "weather?", "all_llm_responses": ["a"], "execution_history": _search()}
    await graph_mod.persist_conversation(state, config)
    assert sent == [proof]
    kwargs = manager._persist_workflow_messages.call_args.kwargs
    assert kwargs["history"] is state["execution_history"] and kwargs["user_message"] == "weather?"
