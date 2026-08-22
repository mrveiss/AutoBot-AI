# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One-time backfill of tenancy scoping onto legacy agent sessions (#14756).

#12685 gave LLC agent conversations first-class ``company_id`` / ``session_kind``
metadata and filtered them out of the general ``GET /api/chat/sessions`` list.
Sessions created before that carry neither field, so they still appear there —
including the one named in #12685's reproduction.

They were deliberately not reclassified on read. The only signal a legacy agent
session carries is its display title (``"CEO · <company_id>"``), and matching on
a title is precisely the fragility #12685 removed; rebuilding the guard on it
would put the bug back inside the fix. So this is an explicit, operator-run
backfill instead of an implicit filter.

**What makes a classification confident rather than a guess.** The title alone is
not enough. A session is only tagged when the id parsed out of its title
resolves to a company that actually exists. A user who happens to name a chat
``"CEO · notes"`` — or even ``"CEO · <a uuid that is not a company>"`` — is
reported and left alone. A heuristic that silently *hides* someone's
conversation is worse than one that leaves an agent conversation visible, so
every ambiguous case fails towards visible.

Additive and idempotent: it only ever writes the two scoping fields, via
``update_session_metadata`` (which merges rather than replaces, #12129), and
skips any session that already carries either field. Nothing is deleted,
renamed, or moved.

Not auto-run: nothing here executes on import, there is no scheduled or Celery
hook, and the CLI defaults to a dry run. Writing requires ``--apply``.

Usage::

    python -m chat_history.session_scope_backfill              # dry run, writes nothing
    python -m chat_history.session_scope_backfill --apply

Like ``session_reply_backfill``, this is an unlocked read-modify-write: run it
when the sessions it touches have no concurrent writer.
"""

from __future__ import annotations

import argparse
import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Set

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

SESSION_KIND_AGENT = "agent"

# The title #12685's producer wrote: `CEO · ${company_id}` (CeoChatView.vue).
# The role half is captured but never trusted on its own — only the id is acted
# on, and only after it is confirmed to name a real company.
_AGENT_TITLE = re.compile(
    r"^(?P<role>[^\W\d_][\w .\-]*)\s+·\s+(?P<company_id>[0-9a-fA-F-]{8,})$",
    re.UNICODE,
)

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


@dataclass
class Candidate:
    """One legacy session and what the backfill decided about it."""

    session_id: str
    name: str
    company_id: str = ""
    reason: str = ""


@dataclass
class BackfillPlan:
    """What a dry run found. ``taggable`` is the only group that gets written."""

    taggable: List[Candidate] = field(default_factory=list)
    already_tagged: List[Candidate] = field(default_factory=list)
    unclassified: List[Candidate] = field(default_factory=list)

    @property
    def scanned(self) -> int:
        return len(self.taggable) + len(self.already_tagged) + len(self.unclassified)


def is_already_scoped(session: Dict[str, Any]) -> bool:
    """Mirrors ``api/chat_sessions._is_agent_scoped_session``.

    Deliberately the same predicate the read path uses: a session this returns
    True for is one the existing filter already covers, so tagging it again
    would be a no-op write. Keeping the two in step is what makes a re-run
    idempotent.
    """
    return bool(session.get("companyId")) or session.get("sessionKind") == SESSION_KIND_AGENT


def classify(session: Dict[str, Any], known_company_ids: Set[str]) -> Candidate:
    """Decide what to do with one session. Pure — no I/O, no writes.

    The whole judgement of this backfill lives here so it can be tested and
    mutated directly, rather than inferred from what a run happened to write.
    """
    session_id = str(session.get("chatId") or "")
    name = str(session.get("name") or "")
    candidate = Candidate(session_id=session_id, name=name)

    if is_already_scoped(session):
        candidate.reason = "already carries scoping metadata"
        return candidate

    match = _AGENT_TITLE.match(name.strip())
    if match is None:
        candidate.reason = "title does not have the legacy agent shape"
        return candidate

    parsed = match.group("company_id").lower()
    if not _UUID.match(parsed):
        candidate.reason = "the id in the title is not a company id"
        return candidate
    if parsed not in known_company_ids:
        # The check that separates a confident classification from a guess: the
        # title says "CEO · <id>", but no such company exists, so this is a user
        # chat that merely looks like one.
        candidate.reason = "no company with that id exists"
        return candidate

    candidate.company_id = parsed
    candidate.reason = "legacy agent session for an existing company"
    return candidate


def build_plan(sessions: Iterable[Dict[str, Any]], known_company_ids: Set[str]) -> BackfillPlan:
    """Sort every session into exactly one bucket. Writes nothing."""
    plan = BackfillPlan()
    normalised = {str(cid).lower() for cid in known_company_ids}
    for session in sessions:
        candidate = classify(session, normalised)
        if candidate.company_id:
            plan.taggable.append(candidate)
        elif is_already_scoped(session):
            plan.already_tagged.append(candidate)
        else:
            plan.unclassified.append(candidate)
    return plan


async def apply_plan(plan: BackfillPlan, chat_mgr) -> int:
    """Write the scoping fields for every taggable session. Returns count written.

    Only ``company_id`` and ``session_kind`` are written, through
    ``update_session_metadata``, which merges into the existing metadata rather
    than replacing it — nothing else about the session is touched.
    """
    written = 0
    for candidate in plan.taggable:
        ok = await chat_mgr.update_session_metadata(
            candidate.session_id,
            {"company_id": candidate.company_id, "session_kind": SESSION_KIND_AGENT},
        )
        if ok:
            written += 1
        else:
            logger.error(
                "Could not write scoping metadata for session %s — leaving it untagged",
                candidate.session_id,
            )
    return written


async def load_known_company_ids() -> Set[str]:
    """Every organization id, so a title's id can be confirmed against reality."""
    from sqlalchemy import text

    from user_management.database import get_async_session_factory

    factory = get_async_session_factory()
    async with factory() as session:
        result = await session.execute(text("SELECT id FROM organizations"))
        return {str(row[0]).lower() for row in result.fetchall()}


def render(plan: BackfillPlan, *, applied: int | None = None) -> str:
    """A report an operator can read before deciding to apply it."""
    lines = [
        f"scanned {plan.scanned} sessions",
        f"  taggable       {len(plan.taggable)}",
        f"  already tagged {len(plan.already_tagged)}",
        f"  unclassified   {len(plan.unclassified)} (left untouched)",
    ]
    if plan.taggable:
        lines.append("\ntaggable:")
        lines += [f"  {c.session_id}  {c.name!r} -> company {c.company_id}" for c in plan.taggable]
    if plan.unclassified:
        lines.append("\nunclassified (reported, never guessed):")
        lines += [f"  {c.session_id}  {c.name!r} — {c.reason}" for c in plan.unclassified]
    if applied is None:
        lines.append("\nDRY RUN — nothing was written. Re-run with --apply to write.")
    else:
        lines.append(f"\napplied: {applied} session(s) tagged")
    return "\n".join(lines)


async def _main(apply_changes: bool) -> None:
    from chat_history import ChatHistoryManager

    chat_mgr = ChatHistoryManager()
    sessions = await chat_mgr.list_sessions()
    plan = build_plan(sessions, await load_known_company_ids())

    # Reported through the logger, not print(), matching
    # `session_reply_backfill` and `workflow_redis_backfill` — the two existing
    # operator-run backfills — and the repo's logging standard.
    if not apply_changes:
        logger.info("%s", render(plan))
        return
    written = await apply_plan(plan, chat_mgr)
    logger.info("%s", render(plan, applied=written))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill company_id/session_kind onto legacy agent chat sessions (#14756).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the metadata. Without this the run reports and changes nothing.",
    )
    args = parser.parse_args()
    asyncio.run(_main(args.apply))


if __name__ == "__main__":
    main()
