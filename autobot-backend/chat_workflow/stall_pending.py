# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The stall question a paused chat graph is waiting on, read from its checkpoint (#21022).

One reader (``pending_stall_question``) serves both consumers: ``POST /chats/{id}/resume`` binds a request to the
question it answers, and ``GET /chat/sessions/{id}`` restores the card for a person who reloaded while it was open.
"""

from __future__ import annotations

import uuid
from typing import Any, AsyncIterator, Dict, List

from fastapi import HTTPException

from autobot_shared.coordination.work_claims import (
    ClaimConflict,
    ClaimUnavailable,
    ScopeError,
    release_scope,
    try_acquire,
)
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp

logger = get_logger(__name__)

QUESTION_TYPE = "human_question"


async def pending_stall_question(manager: Any, session_id: str) -> Dict[str, Any] | None:
    """The question the graph for *session_id* is interrupted on, or None. Raises when the checkpoint is unreadable."""
    from .graph import get_compiled_graph

    graph = await get_compiled_graph(manager)
    snapshot = await graph.aget_state({"configurable": {"thread_id": session_id}})
    for task in getattr(snapshot, "tasks", None) or ():
        for pending in getattr(task, "interrupts", None) or ():
            value = getattr(pending, "value", None)
            if isinstance(value, dict) and value.get("type") == QUESTION_TYPE:
                return value
    return None


def _is_stall_resume(request_data: dict) -> bool:
    return "answer" in request_data or "question_id" in request_data


RESUME_CLAIM_AGENT = "chat-resume"


async def acquire_answer_lock(chat_id: str) -> str:
    """Hold the per-chat answer claim (the one work-claim registry); returns its task id.

    Check + resume cannot interleave: a second concurrent answer finds it held and gets 409.
    """
    task_id = uuid.uuid4().hex
    try:
        outcome = await try_acquire(
            f"queue:chat-resume-{chat_id}",
            agent_id=RESUME_CLAIM_AGENT,
            task_id=task_id,
            intent="answer a stall question",
        )
    except ScopeError:
        raise HTTPException(status_code=400, detail="Invalid chat id")
    except ClaimUnavailable:
        raise HTTPException(status_code=503, detail="The answer could not be recorded; try again")
    if isinstance(outcome, ClaimConflict):
        raise HTTPException(status_code=409, detail="This question is already being answered")
    return task_id


async def release_answer_lock(chat_id: str, task_id: str) -> None:
    await release_scope(f"queue:chat-resume-{chat_id}", agent_id=RESUME_CLAIM_AGENT, task_id=task_id)


async def release_after(stream: Any, chat_id: str, task_id: str) -> AsyncIterator[Any]:
    """Yield *stream*, then free the answer claim however it ends (the TTL covers a stream never started)."""
    try:
        async for item in stream:
            yield item
    finally:
        await release_answer_lock(chat_id, task_id)


async def check_resume_binding(manager: Any, chat_id: str, request_data: dict) -> None:
    """Refuse a resume that does not match the paused graph: an answer needs its question, a question its answer.

    An explicit empty ``answer`` is a valid "stop here". An approval resume is untouched unless the graph is
    paused on a stall question, where it would otherwise be read as an empty answer and end the turn.
    """
    stall = _is_stall_resume(request_data)
    try:
        pending = await pending_stall_question(manager, chat_id)
    except Exception as exc:  # noqa: BLE001 -- an approval resume reports its own checkpoint failure downstream
        logger.warning("Resume binding unread for chat %s...: %s", chat_id[:8], type(exc).__name__)
        if stall:
            raise HTTPException(status_code=503, detail="The pending question could not be read; try again")
        return
    if pending is None:
        if stall:
            raise HTTPException(status_code=409, detail="No question is waiting for an answer")
        return
    if "answer" not in request_data or request_data.get("question_id") != pending.get("question_id"):
        raise HTTPException(status_code=409, detail="The request does not answer the pending question")


def _question_message(question: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    qid = question.get("question_id")
    return {
        "id": f"stall-{qid}",
        "sender": "assistant",
        "type": QUESTION_TYPE,
        "messageType": QUESTION_TYPE,
        "text": question.get("question", ""),
        "timestamp": utc_timestamp(),
        "metadata": {**question, "session_id": session_id},
    }


def _reopen(message: Dict[str, Any], qid: Any) -> bool:
    """Mark *message* unanswered when it is the card for *qid*: the graph is still paused on it."""
    meta = message.get("metadata") or {}
    if message.get("type") != QUESTION_TYPE or meta.get("question_id") != qid:
        return False
    message["metadata"] = {k: v for k, v in meta.items() if k not in ("answered", "answer_text")}
    return True


async def with_pending_question(request: Any, session_id: str, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """*messages* plus the open stall question's card when history lacks it; a stale ``answered`` card is reopened."""
    manager = getattr(request.app.state, "chat_workflow_manager", None)
    if manager is None:
        return messages
    try:
        question = await pending_stall_question(manager, session_id)
    except Exception as exc:  # noqa: BLE001 -- history still loads without the card
        logger.debug("No stall question restored for chat %s...: %s", session_id[:8], type(exc).__name__)
        return messages
    if question is None:
        return messages
    found = [_reopen(m, question.get("question_id")) for m in messages]
    return messages if any(found) else [*messages, _question_message(question, session_id)]


async def guarded_resume(chat_id: str, request_data: dict, manager: Any, open_stream: Any) -> Any:
    """Check the resume binding and open its stream under the per-chat claim; None claim for an approval resume.

    The claim is held until the returned stream ends (``release_after``) or the check / open fails.
    """
    task_id = await acquire_answer_lock(chat_id) if _is_stall_resume(request_data) else None
    try:
        await check_resume_binding(manager, chat_id, request_data)
        stream = await open_stream()
    except BaseException:
        if task_id:
            await release_answer_lock(chat_id, task_id)
        raise
    return release_after(stream, chat_id, task_id) if task_id else stream
