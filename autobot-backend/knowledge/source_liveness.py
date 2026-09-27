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

import asyncio
import errno
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

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

#: Per-probe ceiling. A `stat` on a healthy mount answers in microseconds; this
#: bound exists entirely for the unhealthy case, which is the case this module is
#: FOR -- a hard NFS or SMB mount whose server has gone away blocks in the kernel
#: for minutes. `TimingConstants.SHORT_TIMEOUT` (30s) is the wrong order of
#: magnitude for one stat, and reusing a "delay" constant as a timeout would be
#: worse than a local one. Not env-configurable: `ssot_config.py` sits at its
#: 3307-line ratchet ceiling, so a new key cannot be added without splitting it
#: -- recorded rather than hidden (#17615 review).
PROBE_TIMEOUT_SECONDS = 2.0

#: Bounded, module-private, and deliberately NOT the default executor.
#: `asyncio.wait_for` cancels the *wait*, never an `os.stat` already blocked in
#: the kernel, so a hung mount leaks one worker until the kernel returns. A
#: separate bounded pool means those leaks cannot starve unrelated work sharing
#: the loop's default executor, and the bound caps how many can leak at once.
_PROBE_WORKERS = 4

_probe_pool: ThreadPoolExecutor | None = None


def _pool() -> ThreadPoolExecutor:
    """The probe pool, created on first use and never shut down on a request.

    Shutting it down with `wait=True` from a request path would block on exactly
    the hung stat the timeout exists to escape.
    """
    global _probe_pool
    if _probe_pool is None:
        _probe_pool = ThreadPoolExecutor(max_workers=_PROBE_WORKERS, thread_name_prefix="source-liveness")
    return _probe_pool


async def probe_path_async(path: str | None) -> str:
    """`probe_path` off the event loop, with a per-probe ceiling.

    The synchronous probe blocks, and the paths it touches are the ones most
    likely to block -- so running it inline would let one dead mount stall every
    other request served by that worker. A timeout is reported as `unreadable`:
    not looking is never evidence of absence.
    """
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(loop.run_in_executor(_pool(), probe_path, path), timeout=PROBE_TIMEOUT_SECONDS)
    except (asyncio.TimeoutError, TimeoutError):
        logger.warning("Source-liveness probe timed out after %ss; recording unreadable", PROBE_TIMEOUT_SECONDS)
        return PROBE_UNREADABLE


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
    """Whether the locator's parent is a resolvable **directory**.

    An unmounted or unreachable share reports the child's absence identically to
    a deleted file, so this is what separates the two.

    `isdir`, not a bare `stat` (#17615 review): for `/some-regular-file/child`,
    `os.stat` on the child raises ENOTDIR -- which is in `_ABSENCE_ERRNOS` -- and
    a bare stat of the parent then SUCCEEDS, because the parent is a file that
    exists. That reported `absent`, i.e. positive evidence that a document was
    deleted, for a locator that was never a valid path. A parent that is not a
    directory cannot tell us anything about a child, so it is unresolvable.
    """
    return os.path.isdir(os.path.dirname(path) or os.sep)


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
    """Least-recently-probed facts that carry a `file_path` key at all.

    Selects the id and the RAW metadata, not the ORM object: the read
    transaction closes before any probing starts, and one rule -- `locator_of` --
    then decides usability in Python. The SQL narrows candidates; it does not get
    a second opinion on what counts as a locator (#17615 review).

    `has_key`, not `->> IS NOT NULL`: the two disagreed. The old form selected a
    row whose `file_path` was `""` or a number, `locator_of` then rejected it, the
    loop skipped it without writing, `source_checked_at` stayed NULL, and with
    `nullsfirst` that row sorted first in EVERY later sweep -- a page of them
    would starve the sweep permanently. Candidacy and usability are now separate
    questions with one rule each.

    Facts with a witnessed deletion are skipped: re-probing cannot un-witness the
    event, and letting a later `resolved` probe sit beside `source_gone_at` would
    make the row say two things. A source that genuinely returns comes back
    through an ingest, not through this sweep.
    """
    return (
        select(KnowledgeFact.id, KnowledgeFact.metadata_json)
        .where(KnowledgeFact.metadata_json.has_key(LOCATOR_KEY))  # noqa: W601 - JSONB `?`, not dict.has_key
        .where(KnowledgeFact.source_gone_at.is_(None))
        .order_by(KnowledgeFact.source_checked_at.asc().nullsfirst())
        .limit(limit)
    )


