# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Rolling summary of the chat turns that fall out of the prompt window (#20852).

``LLMHandler._build_conversation_context`` keeps the last ``RECENT_TURNS_KEPT``
turns verbatim. Everything older used to be dropped, so a constraint or decision
stated early in a long task vanished from the prompt. This module folds those
older turns into a summary produced by ``ConversationSummarizer`` -- the one
summariser the overflow protection, the compact hook and ``/chat/summarize``
also use -- on the locally configured model.

Store authority: the durable conversation is the system of record. The summary
is a rebuildable projection kept only on the in-process ``WorkflowSession``
(``metadata[ROLLING_SUMMARY_KEY]``); it is never written to a store of its own.
Losing it (restart, TTL expiry) costs one re-summarisation of the older turns.
"""

import time
from typing import Any, Dict, List, Optional

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import CategoryDefaults
from chat_history.context_overflow import ConversationSummarizer

logger = get_logger(__name__)

# Turns kept verbatim in the prompt; only turns before these are summarised.
RECENT_TURNS_KEPT = env_int("AUTOBOT_ROLLING_SUMMARY_RECENT_TURNS", 2)

# A cached summary older than this is rebuilt from the turns, bounding drift
# from repeated fold-of-a-fold summarisation.
ROLLING_SUMMARY_TTL_SECONDS = env_int("AUTOBOT_ROLLING_SUMMARY_TTL_SECONDS", 3600)

# After a failed summarisation, do not retry for this long (one attempt per
# window instead of one per turn, mirroring the overflow-protection backoff).
ROLLING_SUMMARY_FAILURE_BACKOFF_SECONDS = env_int("AUTOBOT_ROLLING_SUMMARY_FAILURE_BACKOFF_SECONDS", 300)

# Output cap handed to the summariser.
ROLLING_SUMMARY_MAX_TOKENS = env_int("AUTOBOT_ROLLING_SUMMARY_MAX_TOKENS", 500)

ROLLING_SUMMARY_KEY = "rolling_summary"


def complete_turns(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Turns whose assistant reply exists (an empty reply is an in-flight turn, #715)."""
    return [msg for msg in history or [] if msg.get("assistant")]


def render_context(history: List[Dict[str, str]], rolling_summary: str = "") -> str:
    """Prompt text: summary of the older turns (if any), then the last turns verbatim (#715 filter)."""
    recent = complete_turns(history)[-RECENT_TURNS_KEPT:]
    if not recent:
        return ""
    parts = [f"\n**Summary of earlier conversation:**\n{rolling_summary}\n"] if rolling_summary else []
    parts.append("\n**Recent Context:**\n")
    parts.extend(f"User: {t['user']}\nYou: {t['assistant']}\n\n" for t in recent)
    return "".join(parts)


def _as_messages(turns: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for turn in turns:
        out.append({"role": CategoryDefaults.ROLE_USER, "content": turn.get("user", "")})
        out.append({"role": CategoryDefaults.ROLE_ASSISTANT, "content": turn.get("assistant", "")})
    return out


def _plan(entry: Optional[Dict[str, Any]], total: int, now: float) -> tuple:
    """Return (prior_summary, first_unsummarised_index) from the cache entry."""
    if not entry or now - entry.get("ts", 0) > ROLLING_SUMMARY_TTL_SECONDS:
        return "", 0
    covered = entry.get("covered", 0)
    if covered > total:  # history shrank (edit/regenerate): rebuild
        return "", 0
    return entry.get("text", ""), covered


async def fold_older_turns(
    metadata: Dict[str, Any],
    history: List[Dict[str, str]],
    model_name: str,
    summarizer: Optional[ConversationSummarizer] = None,
    now: Optional[float] = None,
) -> str:
    """Rolling summary of the turns before the last ``RECENT_TURNS_KEPT``.

    Returns ``""`` when there is nothing older, or when summarisation failed --
    the caller then behaves exactly as before this feature (older turns dropped).
    A failure is logged as a warning and never raised.
    """
    older = complete_turns(history)[: -RECENT_TURNS_KEPT or None]
    if not older:
        return ""
    now = time.time() if now is None else now
    entry = metadata.get(ROLLING_SUMMARY_KEY)
    if entry and now - entry.get("failed_at", -1e12) < ROLLING_SUMMARY_FAILURE_BACKOFF_SECONDS:
        return entry.get("text", "")
    prior, start = _plan(entry, len(older), now)
    if prior and start == len(older):
        return prior
    summarizer = summarizer or ConversationSummarizer()
    try:
        text = await summarizer.summarize_messages(
            _as_messages(older[start:]),
            model_name,
            prior_summary=prior,
            max_tokens=ROLLING_SUMMARY_MAX_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001 -- a summary failure must never break the turn
        logger.warning("Rolling summary failed; older turns dropped from the prompt: %s", exc, exc_info=True)
        metadata[ROLLING_SUMMARY_KEY] = {**(entry or {}), "failed_at": now}
        return (entry or {}).get("text", "") if prior else ""
    metadata[ROLLING_SUMMARY_KEY] = {"text": text, "covered": len(older), "ts": now}
    return text


async def fold_session(session: Any, model_name: str) -> str:
    """``fold_older_turns`` over a ``WorkflowSession`` (its metadata is the cache)."""
    return await fold_older_turns(session.metadata, session.conversation_history, model_name)
