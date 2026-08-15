# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One reader for the two shapes a chat message arrives in (#14259).

Chat messages exist in two schemas and always have:

* **stored / display** — what ``MessagesMixin._build_message_dict`` writes to
  disk and what ``load_session`` returns: ``{"id", "sender", "text",
  "metadata", "timestamp", "sources"}``;
* **API / LLM** — what providers and the chat API exchange: ``{"role",
  "content"}``.

Neither is going away, and a consumer that reads only one silently sees nothing
when handed the other. That is not hypothetical: skill distillation read
``role``/``content`` and **filtered** on ``if msg.get("content")``, so every
stored conversation collapsed to an empty list. The pass then reported those
conversations as distilled and advanced its cursor past them — #12809's pipeline
had never extracted a skill from a real conversation.

The knowledge was already in the codebase, twice, in hand-written pairs:
``context_overflow._format_messages`` and ``api/chat.py``'s inbound mapping both
do the ``or`` fallback. A third consumer simply did not, and nothing made the
omission visible. Hence one function rather than a fourth copy — see the
consolidate-never-fork rule.

Deliberately NOT applied to LLM-API-only readers (``llm_shared/providers/*``,
``token_optimizer``, ``complexity_router``, and ``context_overflow``'s
tool-batch scan). Those handle messages that are already in API shape by
construction, and teaching them a second schema would widen a contract that is
currently correct.
"""

from typing import Any, Dict, List

_UNKNOWN_ROLE = "unknown"


def message_role(message: Dict[str, Any], default: str = _UNKNOWN_ROLE) -> str:
    """The speaker, from either schema.

    ``role`` (API) wins over ``sender`` (stored) when both are present, matching
    the precedence the existing hand-written readers already use.
    """
    return str(message.get("role") or message.get("sender") or default)


def message_text(message: Dict[str, Any]) -> str:
    """The body, from either schema.

    Returns ``""`` when the message carries no text under either key, so callers
    can filter on emptiness without having to know which schema they were handed.
    """
    value = message.get("content")
    if value is None or value == "":
        value = message.get("text")
    if value is None:
        return ""
    # A list is the multimodal content shape (`[{"type": "text", ...}, ...]`);
    # join its text parts rather than str()-ing the whole structure into the
    # conversation, which would put JSON punctuation in front of the model.
    #
    # `isinstance(part.get("text"), str)` is load-bearing, not defensive: a part
    # with ``text: None`` is a shape providers genuinely emit, and it 500'd the
    # live chat path once already (#14065). Lifted verbatim from
    # `context_overflow._format_messages` rather than re-derived — that version
    # is the one that survived the incident.
    if isinstance(value, list):
        return " ".join(
            part["text"]
            for part in value
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)
        ).strip()
    return str(value)


def as_llm_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Normalise a conversation to API shape, dropping entries with no text.

    The single call for "give me this conversation as the model would see it",
    whichever schema it was stored in. Non-dict entries are skipped rather than
    raising: malformed history is data, not a programming error.
    """
    normalised: List[Dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        text = message_text(message)
        if not text:
            continue
        normalised.append({"role": message_role(message), "content": text})
    return normalised
