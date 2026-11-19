# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One reply for a turn that ends in ``respond`` (#21880); every assistant entry has its model (#21881)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from async_chat_workflow import WorkflowMessage
from chat_history.messages import MessagesMixin
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.reply_persistence import UNKNOWN_MODEL, is_redundant_prose, normalize_reply

ANSWER = "Riga is **4 degrees** and cloudy today."


def _build(workflow_messages, responses, selected_model="model-a"):
    chat_mgr = SimpleNamespace(_build_message_dict=lambda *a, **k: MessagesMixin._build_message_dict(None, *a, **k))
    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    return manager._build_persist_batch(chat_mgr, workflow_messages, responses, selected_model, None, False)


def _respond(text, iteration):
    return WorkflowMessage(
        type="response",
        content=text,
        metadata={"message_type": "respond_tool", "iteration": iteration},
    )


def _chunk_marker(iteration, model):
    return WorkflowMessage(
        type="segment_complete",
        content="",
        timestamp=1_700_000_000.0 + iteration,
        metadata={
            "completed_type": "response",
            "message_id": f"seg-{iteration}",
            "internal": True,
            "iteration": iteration,
            "model": model,
        },
    )


def _texts(batch):
    return [e["text"] for e in batch if e["sender"] == "assistant"]


@pytest.mark.parametrize(
    "narration",
    [
        "Riga is 4 degrees and cloudy today.",
        "  riga is  **4 degrees**\n and cloudy today!  ",
        "> Riga is _4 degrees_ and cloudy today",
    ],
)
def test_narration_differing_only_in_whitespace_or_markdown_persists_one_reply(narration):
    batch = _build([_respond(ANSWER, 1)], [narration])
    assert _texts(batch) == [ANSWER]


def test_narration_covered_by_the_respond_text_is_dropped():
    batch = _build([_respond(f"Here you go. {ANSWER} Anything else?", 1)], [ANSWER])
    assert len(_texts(batch)) == 1


def test_narration_with_content_absent_from_respond_keeps_both():
    narration = "I could not reach the second site, so the figure comes from the first one only."
    batch = _build([_respond(ANSWER, 1)], [narration])
    assert _texts(batch) == [narration, ANSWER]


def test_narration_containing_the_answer_plus_more_is_kept():
    narration = f"Checked two sources. {ANSWER} Sources disagree by a degree."
    assert not is_redundant_prose(
        narration, [{"sender": "assistant", "text": ANSWER, "metadata": {"message_type": "respond_tool"}}]
    )


def test_normalisation_ignores_case_markdown_and_whitespace():
    assert normalize_reply("**Hello**,\n  World!") == normalize_reply("hello world")


def test_the_surviving_entry_keeps_the_model():
    batch = _build([_respond(ANSWER, 1)], [ANSWER], selected_model="model-a")
    (survivor,) = [e for e in batch if e["sender"] == "assistant"]
    assert survivor["metadata"]["model"] == "model-a"


def test_every_assistant_entry_of_a_two_iteration_turn_has_a_model():
    first = WorkflowMessage(type="terminal_output", content="out", metadata={"iteration": 1})
    batch = _build([first, _respond(ANSWER, 2)], ["Let me search.", ""], selected_model="model-a")
    assistants = [e for e in batch if e["sender"] == "assistant"]
    assert len(assistants) == 2
    assert all(e["metadata"]["model"] == "model-a" for e in assistants)


def test_each_iteration_keeps_the_model_that_produced_it():
    msgs = [_chunk_marker(1, "model-a"), _chunk_marker(2, "model-b"), _respond("final", 2)]
    batch = _build(msgs, ["Searching the web now.", "Writing it up."], selected_model="model-b")
    by_text = {e["text"]: e["metadata"]["model"] for e in batch if e["sender"] == "assistant"}
    assert by_text["Searching the web now."] == "model-a"
    assert by_text["Writing it up."] == "model-b"


def test_an_unknown_model_is_recorded_as_unknown_never_empty():
    batch = _build([_respond("final", 2)], ["First.", ""], selected_model="")
    models = [e["metadata"]["model"] for e in batch if e["sender"] == "assistant"]
    assert models and set(models) == {UNKNOWN_MODEL}