async def sweep_source_liveness(*, limit: int = DEFAULT_SWEEP_LIMIT) -> Dict[str, Any]:
    """Probe a page of locators and record what each look established.

    Three phases on purpose (#17615 review). The earlier version held ONE session
    across the row query, every probe and the commit -- so a page containing a
    dead mount kept a database transaction open for as long as the kernel took to
    answer. Reading first, probing outside any transaction, then writing in a
    short one means a stalled filesystem costs no database time.

    Returns the per-outcome counts for this page, plus two discard counts:
    ``superseded`` (a newer sweep had already recorded a look) and ``relocated``
    (the fact's locator changed between the probe and the write). Both are
    reported rather than swallowed -- `probed` counts what was probed, not what
    was written, and a caller comparing the two would otherwise be reading a
    silent discrepancy.

    ``started_at`` and ``finished_at`` bound the sweep. Neither is the timestamp
    written to a row: each observation carries the instant its own probe returned,
    which on a page containing a dead mount is minutes from either bound.

    Nothing is deleted and no field outside the four observation columns is
    written.
    """
    factory = get_async_session_factory()

    # 1. Read the candidates, then let the read transaction go.
    async with factory() as session:
        candidates: List[Tuple[str, Dict[str, Any]]] = [
            (fact_id, metadata or {}) for fact_id, metadata in (await session.execute(_sweep_query(limit))).all()
        ]

    # 2. Probe with no transaction held and no blocking on the event loop. An
    #    unusable locator is NOT skipped -- `probe_path` reports it `unreadable`,
    #    which records an observation and lets the page make progress.
    #
    #    Each probe carries its OWN completion timestamp and the locator it
    #    actually looked at (#17615 review). One timestamp for the whole page was
    #    wrong twice over: it is not when the probe happened -- a page of 2s
    #    timeouts understates by the page's duration -- and it made the ordering
    #    guard below compare the wrong instants, so a LATER successful probe from
    #    a sweep that started earlier was discarded as stale and `source_seen_at`
    #    stayed older than a sighting that really occurred.
    started_at = datetime.now(tz=timezone.utc)
    counts: Dict[str, int] = {outcome: 0 for outcome in PROBE_OUTCOMES}
    observed: List[Tuple[str, str, str | None, datetime]] = []
    for fact_id, metadata in candidates:
        probed_locator = locator_of(metadata)
        outcome = await probe_path_async(probed_locator)
        counts[outcome] += 1
        observed.append((fact_id, outcome, probed_locator, datetime.now(tz=timezone.utc)))

    # 3. Persist in a short write transaction, one row at a time under a lock.
    #
    #    Two sweeps can select the same page, and nothing serialises them (#17615
    #    review). Without the lock and the timestamp comparison a SLOW sweep
    #    commits after a fast one and writes its OLDER observation on top:
    #    `source_checked_at` moves backwards, `source_last_probe` reports a probe
    #    that has since been superseded, and `source_check_failures` -- a
    #    read-modify-write -- loses an increment, so two consecutive failures
    #    count as one. `source_seen_at` going backwards is the dangerous one,
    #    because #17538's retention policy reads it as "last known good".
    #
    #    `with_for_update` serialises the read-modify-write; the comparison makes
    #    the write monotonic even across processes that never contend for the lock
    #    at the same instant. The SQLite dialect omits FOR UPDATE rather than
    #    failing on it, so a test database is unaffected.
    #
    #    The locator is re-read under the lock and compared with the one probed:
    #    `update_fact` can move a fact's `file_path` while the sweep is probing,
    #    and an observation of the OLD document applied to the NEW locator would
    #    mark a path `resolved` that nothing looked at. That is the exact
    #    mis-attribution this module exists to prevent, so the observation is
    #    dropped -- and counted, not swallowed.
    stale = 0
    relocated = 0
    if observed:
        async with factory() as session:
            for fact_id, outcome, probed_locator, observed_at in observed:
                row = await session.get(KnowledgeFact, fact_id, with_for_update=True)
                if row is None:
                    continue
                if locator_of(row.metadata_json) != probed_locator:
                    relocated += 1
                    continue
                if row.source_checked_at is not None and row.source_checked_at >= observed_at:
                    # A newer sweep already recorded a look at this fact. Dropping
                    # the write is correct; dropping it SILENTLY is not, so it is
                    # counted and returned.
                    stale += 1
                    continue
                apply_observation(row, outcome, now=observed_at)
            await session.commit()

    finished_at = datetime.now(tz=timezone.utc)
    logger.info(
        "Source-liveness sweep probed %d locator(s): %s (%d superseded, %d relocated mid-probe)",
        sum(counts.values()),
        counts,
        stale,
        relocated,
    )
    return {
        "probed": sum(counts.values()),
        "outcomes": counts,
        "superseded": stale,
        "relocated": relocated,
        "limit": limit,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
    }


