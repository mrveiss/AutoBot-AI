# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Repair path for Issue #13293 — chat:session:* turns damaged before #13214.

Before #13214 merged, a completed streamed reply was never written to
``chat:session:{id}`` (the durable, GUI-facing store): every LLM chunk carries
``metadata.streaming = True`` and both accumulators drop those chunks, and the
completed-reply text was accepted by ``_persist_workflow_messages`` and then
silently discarded. A conversational turn from that window therefore reads
back with the user's message and no assistant reply at all.

The missing text survives in the legacy per-turn transcript file
(``data/conversation_transcripts/{id}.json``, read through
``chat_history.legacy_transcripts``), which ``_persist_conversation`` used to
write regardless of the bug. ``chat_sessions`` is the system of record for
conversation turns (``autobot_shared/store_authority.py``); the transcript is
a frozen, read-only LEGACY source that nothing writes since #18293, used here
only as the witness that recovers what ``chat_sessions`` lost. The repair
writes the recovered reply into ``chat_sessions``, never the other way round.

``chat:conversation:{id}`` is no longer consulted. Since #18293 it is a cache
re-projected from ``chat_sessions`` itself, so it cannot carry a reply
``chat_sessions`` lacks -- and a warm entry would shadow the transcript that can.

Still needed after #18293: nothing writes the transcript any more, but the
sessions damaged before #13214 are exactly the ones whose reply exists only
there, and they stay damaged until this repair runs for them.

This module is a REPAIR PATH, not an auto-run migration: nothing here
executes on import, there is no scheduled/Celery hook, and the CLI entry
point requires explicit ``--session-id`` arguments — no bulk "repair
everything" default. Per #13293 this PR only adds the repair logic and its
tests; it must never be executed against a live system as part of this
change. ``repair_session`` is an unlocked read-modify-write over
``chat_mgr.load_session``/``save_session`` — run it only against a session
with no concurrent writer (e.g. no active chat) or a late write can be lost.
"""

import argparse
import asyncio
from typing import Any, Callable, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from chat_history.legacy_transcripts import read_legacy_transcript_pairs

logger = get_logger(__name__)


def _find_turn_end(messages: List[Dict[str, Any]], start: int) -> int:
    """Index of the next ``sender == "user"`` message after *start*, or ``len(messages)``.

    Defines one turn's message window: everything from a user message up to
    (not including) the next user message, or the end of the session.
    """
    return next((j for j in range(start, len(messages)) if messages[j].get("sender") == "user"), len(messages))


def _find_matching_pair_index(
    user_text: str,
    conversation_pairs: List[Dict[str, str]],
    used_pair_indices: set,
) -> int | None:
    """First not-yet-consumed pair whose ``user`` text matches *user_text* byte-for-byte."""
    return next(
        (
            idx
            for idx, pair in enumerate(conversation_pairs)
            if idx not in used_pair_indices and (pair.get("user") or "").strip() == user_text
        ),
        None,
    )


def compute_backfilled_messages(
    session_messages: List[Dict[str, Any]],
    conversation_pairs: List[Dict[str, str]],
    build_assistant_message: Callable[[str], Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Return (repaired_messages, backfilled_count) for one session.

    Pure function: plain dicts in, plain dicts out — no I/O —
    so the matching logic is independently testable from the load/save seam
    that ``repair_session`` owns.

    A user turn is "damaged" when NO assistant message appears anywhere in its
    window — from the user message up to (not including) the next user
    message. Checking only the immediately-following slot is wrong: a healthy
    tool-using turn persists as ``[user, system(terminal_output), assistant]``
    (see ``manager.py``'s ``_build_workflow_message_batch``), and would be
    misjudged damaged by a next-slot-only check, causing a spurious duplicate
    insertion (#13303 review). For each genuinely damaged turn, the first
    not-yet-consumed legacy transcript pair whose ``user``
    text matches byte-for-byte supplies the missing ``assistant`` text,
    inserted at the end of the turn's window — after any tool/system entries,
    preserving them.
    """
    repaired = list(session_messages)
    used_pair_indices: set = set()
    backfilled = 0

    i = 0
    while i < len(repaired):
        msg = repaired[i]
        if msg.get("sender") != "user":
            i += 1
            continue

        turn_end = _find_turn_end(repaired, i + 1)
        user_text = (msg.get("text") or "").strip()
        has_reply = any(repaired[j].get("sender") == "assistant" for j in range(i + 1, turn_end))
        if has_reply or not user_text:
            i = turn_end
            continue

        pair_idx = _find_matching_pair_index(user_text, conversation_pairs, used_pair_indices)
        if pair_idx is None:
            i = turn_end
            continue

        used_pair_indices.add(pair_idx)
        assistant_text = (conversation_pairs[pair_idx].get("assistant") or "").strip()
        if not assistant_text:
            i = turn_end
            continue

        repaired.insert(turn_end, build_assistant_message(assistant_text))
        backfilled += 1
        i = turn_end + 1  # skip past the reply just inserted

    return repaired, backfilled


