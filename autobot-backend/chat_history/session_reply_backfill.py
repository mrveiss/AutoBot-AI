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

``chat:conversation:{id}`` (see ``chat_workflow.conversation``) — the short
lived ``{user, assistant}`` pair cache used to build LLM context — was
unaffected: ``_persist_conversation`` always wrote it, bug or no bug. While it
has not expired (``conversation_history_ttl``, default 24h — see
``chat_history/cache.py``), it is the only remaining source of the missing
assistant text, so it is the backfill source of truth here.

This module is a REPAIR PATH, not an auto-run migration: nothing here
executes on import, there is no scheduled/Celery hook, and the CLI entry
point requires explicit ``--session-id`` arguments — no bulk "repair
everything" default. Per #13293 this PR only adds the repair logic and its
tests; it must never be executed against a live system as part of this
change.
"""

import argparse
import asyncio
import json
from typing import Any, Callable, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

# Mirrors chat_workflow.conversation.ConversationHandlerMixin._get_conversation_key.
_CONVERSATION_KEY_PREFIX = "chat:conversation:"


def _conversation_key(session_id: str) -> str:
    """Redis key holding the ``{user, assistant}`` pair history for *session_id*."""
    return f"{_CONVERSATION_KEY_PREFIX}{session_id}"


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


def compute_backfilled_messages(
    session_messages: List[Dict[str, Any]],
    conversation_pairs: List[Dict[str, str]],
    build_assistant_message: Callable[[str], Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Return (repaired_messages, backfilled_count) for one session.

    Pure function: plain dicts in, plain dicts out — no I/O, no Redis client —
    so the matching logic is independently testable from the load/save seam
    that ``repair_session`` owns.

    A user turn is "damaged" when no assistant message immediately follows it
    (before the next user message, if any). For each damaged turn, the first
    not-yet-consumed ``chat:conversation:*`` pair whose ``user`` text matches
    byte-for-byte supplies the missing ``assistant`` text, inserted as a new
    message directly after the user turn — restoring both the reply and the
    turn ordering a reload should show.
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

        user_text = (msg.get("text") or "").strip()
        next_is_reply = i + 1 < len(repaired) and repaired[i + 1].get("sender") == "assistant"
        if next_is_reply or not user_text:
            i += 1
            continue

        pair_idx = next(
            (
                idx
                for idx, pair in enumerate(conversation_pairs)
                if idx not in used_pair_indices and (pair.get("user") or "").strip() == user_text
            ),
            None,
        )
        if pair_idx is None:
            i += 1
            continue

        used_pair_indices.add(pair_idx)
        assistant_text = (conversation_pairs[pair_idx].get("assistant") or "").strip()
        if not assistant_text:
            i += 1
            continue

        repaired.insert(i + 1, build_assistant_message(assistant_text))
        backfilled += 1
        i += 2  # skip past the turn just repaired

    return repaired, backfilled


def _build_backfilled_assistant_message(chat_mgr, text: str) -> Dict[str, Any]:
    """Build the persisted dict for one backfilled assistant turn.

    ``sources: []`` — chat:conversation:* pairs carry no citation metadata, so
    a backfilled turn cannot claim KB provenance it never recorded (#13292's
    fidelity fix does not apply retroactively; there is nothing to recover).
    """
    return chat_mgr._build_message_dict(
        "assistant",
        text,
        "response",
        {"message_type": "llm_response", "backfilled_from": "chat:conversation", "streamed": True},
        None,
        sources=[],
    )


async def repair_session(session_id: str, chat_mgr, redis_client=None) -> int:
    """Backfill missing assistant turns for one session. Returns count repaired.

    Args:
        session_id: The session to repair.
        chat_mgr: A ``ChatHistoryManager`` (or duck-typed equivalent exposing
            ``load_session``/``save_session``/``_build_message_dict``).
        redis_client: Optional async Redis client (``database="main"``); a
            fresh one is opened when omitted. Injectable so tests never touch
            a real connection.

    Returns 0 when the session needed no repair, chat:conversation:* has
    already expired/never existed, or the session itself has no messages.
    """
    redis_client = redis_client if redis_client is not None else await get_async_redis_client(database="main")
    if redis_client is None:
        logger.warning("No Redis client available — cannot repair session %s", session_id)
        return 0

    raw = await redis_client.get(_conversation_key(session_id))
    conversation_pairs = _parse_conversation_pairs(raw)
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