def _census_rows(rows: Iterable[Any]) -> Dict[str, Any]:
    """Fold selected columns into per-ingest-class state counts.

    Takes the RAW metadata and applies `locator_of` / `ingest_class_of`, the same
    predicates `state_of` uses. The earlier version pulled both out in SQL with
    `.astext`, which coerces a JSON number to a string (#17615 review): a
    `file_path` of `7` became `"7"`, so the census read it as a locator while
    `state_of` called the row `no_locator`, and an ingest class of `7` opened a
    `"7"` bucket while `ingest_class_of` defines non-strings as `"unknown"`. Two
    rules for one question, in the same module -- the divergence this repository
    keeps paying for.

    The state is derived in Python rather than in SQL for the same reason: a CASE
    expression would be a second copy of `derive_source_state`.
    """
    by_class: Dict[str, Dict[str, int]] = defaultdict(lambda: {state: 0 for state in SOURCE_STATES})
    states: Dict[str, int] = {state: 0 for state in SOURCE_STATES}
    total = 0
    for metadata, checked_at, last_probe, gone_at in rows:
        metadata = metadata or {}
        state = derive_source_state(
            has_locator=locator_of(metadata) is not None,
            checked_at=checked_at,
            last_probe=last_probe,
            gone_at=gone_at,
        )
        by_class[ingest_class_of(metadata)][state] += 1
        states[state] += 1
        total += 1
    return {"total": total, "states": states, "by_ingest_class": dict(by_class)}


async def source_liveness_census() -> Dict[str, Any]:
    """How many facts have lost their source -- the #17538 measurement.

    ``never_checked`` and ``no_locator`` are reported as their own buckets and are
    never folded into ``resolved`` or ``absent``: *did not look* and *nothing to
    look at* are both different from *looked and found nothing*.

    Selects whole `metadata_json` rather than two `.astext` projections of it, so
    the locator and the ingest class are decided by the same predicates the row
    read uses. That costs reading the metadata for every fact, which is the price
    of having one rule instead of two.
    """
    query = select(
        KnowledgeFact.metadata_json,
        KnowledgeFact.source_checked_at,
        KnowledgeFact.source_last_probe,
        KnowledgeFact.source_gone_at,
    )
    factory = get_async_session_factory()
    async with factory() as session:
        rows = (await session.execute(query)).all()
    return _census_rows(rows)
