# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The default live turn: one headless chat turn on a throwaway session, and everything it must clean up (#20843).

The turn leaves nothing behind: the graph checkpoints, the chat-history session that ``process_message`` persists
under the eval's own ``eval-*`` id, and any approval the turn paused on (denied, "denied: eval run", so none stays
queued). A turn whose graph never ran (``process_message_stream`` fell back to the legacy flow) is not run.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.tool_catalogue import APPROVAL_CATEGORY_TOOLS
from eval.live_classify import LiveRunRecord
from eval.runner import RecordingUnusable
from eval.store import GoldenTrajectory

logger = get_logger(__name__)

#: The bounded profile every live run is governed by (``orchestration.agent_registry``).
READ_ONLY_AGENT_ID = "research_agent"
STATUS_COMPLETED, STATUS_ERROR, STATUS_AWAITING_APPROVAL = "completed", "error", "awaiting_approval"
#: The reason recorded on an approval the eval denies instead of leaving it queued.
DENIED_REASON = "denied: eval run"
#: Knowledge-base states a live run can find: documents present, no documents, or unreachable.
KB_POPULATED, KB_EMPTY, KB_UNREACHABLE = "populated", "empty", "unreachable"


#: The exact shape of a session id this module creates: ``eval-<trajectory_id>-<uuid4 hex>``.
_OWN_SESSION = re.compile(r"^eval-[\w-]+-[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$")


def new_session_id(golden: GoldenTrajectory) -> str:
    """A unique throwaway session id of the one shape ``_delete_history`` will agree to delete."""
    return f"eval-{golden.trajectory_id}-{uuid.uuid4().hex}"


class GraphDidNotRun(RecordingUnusable):
    """No graph state exists for the turn: the chat flow fell back to its legacy path, so the loop was not measured."""


def run_context(model: str) -> Dict[str, Any]:
    """The chat context for one live turn: the pinned model, the bounded profile, every approval gate."""
    return {
        "model": model,
        "agent_id": READ_ONLY_AGENT_ID,
        "requires_approval_before": sorted(APPROVAL_CATEGORY_TOOLS),
    }


def _as_dict(message: Any) -> Dict[str, Any]:
    if isinstance(message, dict):
        return message
    return {
        "type": getattr(message, "type", ""),
        "content": getattr(message, "content", ""),
        "metadata": dict(getattr(message, "metadata", None) or {}),
    }


def _final_text(state: Dict[str, Any], messages: List[Dict[str, Any]]) -> str:
    for text in reversed(state.get("all_llm_responses") or []):
        if text and text.strip():
            return text
    replies = [m.get("content", "") for m in messages if m.get("type") == "response"]
    return replies[-1] if replies else ""


def _status(state: Dict[str, Any]) -> str:
    if state.get("error"):
        return STATUS_ERROR
    return STATUS_AWAITING_APPROVAL if state.get("pending_approval") else STATUS_COMPLETED


def build_record(raw_messages: List[Any], state: Dict[str, Any]) -> LiveRunRecord:
    """A ``LiveRunRecord`` from the messages a turn streamed and the graph state read back afterwards."""
    messages = [_as_dict(m) for m in raw_messages]
    history = list(state.get("execution_history") or [])
    return LiveRunRecord(
        final_text=_final_text(state, messages),
        final_status=_status(state),
        tool_sequence=[str(e["tool"]) for e in history if e.get("tool")],
        raw_responses=list(state.get("all_llm_responses") or []),
        messages=messages,
        execution_history=history,
        tool_loop_count=int(state.get("tool_loop_count") or 0),
        iteration_count=int(state.get("iteration_count") or 0),
        should_continue=bool(state.get("should_continue")),
        used_knowledge=bool(state.get("used_knowledge")),
        rag_citations=list(state.get("rag_citations") or []),
        error=state.get("error"),
    )


async def chat_endpoint_for(model: str) -> str:
    """The endpoint chat will send *model*'s prompts to: SLM discovery first, then the SSOT routing."""
    from chat_workflow import get_chat_workflow_manager

    manager = get_chat_workflow_manager()
    return await manager._discover_ollama_from_slm() or manager._get_ollama_endpoint_for_model(model)


async def _deny_pending_approval(manager: Any, graph: Any, session_id: str, snapshot: Any) -> None:
    """Resume a paused graph with a denial, so the approval the turn raised is resolved and not left queued."""
    if not snapshot.next:
        return
    try:
        async for _ in manager.resume_graph(session_id, {"approved": False, "reason": DENIED_REASON}):
            pass
    except Exception:  # noqa: BLE001 - cleanup must not mask the record; the checkpoints are deleted next
        logger.warning("could not deny the pending approval of %s", session_id, exc_info=True)


async def _delete_history(session_id: str) -> None:
    """Remove the chat-history session ``process_message`` persisted under this eval's own id, and only that id."""
    from chat_history import ChatHistoryManager

    if not _OWN_SESSION.fullmatch(session_id):
        raise ValueError("refusing to delete a chat-history session that is not the eval's own")
    try:
        await ChatHistoryManager().delete_session(session_id)
    except Exception:  # noqa: BLE001 - a leftover transient row must not turn a measured run into a crash
        logger.warning("could not delete the chat history of %s", session_id, exc_info=True)


async def _cleanup(session_id: str) -> None:
    from chat_workflow.graph import delete_thread_checkpoints

    await delete_thread_checkpoints(session_id)
    await _delete_history(session_id)


async def chat_turn_runner(golden: GoldenTrajectory, model: str, workspace: Path) -> LiveRunRecord:
    """The default turn: the real chat graph on a unique throwaway session, cleaned up whatever happens."""
    from chat_workflow import get_chat_workflow_manager
    from chat_workflow.graph import get_compiled_graph

    manager = get_chat_workflow_manager()
    await manager.initialize()
    session_id = new_session_id(golden)
    try:
        messages = await manager.process_message(session_id, golden.query, run_context(model))
        graph = await get_compiled_graph(manager)
        snapshot = await graph.aget_state({"configurable": {"thread_id": session_id}})
        state = dict(snapshot.values or {})
        if not state.get("iteration_count"):
            raise GraphDidNotRun("no graph state for the turn; chat fell back to its legacy flow")
        record = build_record(messages, state)
        await _deny_pending_approval(manager, graph, session_id, snapshot)
        return record
    finally:
        await _cleanup(session_id)


async def probe_knowledge_base() -> str:
    """Whether the knowledge base has documents: ``populated``, ``empty`` or ``unreachable``."""
    try:
        from knowledge_factory import get_knowledge_base_async

        kb = await get_knowledge_base_async()
        if kb is None:
            return KB_UNREACHABLE
        stats = await kb.get_stats()
        return KB_POPULATED if int(stats.get("total_documents", 0)) > 0 else KB_EMPTY
    except Exception:  # noqa: BLE001 - any failure to ask is "unreachable", reported as an environment cause
        logger.warning("knowledge base probe failed", exc_info=True)
        return KB_UNREACHABLE


def chat_resolved_provider() -> str:
    """The provider chat resolves for its turns (the SSOT), not an operator-typed label."""
    from chat_workflow.llm_provider import configured_provider

    return configured_provider().value
