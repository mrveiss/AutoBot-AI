# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A turn's stored transcript keeps its final answer and each step's own time (#21904, #21846 AC 4).

Drives the graph's real path: ``WorkflowMessage.to_dict()`` state entries, rebuilt by
``_build_workflow_messages_from_state``, built into a batch, then loaded back through the deduplication
a reload applies.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from async_chat_workflow import WorkflowMessage
from chat_history.deduplication import DeduplicationMixin
from chat_history.message_times import distinct_ordered_times, parse_message_timestamp
from chat_history.messages import MessagesMixin
from chat_workflow.graph import _build_workflow_messages_from_state
from chat_workflow.manager import ChatWorkflowManager

NARRATION = "I'll navigate to the page now."
ANSWER = "The current temperature in Riga is -1 degrees."
RAN_AT = time.time() - 120.0  # the tool ran two minutes before the turn was persisted


def _tool_steps(iteration):
    steps = []
    for offset, kind in enumerate(("tool_execution", "command_output", "execution_summary")):
        msg = WorkflowMessage(type=kind, content=f"{kind} text", metadata={"iteration": iteration})
        msg.timestamp = RAN_AT + offset * 0.01
        steps.append(msg)
    return steps


def _stored(wf_messages, responses):
    chat_mgr = SimpleNamespace(_build_message_dict=lambda *a, **k: MessagesMixin._build_message_dict(None, *a, **k))
    manager = ChatWorkflowManager.__new__(ChatWorkflowManager)
    batch = manager._build_persist_batch(chat_mgr, wf_messages, responses, "m", None, False)
    distinct_ordered_times(batch)
    dedupe = DeduplicationMixin()._dedupe_streaming_messages
    return dedupe(dedupe(batch))  # a reload sorts by time; the next save or load then groups the sorted list


def _through_state(messages):
    state = {"workflow_messages": [m.to_dict() for m in messages]}
    return _build_workflow_messages_from_state(state)


def _through_state_entries(entries):
    return _build_workflow_messages_from_state({"workflow_messages": entries})


def _at(entry):
    return parse_message_timestamp(entry["timestamp"]).timestamp()


def test_tool_then_prose_only_turn_stores_the_final_answer():
    stored = _stored(_through_state(_tool_steps(1)), [NARRATION, ANSWER])
    texts = [e["text"] for e in stored]
    assert ANSWER in texts and NARRATION in texts
    assert [e["messageType"] for e in stored][-1] == "response" and stored[-1]["text"] == ANSWER


def test_tool_steps_keep_the_time_they_ran_and_the_prose_sorts_with_them():
    stored = _stored(_through_state(_tool_steps(1)), [NARRATION, ANSWER])
    tools = [e for e in stored if e["messageType"] != "response"]
    assert all(abs(_at(e) - RAN_AT) < 1.0 for e in tools)
    narration = next(e for e in stored if e["text"] == NARRATION)
    assert _at(narration) <= min(_at(e) for e in tools)
    assert _at(stored[-1]) > max(_at(e) for e in tools)
    assert [_at(e) for e in stored] == sorted(_at(e) for e in stored)


def test_a_respond_turn_stores_narration_and_thought_before_the_answer():
    thought = WorkflowMessage(type="response", content="[THOUGHT] checking", metadata={"iteration": 2})
    thought.timestamp = RAN_AT + 1
    respond = WorkflowMessage(
        type="response", content=ANSWER, metadata={"message_type": "respond_tool", "iteration": 2}
    )
    respond.timestamp = RAN_AT + 2
    stored = _stored(_through_state([*_tool_steps(1), thought, respond]), [NARRATION, "Done."])
    times = [_at(e) for e in stored]
    assert times == sorted(times)
    assert stored[-1]["text"] == ANSWER or ANSWER in [e["text"] for e in stored]
    assert _at(next(e for e in stored if e["text"] == ANSWER)) >= _at(
        next(e for e in stored if "[THOUGHT]" in e["text"])
    )


def test_a_rebuilt_message_keeps_its_id_and_creation_time():
    original = _tool_steps(1)[0]
    rebuilt = _through_state([original])[0]
    assert rebuilt.id == original.id and rebuilt.timestamp == original.timestamp


