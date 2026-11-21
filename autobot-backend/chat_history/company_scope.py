# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which company a chat belongs to, and the one rule for what each company's chat list shows (#21997).

A session carries ``companyId`` (surfaced from ``metadata.company_id``); empty means *Unassigned*. Nothing here
writes a company: a chat is tagged only at creation (the active company) or by a person through
``POST /chat/sessions/{id}/company`` (audited). The rule, applied by every route that lists sessions:

* with an active company: ``sessions`` are the chats tagged with it, and ``unassigned`` the untagged ones;
* with none (a caller that names no company): ``sessions`` are the untagged chats, so nothing a caller could see
  before disappears, and a chat tagged with a company is never shown outside it.

Agent-kind conversations (``sessionKind == "agent"``, the Company OS CEO chat) are not ordinary chats and are in
neither set; they live in Company OS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

SESSION_KIND_AGENT = "agent"


def session_company(session: dict) -> str:
    """The company id on a session summary, lower-cased; ``""`` when it is Unassigned."""
    return str(session.get("companyId") or "").strip().lower()


def is_agent_kind(session: dict) -> bool:
    """A Company OS agent conversation (CEO chat), not an ordinary user chat (#12685)."""
    return session.get("sessionKind") == SESSION_KIND_AGENT


@dataclass(frozen=True)
class CompanyScope:
    """The company the caller is acting in (``None`` when they name none) and what it makes visible."""

    active: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "active", str(self.active).lower() if self.active else None)

    def split(self, sessions: Iterable[dict]) -> tuple[list[dict], list[dict]]:
        """``(sessions of the active company, Unassigned sessions)``; agent-kind and other companies' are in neither."""
        ordinary = [s for s in sessions if not is_agent_kind(s)]
        unassigned = [s for s in ordinary if not session_company(s)]
        scoped = [s for s in ordinary if session_company(s) == self.active] if self.active else list(unassigned)
        return scoped, unassigned

    def visible(self, sessions: Iterable[dict]) -> list[dict]:
        """Every session this scope lists in either set, once (what an export of the caller's chats carries)."""
        scoped, unassigned = self.split(sessions)
        shown = {id(s) for s in scoped}
        return scoped + [s for s in unassigned if id(s) not in shown]

    def listing(self, sessions: list[dict]) -> dict[str, Any]:
        """The list payload fields every listing route adds: the company's chats and the Unassigned set."""
        scoped, unassigned = self.split(sessions)
        return {
            "sessions": scoped,
            "count": len(scoped),
            "unassigned": unassigned,
            "unassigned_count": len(unassigned),
            "company_id": self.active,
        }

    def allows(self, session_company_id: str | None) -> bool:
        """Whether a session tagged *session_company_id* may be opened here: untagged, or tagged with the active one."""
        tagged = str(session_company_id or "").strip().lower()
        return not tagged or self.active is None or tagged == self.active
