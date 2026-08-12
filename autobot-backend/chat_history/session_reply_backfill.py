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

Two sources can supply the missing text, both written by
``chat_workflow.conversation._persist_conversation`` regardless of the bug:

1. ``chat:conversation:{id}`` (Redis, ``REDIS_KEY.CHAT_CONVERSATION_PREFIX``)
   — short-lived, ``conversation_history_ttl`` (default 24h). Fast, but every
   session damaged by #13214 is in the past, so this has very likely expired
   by the time anyone runs a repair.
2. ``data/conversation_transcripts/{id}.json`` (the durable file transcript,
   ``ChatWorkflowManager.transcript_dir``) — no TTL, one ``{timestamp, user,
   assistant}`` entry per exchange, the entire session's history (unlike the
   production loader's last-10 truncation, which exists only to bound LLM
   context and is irrelevant here).

``repair_session`` tries Redis first (fast path when still warm) and falls
back to the transcript file — the actual source of truth for anything old
enough to need this repair.

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
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import aiofiles

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_constants import REDIS_KEY

logger = get_logger(__name__)

# Mirrors ChatWorkflowManager.transcript_dir (chat_workflow/manager.py) — not
# yet promoted to a shared SSOT path constant there, so this is a second,
# clearly-labeled copy of that one existing literal (not a new triplication
# like the Redis prefix below was).
_TRANSCRIPT_DIR = "data/conversation_transcripts"


def _conversation_key(session_id: str) -> str:
    """Redis key holding the ``{user, assistant}`` pair history for *session_id*."""
    return f"{REDIS_KEY.CHAT_CONVERSATION_PREFIX}{session_id}"


def _parse_conversation_pairs(raw: str | bytes | None) -> List[Dict[str, str]]:
    """Parse the ``chat:conversation:*`` JSON payload into ``{user, assistant}`` pairs.

    Malformed or empty payloads repair to an empty list rather than raising —
    a single corrupt/expired key must not abort a batch repair run.
    """
    if not raw:
        return []
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        pairs = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Malformed chat:conversation payload — skipping repair for this session")
        return []
    if not isinstance(pairs, list):
        return []
    return [p for p in pairs if isinstance(p, dict) and (p.get("user") or "").strip()]


async def _load_transcript_pairs(session_id: str, transcript_dir: str = _TRANSCRIPT_DIR) -> List[Dict[str, str]]:
    """Read the FULL durable transcript file as ``{user, assistant}`` pairs.

    Unlike ``ChatWorkflowManager._load_transcript`` (which truncates to the
    last 10 exchanges — a bound for LLM context, not repair), this reads
    every exchange ever recorded: a #13214-damaged turn can be arbitrarily
    far back in a long session's history, and it is exactly the case where
    ``chat:conversation:*`` has already expired.
    """
    path = Path(transcript_dir) / f"{session_id}.json"
    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
    except FileNotFoundError:
        return []
    except OSError as exc:
        logger.warning("Failed to read transcript file %s: %s", path, exc)
        return []

    try:
        transcript = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Malformed transcript file %s — skipping repair for this session", path)
        return []

    messages = transcript.get("messages", []) if isinstance(transcript, dict) else []
    if not isinstance(messages, list):
        return []
    return [
        {"user": m.get("user", ""), "assistant": m.get("assistant", "")}
        for m in messages
        if isinstance(m, dict) and (m.get("user") or "").strip()
    ]


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

    Pure function: plain dicts in, plain dicts out — no I/O, no Redis client —
    so the matching logic is independently testable from the load/save seam
    that ``repair_session`` owns.

    A user turn is "damaged" when NO assistant message appears anywhere in its
    window — from the user message up to (not including) the next user
    message. Checking only the immediately-following slot is wrong: a healthy
    tool-using turn persists as ``[user, system(terminal_output), assistant]``
    (see ``manager.py``'s ``_build_workflow_message_batch``), and would be
    misjudged damaged by a next-slot-only check, causing a spurious duplicate
    insertion (#13303 review). For each genuinely damaged turn, the first
    not-yet-consumed ``chat:conversation:*``/transcript pair whose ``user``
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

    ``sources: []`` — the conversation-pair/transcript sources carry no
    citation metadata, so a backfilled turn cannot claim KB provenance it
    never recorded (#13292's fidelity fix does not apply retroactively;
    there is nothing to recover).
    """
    return chat_mgr._build_message_dict(
        "assistant",
        text,
        "response",
        {"message_type": "llm_response", "backfilled_from": "chat:conversation", "streamed": True},
        None,
        sources=[],
    )


async def _load_conversation_pairs(session_id: str, redis_client, transcript_dir: str) -> List[Dict[str, str]]:
    """Redis ``chat:conversation:*`` first (fast, may be TTL-expired), else the
    durable transcript file — the actual source for anything old enough to
    need this repair.
    """
    if redis_client is not None:
        raw = await redis_client.get(_conversation_key(session_id))
        pairs = _parse_conversation_pairs(raw)
        if pairs:
            return pairs
    return await _load_transcript_pairs(session_id, transcript_dir)


async def repair_session(
    session_id: str,
    chat_mgr,
    redis_client=None,
    transcript_dir: str = _TRANSCRIPT_DIR,
) -> int:
    """Backfill missing assistant turns for one session. Returns count repaired.

    Args:
        session_id: The session to repair.
        chat_mgr: A ``ChatHistoryManager`` (or duck-typed equivalent exposing
            ``load_session``/``save_session``/``_build_message_dict``).
        redis_client: Optional async Redis client (``database="main"``); a
            fresh one is opened when omitted, and Redis is skipped (falling
            straight to the transcript file) if unavailable.
        transcript_dir: Override for tests; defaults to production's path.

    Returns 0 when the session needed no repair, or no source (Redis nor
    transcript) has anything to backfill from.

    Not concurrency-safe: this is a plain read-modify-write over
    ``load_session``/``save_session`` with no lock. Run it only against a
    session with no in-flight writer.
    """
    if redis_client is None:
        redis_client = await get_async_redis_client(database="main")
        if redis_client is None:
            logger.warning("No Redis client available for session %s — using transcript file only", session_id)

    conversation_pairs = await _load_conversation_pairs(session_id, redis_client, transcript_dir)
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
