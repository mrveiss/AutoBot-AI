# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Does the document a fact came from still exist? (#17545)

#17538 orders the retention work **detect -> measure -> build**, because the size
of a retention tier depends entirely on how often sources actually vanish, and
nothing measured that: no fact recorded anything about its source, so no query
could name the facts that had lost their evidence.

Two kinds of knowledge live on the fact row and this module writes only one of
them. ``source_checked_at`` / ``source_seen_at`` / ``source_last_probe`` /
``source_check_failures`` are **observations** written here. ``source_gone_at``
is an **event**, written only when a deletion was witnessed (#17546's watchdog
handlers), and **never** by anything in this file -- an event set by inference
launders a judgement into a fact, and once it carries a timestamp everything
downstream treats a threshold's output as something someone saw.

The rule that makes the distinction work: **an unmounted share answers ENOENT
for every path beneath it.** A missing file whose parent directory is also
unresolvable is evidence of nothing, so the parent is probed before the child's
absence is believed. ``os.path.exists`` cannot express this -- it returns False
for a missing file *and* for one whose parent denies traversal -- so the probe
reads ``errno`` instead.

No threshold lives here either. The detector reports the evidence (``absent``,
and how many probes in a row said so); *how much is enough* is the consumer's
retention policy (#17538). A detector that decides "confirmed missing" has made
the policy call invisible.

Scope: filesystem locators only. Probing a URL read from stored config is an
outbound request that must go through the guarded fetch with an egress policy,
so it is deliberately not attempted here.
"""

from __future__ import annotations

import errno
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from sqlalchemy import select

from autobot_shared.logging_manager import get_logger
from autobot_shared.store_authority import Store, system_of_record
from models.knowledge_fact import KnowledgeFact
from user_management.database import get_async_session_factory

logger = get_logger(__name__)

#: Declared beside the code that writes the row, like every other write site for
#: this concept -- the authority is one jump from the write, not in a document.
SYSTEM_OF_RECORD = system_of_record("knowledge_facts")
assert SYSTEM_OF_RECORD.system_of_record is Store.POSTGRES  # nosec B101

#: The metadata key carrying a filesystem locator. `kb_folder_watcher` writes it
#: for every watch-folder ingest; nothing else has to be taught about it.
LOCATOR_KEY = "file_path"

#: The metadata key naming the ingest class -- `watch_folder`, `uploads`, ... --
#: which is the axis #17538's retention policy is written per.
INGEST_CLASS_KEY = "source"

#: How many facts one sweep probes. A page size, not a policy: sweeps order by
#: least-recently-checked so repeated runs make progress through the table.
DEFAULT_SWEEP_LIMIT = 500

# ---------------------------------------------------------------------------
# Probe outcomes -- what a single look at a locator established
# ---------------------------------------------------------------------------

#: The locator resolved.
PROBE_RESOLVED = "resolved"
#: The file is not there **and its parent is**: the only outcome that is
#: positive evidence of absence.
PROBE_ABSENT = "absent"
#: The probe could not see whether the file exists -- a permission error, a
#: stale handle, a dead mount, an unusable locator. Not evidence.
PROBE_UNREADABLE = "unreadable"
#: The file is not there and neither is its parent: the unmounted-share case.
#: Not evidence.
PROBE_PARENT_UNRESOLVABLE = "parent_unresolvable"

PROBE_OUTCOMES = (
    PROBE_RESOLVED,
    PROBE_ABSENT,
    PROBE_UNREADABLE,
    PROBE_PARENT_UNRESOLVABLE,
)

#: The two errno values that mean "this path is not there". Everything else --
#: EACCES, EPERM, ESTALE, EIO, ELOOP, ETIMEDOUT and any value not enumerated --
#: falls to `unreadable` on purpose: the safe default is *not evidence*, so a
#: failure mode nobody anticipated can never read as a deleted document.
_ABSENCE_ERRNOS = (errno.ENOENT, errno.ENOTDIR)

# ---------------------------------------------------------------------------
# Derived states -- computed on read, never stored
# ---------------------------------------------------------------------------

#: A deletion was witnessed. Only #17546 writes the event this derives from.
STATE_GONE = "gone"
#: Probeable and never probed. Distinct from every other state: *did not look*
#: is not *looked and found nothing*.
STATE_NEVER_CHECKED = "never_checked"
#: The last probe resolved.
STATE_RESOLVED = "resolved"
#: The last probe was positive evidence of absence, not yet witnessed.
STATE_ABSENT = "absent"
#: The last probe could not tell. Recoverable, and never a reason to act.
STATE_UNREACHABLE = "unreachable"
#: The fact carries no filesystem locator, so there is nothing to probe. Kept
#: separate so a census can never imply these were checked and found fine.
STATE_NO_LOCATOR = "no_locator"

SOURCE_STATES = (
    STATE_GONE,
    STATE_NEVER_CHECKED,
    STATE_RESOLVED,
    STATE_ABSENT,
    STATE_UNREACHABLE,
    STATE_NO_LOCATOR,
)


def locator_of(metadata: Dict[str, Any] | None) -> str | None:
    """The filesystem locator a fact's metadata carries, or None."""
    path = (metadata or {}).get(LOCATOR_KEY)
    return path if isinstance(path, str) and path.strip() else None


def ingest_class_of(metadata: Dict[str, Any] | None) -> str:
    """The ingest class a fact's metadata names, or ``"unknown"``."""
    value = (metadata or {}).get(INGEST_CLASS_KEY)
    return value if isinstance(value, str) and value.strip() else "unknown"


def _parent_resolves(path: str) -> bool:
    """Whether the locator's parent directory can be stat'd at all.

    An unmounted or unreachable share reports the child's absence identically to
    a deleted file, so this is what separates the two.
    """
    try:
        os.stat(os.path.dirname(path) or os.sep)
        return True
    except OSError:
        return False


def probe_path(path: str | None) -> str:
    """Look at one filesystem locator and report what was established.

    Returns one of ``PROBE_OUTCOMES``. Only ``PROBE_ABSENT`` is evidence that
    the document is gone.
    """
    if not path or not os.path.isabs(path):
        # A relative locator cannot be resolved from a server process at all:
        # it would be read against whatever directory the backend happens to
        # run in. That is an unusable locator, not a missing document.
        return PROBE_UNREADABLE
    try:
        os.stat(path)
        return PROBE_RESOLVED
    except OSError as exc:
        if exc.errno not in _ABSENCE_ERRNOS:
            return PROBE_UNREADABLE
        return PROBE_ABSENT if _parent_resolves(path) else PROBE_PARENT_UNRESOLVABLE


def apply_observation(row: KnowledgeFact, outcome: str, *, now: datetime) -> None:
    """Record one probe on a fact row. Writes observations only.

    ``source_gone_at`` is untouched by design -- see this module's docstring.
    """
    row.source_checked_at = now
    row.source_last_probe = outcome
    if outcome == PROBE_RESOLVED:
        row.source_seen_at = now
        row.source_check_failures = 0
        return
    # A failure leaves `source_seen_at` exactly where it was: it is the record of
    # a successful observation, and a later failure does not un-observe it.
    row.source_check_failures = (row.source_check_failures or 0) + 1


def derive_source_state(
    *,
    has_locator: bool,
    checked_at: datetime | None,
    last_probe: str | None,
    gone_at: datetime | None,
) -> str:
    """The fact's source state, computed from the recorded observations.

    Never stored. Keeping it derived is what lets the rule be re-tuned or
    disagreed with later; a column would freeze today's reading of the evidence
    into something that reads as observed.
    """
    if gone_at is not None:
        return STATE_GONE
    if not has_locator:
        return STATE_NO_LOCATOR
    if checked_at is None:
        return STATE_NEVER_CHECKED
    if last_probe == PROBE_RESOLVED:
        return STATE_RESOLVED
    if last_probe == PROBE_ABSENT:
        return STATE_ABSENT
    return STATE_UNREACHABLE


def state_of(row: KnowledgeFact) -> str:
    """``derive_source_state`` for a loaded row."""
    return derive_source_state(
        has_locator=locator_of(row.metadata_json) is not None,
        checked_at=row.source_checked_at,
        last_probe=row.source_last_probe,
        gone_at=row.source_gone_at,
    )


def _sweep_query(limit: int):
    """Least-recently-probed facts that carry a filesystem locator.

    Facts with a witnessed deletion are skipped: re-probing cannot un-witness
    the event, and letting a later `resolved` probe sit beside `source_gone_at`
    would make the row say two things. A source that genuinely returns comes
    back through an ingest, not through this sweep.
    """
    locator = KnowledgeFact.metadata_json[LOCATOR_KEY].astext
    return (
        select(KnowledgeFact)
        .where(locator.isnot(None))
        .where(KnowledgeFact.source_gone_at.is_(None))
        .order_by(KnowledgeFact.source_checked_at.asc().nullsfirst())
        .limit(limit)
    )


async def sweep_source_liveness(*, limit: int = DEFAULT_SWEEP_LIMIT) -> Dict[str, Any]:
    """Probe a page of locators and record what each look established.

    Returns the per-outcome counts for this page. Nothing is deleted and no
    field outside the four observation columns is written.
    """
    now = datetime.now(tz=timezone.utc)
    counts: Dict[str, int] = {outcome: 0 for outcome in PROBE_OUTCOMES}
    factory = get_async_session_factory()
    async with factory() as session:
        rows = (await session.execute(_sweep_query(limit))).scalars().all()
        for row in rows:
            locator = locator_of(row.metadata_json)
            if locator is None:
                continue
            outcome = probe_path(locator)
            apply_observation(row, outcome, now=now)
            counts[outcome] += 1
        await session.commit()
    logger.info("Source-liveness sweep probed %d locator(s): %s", sum(counts.values()), counts)
    return {"probed": sum(counts.values()), "outcomes": counts, "limit": limit, "checked_at": now.isoformat()}


def _census_rows(rows: Iterable[Any]) -> Dict[str, Any]:
    """Fold selected columns into per-ingest-class state counts.

    The state is derived in Python rather than in SQL on purpose: a CASE
    expression would be a second copy of ``derive_source_state``, and two
    spellings of one rule is the defect this subsystem keeps producing.
    """
    by_class: Dict[str, Dict[str, int]] = defaultdict(lambda: {state: 0 for state in SOURCE_STATES})
    states: Dict[str, int] = {state: 0 for state in SOURCE_STATES}
    total = 0
    for ingest_class, checked_at, last_probe, gone_at, locator in rows:
        state = derive_source_state(
            has_locator=bool(locator),
            checked_at=checked_at,
            last_probe=last_probe,
            gone_at=gone_at,
        )
        by_class[ingest_class or "unknown"][state] += 1
        states[state] += 1
        total += 1
    return {"total": total, "states": states, "by_ingest_class": dict(by_class)}


async def source_liveness_census() -> Dict[str, Any]:
    """How many facts have lost their source -- the #17538 measurement.

    ``never_checked`` and ``no_locator`` are reported as their own buckets and
    are never folded into ``resolved`` or ``absent``: *did not look* and *nothing
    to look at* are both different from *looked and found nothing*.
    """
    query = select(
        KnowledgeFact.metadata_json[INGEST_CLASS_KEY].astext,
        KnowledgeFact.source_checked_at,
        KnowledgeFact.source_last_probe,
        KnowledgeFact.source_gone_at,
        KnowledgeFact.metadata_json[LOCATOR_KEY].astext,
    )
    factory = get_async_session_factory()
    async with factory() as session:
        rows = (await session.execute(query)).all()
    return _census_rows(rows)
