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

The knowledge was already in the codebase in hand-written pairs —
``context_overflow._format_messages`` and ``api/chat.py``'s **inbound** mapping
(``_to_persisted_message``) both do the ``or`` fallback. Several other readers
do not, and nothing made the omissions visible. Hence one function rather than
another copy — see the consolidate-never-fork rule.

Known readers still on a single schema, each filed rather than silently fixed
here because they sit in different subsystems with their own blast radius:

* **#14306** — was ``api/chat_sessions.py::_preserve_system_messages``,
  which filtered on the role key against disk-shape records so the flag it
  served preserved nothing. #14359 removed the flag and the reader with it:
  nothing ever persisted a system prompt for it to find, on either schema.

(Described without quoting the literal values: the hardcoded-value gate scans
added lines including prose, and a comment citing a banned pattern trips its
own lint.)

Two further readers are filed but not fixed here, because both are outages of a
different shape than the schema mismatch this module addresses — they lose the
record rather than mislabel it, and they sit in subsystems with their own blast
radius: **#14340** (the shared-link viewer filters on a key stored records have
never carried, so every shared session renders empty) and **#14341** (the
overflow summary is written under one body key and persisted from another, so
every auto-summary is stored empty and the conversation it condensed is gone).

Deliberately NOT applied to LLM-API-only readers (``llm_shared/providers/*``,
``token_optimizer``, ``complexity_router``, and ``context_overflow``'s
tool-batch scan). Those handle messages that are already in API shape by
construction, and teaching them a second schema would widen a contract that is
currently correct.

``llm_role`` is the one exception to that neutrality, and is marked as such
rather than quietly admitted. Everything else here answers a question about the
*stored data*; that one answers a question about what a **provider** will
accept, which is a constraint from the other side of the boundary. It lives
here anyway because the alternative is a second module reimplementing the
both-schemas read, and because the constraint is not one provider's quirk —
``vertexai``'s content builder independently collapses non-conversational roles
the same way. If a third provider-facing rule ever wants to join it, that is the
signal to split them out rather than to keep widening this module.
"""

from typing import Any, Dict, List

_UNKNOWN_ROLE = "unknown"

# The roles a conversation turn can carry into a provider request.
_CALLER_ROLE = "user"
_RESPONDER_ROLE = "assistant"
_CONVERSATION_ROLES = frozenset({_CALLER_ROLE, _RESPONDER_ROLE})


def message_role(message: Dict[str, Any], default: str = _UNKNOWN_ROLE) -> str:
    """The speaker, from either schema.

    ``role`` (API) wins over ``sender`` (stored) when both are present, matching
    the precedence the existing hand-written readers already use.
    """
    return str(message.get("role") or message.get("sender") or default)


def message_type(message: Dict[str, Any], default: str = "default") -> str:
    """The stored message-kind label, from either schema.

    Stored/display records carry it under ``messageType``
    (``MessagesMixin._build_message_dict``); ``_to_persisted_message`` in
    ``api/chat.py`` writes it under ``type``. Both keys are read elsewhere in
    ``api/chat.py`` by hand (``msg.get("messageType", msg.get("type", ...))``,
    duplicated at two call sites); this is that expression promoted to the
    shared reader so a third caller does not re-fork it.
    """
    return str(message.get("messageType") or message.get("type") or default)


def _resolved_body(value: Any) -> str:
    """One key's value as a string: joined part-list, plain string, or ``""``.

    Anything that is neither (``None``, ``0``, ``False``, a stray dict) resolves
    to ``""`` rather than being ``str()``-ed, which would put the literal
    ``"False"`` in front of the model.

    ``isinstance(part.get("text"), str)`` is load-bearing, not defensive: a part
    with ``text: None`` is a shape providers genuinely emit, and it 500'd the
    live chat path once (#14065). Lifted from the version that survived that
    incident rather than re-derived.
    """
    if isinstance(value, list):
        return " ".join(
            part["text"]
            for part in value
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)
        ).strip()
    return value if isinstance(value, str) else ""


def message_text(message: Dict[str, Any]) -> str:
    """The body, from either schema.

    Returns ``""`` when the message carries no text under either key, so callers
    can filter on emptiness without having to know which schema they were handed.

    **A ``content`` that yields no text falls through to the other key**
    (#14335) — an empty part-list, and equally a list whose parts are all
    non-text, such as an image-only multimodal message. The fallback is decided
    on the *resolved* body, not on the raw value, which is what makes those two
    cases behave alike; an earlier version tested the raw value and so fell
    through only when ``content`` was absent or an empty string.

    The image-only list is the case that matters in practice — a bare
    ``content: []`` is barely a real shape, while a message carrying an image
    and a caption is one a provider can genuinely emit.

    The reasoning that was reversed here: that an empty list is a well-formed
    *"this message has no text parts"* and so nothing needs looking up
    elsewhere. That reasoning is wrong for a reader whose entire purpose is
    that either key may hold the body: an empty ``content`` has told us nothing,
    while ``text`` may still hold everything.

    It is also wrong in the direction that costs data. Every consumer treats an
    empty result as *absent*, and each loses something different: distillation
    **drops** the message — precisely the #14259 defect this module exists to
    fix — the overflow tracker under-counts retained tokens and delays the next
    compaction, and the chat path sends the model an empty turn. There is no
    consumer for which returning ``""`` over an available body is the better
    answer.

    No writer emits either shape beside a populated ``text`` today — swept in
    review across the persisted-message writers, the summary builder and the
    workflow batch builder — so nothing live changes. What it removes is a
    divergence from ``context_overflow._message_text``, which already fell
    through and which this function now backs. The behavioural delta therefore
    lands only on this function's *direct* callers (``as_llm_messages``, the
    chat context builders, the shared-link viewer), not on the overflow token
    path, which was already on these semantics.
    """
    return _resolved_body(message.get("content")) or _resolved_body(message.get("text"))


def llm_role(message: Dict[str, Any], default: str = _CALLER_ROLE) -> str:
    """The speaker as a role a provider will actually accept (#14305).

    `message_role` answers *who spoke*, faithfully — and a chat session records
    speakers that are not conversational roles at all. Terminal integration,
    the agent terminal and the workflow state machine all persist into the same
    session under names of their own, so a reader that hands `message_role`'s
    answer straight to a provider builds a request the API rejects, failing the
    whole turn.

    Anything outside the two conversational roles therefore collapses to the
    caller. That is exactly what the hand-written readers did for these records
    before — they asked for a key the stored shape has never carried and took
    their default — so this preserves their behaviour for every record whose
    speaker was never expressible, while the two roles that *are* expressible
    now survive instead of being flattened along with them.

    This is an **allowlist**, not a list of known-bad speakers, and deliberately
    so: the speakers above were found by grepping one keyword-argument form, so
    a writer that passes its sender positionally or through a variable would not
    have appeared. Naming what may pass keeps the unenumerated ones safe — and
    they exist. The websocket layer formats about a dozen more (tool output,
    workflow, agent-step and error variants); they are inert only because that
    path drops its session id and writes to a bucket no session reader touches
    (#14342). Closing that routing gap must not require revisiting this.

    The system role is deliberately not passed through. It is a legal role, but
    it does not mean *a turn in the conversation* — an adapter that separates it
    out hoists it into the instruction channel, so a persisted operational
    notice (an approval, a command result) would arrive as an instruction rather
    than as history. That is an elevation of ordinary history into the
    highest-trust slot, wrong on its own terms; it becomes destructive as well
    on any route that carries a real system prompt for it to overwrite, which
    `chat_optimized` already does and the plain chat path does not yet.
    Callers that genuinely carry a system prompt add it themselves.
    """
    role = message_role(message, default=default)
    return role if role in _CONVERSATION_ROLES else default


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