def test_two_completed_iteration_replies_next_to_each_other_are_not_merged():
    """The loss itself: after a time sort the narration and the answer are adjacent; the longer one used to win."""
    now = time.time()
    entries = [
        {
            "id": "a",
            "sender": "assistant",
            "text": NARRATION + " (longer, with a trailing lead-in)",
            "messageType": "response",
            "metadata": {"iteration": 1},
            "timestamp": f"2026-11-20T19:00:0{i}+00:00",
        }
        for i in (1,)
    ] + [
        {
            "id": "b",
            "sender": "assistant",
            "text": ANSWER,
            "messageType": "response",
            "metadata": {"iteration": 2},
            "timestamp": "2026-11-20T19:00:02+00:00",
        },
    ]
    assert now and [e["id"] for e in DeduplicationMixin()._dedupe_streaming_messages(entries)] == ["a", "b"]


def test_a_reply_with_a_thought_block_stores_the_thought_apart_from_the_answer():
    reply = f"[THOUGHT]I should check the page.[/THOUGHT]\n{ANSWER}"
    stored = _stored(_through_state(_tool_steps(1)), [NARRATION, reply])
    thought = next(e for e in stored if e["messageType"] == "thought")
    assert thought["text"] == "I should check the page."
    assert not any("[THOUGHT]" in e["text"] or "I should check" in e["text"] for e in stored if e is not thought)
    assert stored[-1]["text"] == ANSWER
    assert [_at(e) for e in stored] == sorted(_at(e) for e in stored)


def test_a_marker_quoted_in_code_is_not_a_reasoning_block():
    from chat_workflow.thought_markers import split_reasoning_blocks

    blocks, rest = split_reasoning_blocks("Use `[THOUGHT]` to mark reasoning.")
    assert blocks == [] and rest == "Use `[THOUGHT]` to mark reasoning."


def test_an_unclosed_thought_marker_keeps_the_answer_text():
    from chat_workflow.thought_markers import split_reasoning_blocks

    blocks, rest = split_reasoning_blocks(f"[THOUGHT] still thinking\n{ANSWER}")
    assert blocks == [] and ANSWER in rest
    blocks, rest = split_reasoning_blocks(f"[THOUGHT] first [PLANNING] second [/PLANNING]\n{ANSWER}")
    assert [kind for kind, _ in blocks] == ["thought", "planning"] and rest == ANSWER


def test_a_completed_reply_without_an_iteration_is_still_not_merged():
    entries = [
        {
            "id": "a",
            "sender": "assistant",
            "text": NARRATION + " and some more words",
            "messageType": "response",
            "metadata": {"iteration": None, "completed": True},
            "timestamp": "2026-11-20T19:00:01+00:00",
        },
        {
            "id": "b",
            "sender": "assistant",
            "text": ANSWER,
            "messageType": "response",
            "metadata": {"iteration": None, "completed": True},
            "timestamp": "2026-11-20T19:00:02+00:00",
        },
    ]
    assert [e["id"] for e in DeduplicationMixin()._dedupe_streaming_messages(entries)] == ["a", "b"]


def test_persisting_the_same_turn_twice_adds_nothing_the_second_time():
    from chat_history.session_merge import combine_messages

    messages = _through_state(_tool_steps(1))
    first = _stored(messages, [NARRATION, ANSWER])
    again = _stored(_through_state(_tool_steps(1)), [NARRATION, ANSWER])
    # the tool steps are rebuilt with fresh ids here; the replies must carry the same id both times
    reply_ids = lambda batch: [e["id"] for e in batch if e["messageType"] == "response"]  # noqa: E731
    assert reply_ids(first) == reply_ids(again)
    merged = combine_messages(first, [e for e in first], append=True, replace=False)
    assert [e["id"] for e in merged] == [e["id"] for e in first]


def test_a_state_entry_with_no_created_at_is_stamped_at_persist_time():
    """Pinned limitation: a checkpoint written before ``created_at`` existed has no creation time to keep."""
    before = time.time()
    rebuilt = _through_state_entries([{"type": "tool_execution", "content": "ran", "metadata": {}}])[0]
    assert before <= rebuilt.timestamp <= time.time()
