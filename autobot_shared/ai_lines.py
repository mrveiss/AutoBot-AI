# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The three lines for AI, as pure data and one pure resolution rule (#18430).

Owner rule 2026-10-12. For every ACTION of every tool, AI has one of three lines:

1. ``autonomous``      -- AI does it alone, then reports.
2. ``draft_then_send`` -- AI drafts, a person sends; it waits in Approvals.
3. ``never``           -- AI never touches; only people act.

A line that is not set counts as line 2 until the owner role decides.

This module holds only the vocabulary and the decision function, with no I/O, so the chat
seam, the agent terminal and the API all resolve a line the same way. The store is
``llc.services.ai_lines``; the one place that ENFORCES a resolved line is
``services.ai_line_enforcement``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from autobot_shared.tool_catalogue import ToolEffect, canonical_tool_name, tool_effect


class AiLine(str, Enum):
    """The three lines. ``rank`` orders them from loosest to strictest."""

    AUTONOMOUS = "autonomous"
    DRAFT_THEN_SEND = "draft_then_send"
    NEVER = "never"

    @property
    def rank(self) -> int:
        return _RANKS[self]


_RANKS = {AiLine.AUTONOMOUS: 1, AiLine.DRAFT_THEN_SEND: 2, AiLine.NEVER: 3}

#: A line nobody set. Owner rule: counts as line 2 until the owner role decides.
DEFAULT_LINE = AiLine.DRAFT_THEN_SEND

#: ``context`` key holding the company of the AUTHENTICATED principal (#18430). The request's own
#: ``company_id`` is a client claim and never scopes a policy decision; only this key does.
VERIFIED_COMPANY_KEY = "verified_company_id"
#: ``context`` key holding the AUTHENTICATED user (never the request's ``user_id`` claim): the personal scope.
VERIFIED_USER_KEY = "verified_user_id"
#: ``context`` key set by the chat route ONLY when the STRICT session posture (admin, or the recorded owner)
#: passed for this turn: attached conversation files are read for this turn only then (#20195). Written or removed
#: on every overlay by ``apply_auth_role``, never left as a client sent it.
VERIFIED_ATTACHMENT_ACCESS_KEY = "verified_attachment_access"
#: ``context`` key the workflow sets each turn that carries attached files: file text is untrusted data in the
#: prompt, so EVERY tool call of that turn waits for a person's approval (#20195). Set from the server's own
#: check on every turn; a client sending it can only tighten its own turn.
ATTACHMENT_TURN_KEY = "attachment_turn"
#: ``context`` key set from the SERVER's durable record that this chat once used an attachment: model output derived
#: from a file sits in its history, so every tool call of every later turn waits for a person too (#20195). Removed
#: from whatever a client sent and written only from the record (``chat_workflow.attachment_floor``).
ATTACHMENT_CHAT_KEY = "attachment_chat"
#: ``context`` key set from the admin-only SLM setting ``chat.auto_approve_attachment_turns`` (off by default): when
#: present the two keys above no longer force asking and the normal AI lines apply (#20195). Server-set each turn.
ATTACHMENT_AUTO_APPROVE_KEY = "attachment_auto_approve"

#: A line is stored under a scope: a company, or -- for a user with no company -- the user alone (#18430).
SCOPE_COMPANY = "company"
SCOPE_USER = "user"

#: Why a line resolved the way it did (shown to the person; also what the tests assert on).
SOURCE_STORED = "stored"
SOURCE_DEFAULT = "default"
SOURCE_BASELINE = "baseline_floor"
SOURCE_ROLE = "role_floor"
SOURCE_UNAVAILABLE = "store_unavailable"
SOURCE_UNMANAGED = "unmanaged"
SOURCE_NO_COMPANY = "no_verified_company"


@dataclass(frozen=True)
class LineScope:
    """Whose lines apply: ``kind`` is :data:`SCOPE_COMPANY` or :data:`SCOPE_USER`; ``id`` is that principal's UUID."""

    kind: str
    id: uuid.UUID


def resolve_scope(company_id: Any, user_id: Any) -> Optional[LineScope]:
    """The scope for an authenticated principal, or ``None`` when it cannot be scoped (REFUSE).

    * A company that is PRESENT but not a valid id is forged or broken: ``None``, never a fall-through to the
      user's personal scope.
    * No company at all is normal (a user outside any company): the user's own personal scope.
    * Neither: nothing to scope by, ``None``.
    """
    if company_id not in (None, ""):
        try:
            return LineScope(SCOPE_COMPANY, uuid.UUID(str(company_id)))
        except ValueError:
            return None
    if user_id not in (None, ""):
        try:
            return LineScope(SCOPE_USER, uuid.UUID(str(user_id)))
        except ValueError:
            return None
    return None


