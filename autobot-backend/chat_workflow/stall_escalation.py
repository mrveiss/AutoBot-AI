# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Stall escalation as chat-graph nodes (#21022, part of #20846).

A turn *stalls* when the tool-call loop detector fires ``_LOOP_ABORT_THRESHOLD`` times in a row. With
``config.llm.chat_stall_escalation`` = ``stop`` (the default) the turn ends as it always did. With ``ask`` the
graph routes ``announce_stall`` -> ``ask_human``: the first publishes the question on the one bus (channel
``task:{session}``) and to the SSE stream, the second pauses the graph with LangGraph's ``interrupt()`` -- the same
mechanism as ``request_approval`` -- and is resumed by ``POST /chats/{id}/resume`` carrying ``answer``.

Two nodes, not one: a resumed node runs again from its top, so publishing and interrupting in one node would ask
twice. ``AgentLoop`` is never instantiated; delegated subagents (``delegation_depth`` in the turn context) and the
legacy fallback loop never reach the graph's router and always stop.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from autobot_shared.logging_manager import get_logger
from autobot_shared.prompt_rules import frame_untrusted_block, neutralize_frame_markers
from chat_workflow import limits
from events.bus import PersistStrategy
from events.bus import publish_event as _bus_publish_event
from events.event_types import HUMAN_ANSWER_RECEIVED, HUMAN_QUESTION

logger = get_logger(__name__)

STALL_QUESTION = (
    "I keep repeating the same action without making progress. How would you like me to proceed? "
    "Leave the answer empty to stop here."
)
#: What the next generation pass is told once the person has answered.
_GUIDANCE_INTRO = "[Human guidance] You were stuck repeating the same action. The user answered your question:\n"


def _guidance(answer: str) -> str:
    """The user-supplied *answer* as framed data: it cannot close its own frame or pass for a system rule."""
    block = frame_untrusted_block(
        "USER_ANSWER",
        ["The user's own words, supplied in reply to your question. Use them as guidance for the task."],
        neutralize_frame_markers(answer).splitlines() or [""],
    )
    return _GUIDANCE_INTRO + block


def stall_mode(state: Dict[str, Any]) -> str:
    """``ask`` only when the SSOT flag says so AND the turn can be interrupted; otherwise ``stop``."""
    from autobot_shared.ssot_config import config

    if (state.get("context") or {}).get("delegation_depth"):
        return "stop"  # a delegated subagent has no one to answer it
    return "ask" if config.llm.chat_stall_escalation == "ask" else "stop"


def route_after_ask_human(state: Dict[str, Any]) -> str:
    """After the person answered a stall question: carry on, or end the turn if they gave no answer."""
    if not state.get("should_continue"):
        return "persist_conversation"
    if state.get("iteration_count", 0) < limits.MAX_CONTINUATION_ITERATIONS:
        return "generate_response"
    return "force_final_answer"


def add_stall_nodes(builder: Any) -> None:
    """Wire the stall escalation into the chat graph: ``execute_tools`` routes here only when the flag says ask."""
    builder.add_node("announce_stall", announce_stall)
    builder.add_node("ask_human", ask_human)
    builder.add_edge("announce_stall", "ask_human")
    builder.add_conditional_edges("ask_human", route_after_ask_human)


def _channel(session_id: str) -> str:
    return f"task:{session_id}"


async def announce_stall(state: Dict[str, Any], config: RunnableConfig) -> dict:
    """Publish the stall question on ``task:{session}`` and to the stream; the next node pauses on it."""
    session_id = state["session_id"]
    question = {
        "question_id": uuid.uuid4().hex,
        "question": STALL_QUESTION,
        "choices": None,
        "iteration": state.get("iteration_count", 0),
        "task_id": session_id,
    }
    await _bus_publish_event(_channel(session_id), HUMAN_QUESTION, question, persist=PersistStrategy.MEMORY)
    stream_cb = config["configurable"].get("stream_callback")
    if stream_cb:
        metadata = {**question, "session_id": session_id}
        stream_cb({"type": "human_question", "content": STALL_QUESTION, "metadata": metadata})
    return {"stall_question": question}


def _answer_text(decision: Any) -> str:
    return str(decision.get("answer") or "").strip() if isinstance(decision, dict) else ""


async def ask_human(state: Dict[str, Any], config: RunnableConfig) -> dict:
    """Pause the graph for the person's answer; resume with it as guidance, or stop on an empty one."""
    from chat_workflow.tool_call_loop import _append_loop_abort_message

    question = state.get("stall_question") or {}
    answer = _answer_text(interrupt({"type": "human_question", **question}))  # pure before this line: reruns on resume
    session_id = state["session_id"]
    await _bus_publish_event(
        _channel(session_id),
        HUMAN_ANSWER_RECEIVED,
        {"question_id": question.get("question_id"), "answered": bool(answer), "task_id": session_id},
        persist=PersistStrategy.MEMORY,
    )
    if not answer:
        messages = list(state.get("workflow_messages", []))
        stream_cb = config["configurable"].get("stream_callback")
        _append_loop_abort_message(messages, stream_cb, state.get("iteration_count", 0))
        return {"stall_question": None, "should_continue": False, "workflow_messages": messages}
    logger.info("stall escalation answered (session=%s)", session_id)
    return {
        "stall_question": None,
        "should_continue": True,
        "tool_loop_count": 0,  # the human broke the loop: detection starts over
        "tool_call_fingerprints": [],
        "tool_loop_warning": _guidance(answer),
    }