def _build_backfilled_assistant_message(chat_mgr, text: str) -> Dict[str, Any]:
    """Build the persisted dict for one backfilled assistant turn.

    ``sources: []`` — the legacy transcript carries no
    citation metadata, so a backfilled turn cannot claim KB provenance it
    never recorded (#13292's fidelity fix does not apply retroactively;
    there is nothing to recover).
    """
    return chat_mgr._build_message_dict(
        "assistant",
        text,
        "response",
        {"message_type": "llm_response", "backfilled_from": "legacy_conversation_transcripts", "streamed": True},
        None,
        sources=[],
    )


async def repair_session(
    session_id: str,
    chat_mgr,
    transcript_dir: str | None = None,
) -> int:
    """Backfill missing assistant turns for one session. Returns count repaired.

    Args:
        session_id: The session to repair.
        chat_mgr: A ``ChatHistoryManager`` (or duck-typed equivalent exposing
            ``load_session``/``save_session``/``_build_message_dict``).
        transcript_dir: Override for tests; defaults to production's path.

    Returns 0 when the session needed no repair, or its legacy transcript
    has nothing to backfill from. Sessions with NO turns in ``chat_sessions``
    are not repaired here (``load_session`` is empty): they start with no
    prior context until an approved #17038 backfill moves their turns in.

    Not concurrency-safe: this is a plain read-modify-write over
    ``load_session``/``save_session`` with no lock. Run it only against a
    session with no in-flight writer.
    """
    conversation_pairs = await read_legacy_transcript_pairs(session_id, transcript_dir)
    if not conversation_pairs:
        return 0

    session_messages = await chat_mgr.load_session(session_id)
    if not session_messages:
        return 0

    repaired, backfilled = compute_backfilled_messages(
        session_messages,
        conversation_pairs,
        lambda text: _build_backfilled_assistant_message(chat_mgr, text),
    )

    if backfilled:
        await chat_mgr.save_session(session_id, messages=repaired)
        logger.info("Backfilled %d assistant turn(s) for session %s", backfilled, session_id)

    return backfilled


async def _main(session_ids: List[str]) -> None:
    """CLI driver — repairs exactly the sessions named on the command line.

    No bulk/auto-discovery mode by design (#13293): an operator must name
    every session_id explicitly, so this can never sweep production by
    accident. Not invoked anywhere in this change.
    """
    from chat_history import ChatHistoryManager

    chat_mgr = ChatHistoryManager()
    total = 0
    for session_id in session_ids:
        count = await repair_session(session_id, chat_mgr)
        total += count
        logger.info("session=%s backfilled=%d", session_id, count)
    logger.info("Repair complete: %d turn(s) backfilled across %d session(s)", total, len(session_ids))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill missing chat:session:* assistant turns (#13293).")
    parser.add_argument(
        "--session-id",
        action="append",
        required=True,
        dest="session_ids",
        help="Session ID to repair. Repeat for multiple sessions.",
    )
    args = parser.parse_args()
    asyncio.run(_main(args.session_ids))