def strictest(*lines: AiLine) -> AiLine:
    """The strictest of *lines* (a process is only as free as its least free action)."""
    return max(lines, key=lambda line: line.rank)


def parse_line(value: Any) -> Optional[AiLine]:
    """``AiLine`` for a stored/wire value, ``None`` for anything else (never a guess)."""
    try:
        return AiLine(value)
    except ValueError:
        return None


def action_key(tool_name: str, params: Optional[Mapping[str, Any]] = None) -> str:
    """The key a line is stored under: ``<canonical tool>`` or ``<canonical tool>:<action>``.

    A tool whose call names an ``action`` (``crm`` + ``send``) has per-action lines; the tool-level
    key is the fallback (:func:`fallback_keys`).
    """
    name = canonical_tool_name(str(tool_name).strip())
    action = (params or {}).get("action") if isinstance(params, Mapping) else None
    if isinstance(action, str) and action.strip():
        return f"{name}:{action.strip().lower()}"
    return name


def fallback_keys(key: str) -> tuple[str, ...]:
    """Keys to try, most specific first: ``crm:send`` then ``crm``."""
    tool = key.split(":", 1)[0]
    return (key,) if tool == key else (key, tool)


#: The two ways the AI talks to the person. Gating them would stall the conversation or file an approval
#: to ask for approval; they change nothing in the world.
CONVERSATION_TOOLS = frozenset({"respond", "request_approval"})


def is_mutating(tool_name: str) -> bool:
    """Whether *tool_name* may change something: anything the tool-effect SSOT does not KNOW is read-only.

    Fail closed (#18430): an unknown tool (MCP, plugin, a new builtin) counts as mutating, so an unset line
    holds it. Only a tool the catalogue declares with no mutating effect, or a conversation tool, is free.
    """
    if tool_name in CONVERSATION_TOOLS:
        return False
    declared = tool_effect(tool_name)
    return declared is None or bool(declared & ToolEffect.MUTATING)


@dataclass(frozen=True)
class LineResolution:
    """A resolved line and the reason for it."""

    key: str
    line: AiLine
    source: str
    stored: Optional[AiLine] = None
    floor_category: Optional[str] = None

    @property
    def reason(self) -> str:
        if self.source == SOURCE_BASELINE:
            return f"approval baseline category '{self.floor_category}' can never be autonomous"
        if self.source == SOURCE_ROLE:
            return "the agent role's policy requires approval for this risk"
        if self.source == SOURCE_NO_COMPANY:
            return "no verified company or user scopes this action, so it cannot be allowed"
        if self.source == SOURCE_UNAVAILABLE:
            return "the line store could not be read, so the action fails closed"
        if self.source == SOURCE_DEFAULT:
            return "no line is set for this action; an unset line counts as line 2"
        if self.source == SOURCE_UNMANAGED:
            return "no line is set and the action does not change anything"
        return f"line {self.line.rank} is set for this action"


def resolve_line(
    key: str,
    *,
    stored: Optional[AiLine],
    mutating: bool,
    baseline_category: Optional[str] = None,
    role_requires_approval: bool = False,
    store_unavailable: bool = False,
    scope_missing: bool = False,
) -> LineResolution:
    """Decide the effective line for one action. Pure; every floor can only tighten.

    * A stored line wins over the default. ``never`` is final.
    * Unset: a mutating action counts as line 2; an action that changes nothing is not managed
      (autonomous), because gating every read would hold the conversation itself.
    * A baseline-sensitive category (#18294), when the caller supplies one, can never be line 1, whatever is stored.
    * A role policy that requires approval (#17463) can never be line 1 either.
    * An unreadable store fails closed: ``never``.
    * No verifiable scope (a malformed company, or no principal at all) refuses a mutating action: there is no scope
      its line could be read from, and the request's own claim is not one (#18430).
    """
    if scope_missing and mutating:
        return LineResolution(key, AiLine.NEVER, SOURCE_NO_COMPANY)
    if store_unavailable:
        return LineResolution(key, AiLine.NEVER, SOURCE_UNAVAILABLE)
    if stored is AiLine.NEVER:
        return LineResolution(key, AiLine.NEVER, SOURCE_STORED, stored)
    base, source = (stored, SOURCE_STORED) if stored else _unset(mutating)
    if base is AiLine.AUTONOMOUS and baseline_category:
        return LineResolution(key, DEFAULT_LINE, SOURCE_BASELINE, stored, baseline_category)
    if base is AiLine.AUTONOMOUS and role_requires_approval:
        return LineResolution(key, DEFAULT_LINE, SOURCE_ROLE, stored)
    return LineResolution(key, base, source, stored, baseline_category)


def _unset(mutating: bool) -> tuple[AiLine, str]:
    return (DEFAULT_LINE, SOURCE_DEFAULT) if mutating else (AiLine.AUTONOMOUS, SOURCE_UNMANAGED)
