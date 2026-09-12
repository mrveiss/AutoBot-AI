#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Session-deletion cleanup helpers.

Split out of ``api/chat_sessions.py`` (#16490) rather than added there:
that file was already at ``scripts/check_python_file_size.py``'s recorded
ceiling, a grandfathered ratchet whose file "may not grow" past it, so the
one line ``_perform_all_session_cleanup`` needs to call this module's new
``_cleanup_chat_knowledge_context`` had no room. Moving the six pre-existing
``_cleanup_knowledge_base_facts``/``_cleanup_conversation_transcript`` and
their small helpers (#620's Extract-Method split) out here first --
unchanged -- shrinks
``chat_sessions.py`` enough to lower that ceiling instead of raising it, and
gives the new helper a home beside the ones it now runs alongside.

``_cleanup_chat_knowledge_context`` (#16490) closes the gap issue #16490
found: deleting a chat session never removed its chat-knowledge context
(``api/chat_knowledge_manager.py``'s ``ChatKnowledgeManager.chat_contexts``),
so a deleted chat's context, temporary knowledge and file associations lived
on indefinitely as an orphan. It uses ``peek_chat_knowledge_manager``, never
the constructing accessor: building a ``ChatKnowledgeManager`` (its own
``KnowledgeBase`` + LLM service) on every session deletion just to discover
the session never touched chat-knowledge would be the exact cost
``api/chat_knowledge_manager.py``'s own docstring (#15160) already named and
avoided on the read path.
"""

from typing import List

from fastapi import Request

from api.chat_knowledge_delete import delete_chat_knowledge_context
from api.chat_knowledge_manager import peek_chat_knowledge_manager
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def _get_knowledge_base_or_none(request: Request):
    """
    Get knowledge base from app state or None if unavailable.

    Issue #620.
    """
    return getattr(request.app.state, "knowledge_base", None)


def _create_kb_cleanup_result() -> dict:
    """
    Create initial KB cleanup result dictionary.

    Issue #620.
    """
    return {
        "facts_deleted": 0,
        "facts_preserved": 0,
        "cleanup_error": None,
    }


def _process_kb_deletion_result(result: dict, kb_cleanup_result: dict) -> None:
    """
    Process and update cleanup result from knowledge base deletion.

    Issue #620.

    Args:
        result: Result from knowledge_base.delete_facts_by_session
        kb_cleanup_result: Result dict to update in place
    """
    kb_cleanup_result["facts_deleted"] = result.get("deleted_count", 0)
    kb_cleanup_result["facts_preserved"] = result.get("preserved_count", 0)

    if result.get("errors"):
        kb_cleanup_result["cleanup_error"] = f"{len(result['errors'])} errors during cleanup"


def _log_kb_cleanup_result(session_id: str, kb_cleanup_result: dict, errors: List | None = None) -> None:
    """
    Log KB cleanup results appropriately based on outcome.

    Issue #620.

    Args:
        session_id: Session being cleaned up
        kb_cleanup_result: Cleanup result dictionary
        errors: Optional list of errors from deletion
    """
    if errors:
        logger.warning(
            "KB cleanup completed with errors for session %s: %s",
            session_id,
            errors,
        )

    if kb_cleanup_result["facts_deleted"] > 0 or kb_cleanup_result["facts_preserved"] > 0:
        logger.info(
            "KB cleanup for session %s: deleted=%d, preserved=%d",
            session_id,
            kb_cleanup_result["facts_deleted"],
            kb_cleanup_result["facts_preserved"],
        )


async def _cleanup_knowledge_base_facts(request: Request, session_id: str) -> dict:
    """
    Clean up knowledge base facts created during this session.

    Issue #547: Fixes orphaned KB data when conversations are deleted.
    Issue #620: Refactored using Extract Method pattern.

    Args:
        request: FastAPI request object with app.state
        session_id: Chat session ID being deleted

    Returns:
        Dict with cleanup statistics
    """
    kb_cleanup_result = _create_kb_cleanup_result()

    knowledge_base = _get_knowledge_base_or_none(request)
    if not knowledge_base:
        logger.warning(
            "Knowledge base not available, skipping KB cleanup for session %s",
            session_id,
        )
        return kb_cleanup_result

    try:
        result = await knowledge_base.delete_facts_by_session(
            session_id=session_id,
            preserve_important=True,
        )
        _process_kb_deletion_result(result, kb_cleanup_result)
        _log_kb_cleanup_result(session_id, kb_cleanup_result, result.get("errors"))

    except Exception as kb_cleanup_error:
        logger.error(
            "Failed to cleanup KB facts for session %s: %s",
            session_id,
            kb_cleanup_error,
            exc_info=True,
        )
        kb_cleanup_result["cleanup_error"] = str(kb_cleanup_error)

    return kb_cleanup_result


async def _cleanup_conversation_transcript(session_id: str) -> dict:
    """
    Clean up conversation transcript file from data/conversation_transcripts/.

    This removes the duplicate transcript storage used by ChatWorkflowManager.

    Args:
        session_id: Chat session ID being deleted

    Returns:
        Dict with cleanup result
    """
    import os

    from autobot_shared.security.path_validator import validate_relative_path
    from constants.path_constants import PATH

    result = {"transcript_deleted": False, "error": None}

    try:
        if "/" in session_id or "\\" in session_id or ".." in session_id:
            raise ValueError("Invalid session ID")

        transcript_path = validate_relative_path(
            f"{session_id}.json",
            PATH.DATA_DIR / "conversation_transcripts",
        )

        # CodeQL py/path-injection only credits a realpath + startswith(root + os.sep) guard in the
        # sink's own scope (#16229, #16236); validate_relative_path above stays the real validator.
        # The one name this adds a refusal for resolves to the directory itself, which os.remove refuses too.
        root = os.path.realpath(str(PATH.DATA_DIR / "conversation_transcripts"))
        real = os.path.realpath(str(transcript_path))
        if not real.startswith(root + os.sep):
            raise ValueError("Invalid session ID")

        if os.path.exists(real):
            os.remove(real)
            result["transcript_deleted"] = True
            logger.info("Deleted conversation transcript for session %s", session_id)
        else:
            logger.debug(
                "No conversation transcript found for session %s (may not exist)",
                session_id,
            )

    except Exception as e:
        logger.warning(
            "Failed to delete conversation transcript for session %s: %s",
            session_id,
            e,
        )
        result["error"] = str(e)

    return result


async def _cleanup_chat_knowledge_context(request: Request, session_id: str) -> dict:
    """Delete the chat-knowledge context for a session being deleted (#16490).

    Peek-only, never the constructing accessor: see the module docstring for
    why building a ``ChatKnowledgeManager`` here would repeat #15160's cost.
    """
    result = {"context_deleted": False, "file_associations_removed": 0}

    manager = peek_chat_knowledge_manager(request)
    if manager is None:
        return result

    removed = await delete_chat_knowledge_context(manager, session_id)
    if removed is not None:
        result["context_deleted"] = True
        result["file_associations_removed"] = removed
    return result
