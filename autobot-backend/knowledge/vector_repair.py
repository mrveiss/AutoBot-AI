# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Repair of empty-document poisoning in the KB vector index (Issue #13277).

``BackgroundVectorizer._extract_fact_content`` read the fact hash with **bytes**
keys against a ``decode_responses=True`` client, so every fact the reconciler
touched was inserted as ``Document(text="")`` and then stamped
``vectorization_status=completed`` (#13274). The status stamp makes the row
invisible to the fixed reconciler — ``_filter_pending_facts`` skips
``completed`` — so the code fix cannot reach the existing damage.

Three properties of the write path, verified against the pinned
``chromadb``/``llama-index`` versions, shape this module:

1. **The reconciler's rows are not keyed by fact id.**
   ``VectorStoreIndex.insert(Document(doc_id=fact_id))`` splits the document
   into nodes and stores each node under a *fresh UUID*; the fact id survives
   only in the ``document_id`` / ``ref_doc_id`` / ``doc_id`` metadata. The
   inline path (``vector_store.add``) instead stores under the fact id itself.
   Poisoned rows must therefore be located by metadata, not by id.
2. **``collection.add`` on an existing id is a silent no-op** — no exception,
   the stored document keeps its old (empty) value. Re-vectorizing *over* a
   poisoned row whose id equals the fact id changes nothing while reporting
   success, so such a row is deleted before the rewrite.
3. **A poisoned orphan row is not replaced by a rewrite**, because the rewrite
   lands under a different id. It has to be deleted explicitly or it keeps
   polluting retrieval with an empty hit.

Nothing here is destructive by default: the caller must pass
``apply_changes=True``, and a fact is only ever cleaned up *after* a non-empty
replacement row has been observed in the store.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Sequence

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Page size for the read-only census walk over the collection. Env-tunable so a
# large collection can be scanned in smaller bites without a code change.
SCAN_PAGE_SIZE = max(1, int(os.environ.get("KB_VECTOR_REPAIR_SCAN_PAGE_SIZE", "500")))

# Metadata keys LlamaIndex writes on every ChromaDB row, in preference order,
# that carry the originating fact id.
FACT_ID_METADATA_KEYS = ("document_id", "ref_doc_id", "doc_id", "fact_id")

# Redis hash fields that record vectorization state on ``fact:<id>``.
VECTORIZATION_STATE_FIELDS = (
    "vectorization_status",
    "vectorized_at",
    "vectorization_error",
    "vectorization_failed_at",
)

# Outcome codes. Everything except REPAIRED / ALREADY_CLEAN / WOULD_REPAIR is a
# failure the operator has to look at — none of them are ever skipped quietly.
REPAIRED = "repaired"
ALREADY_CLEAN = "already_clean"
WOULD_REPAIR = "would_repair"
NO_REDIS_CONTENT = "no_redis_content"
REVECTORIZE_FAILED = "revectorize_failed"
VERIFY_FAILED = "verify_failed"

FAILURE_STATUSES = frozenset({NO_REDIS_CONTENT, REVECTORIZE_FAILED, VERIFY_FAILED})
_ALL_STATUSES = (REPAIRED, WOULD_REPAIR, ALREADY_CLEAN, NO_REDIS_CONTENT, REVECTORIZE_FAILED, VERIFY_FAILED)

# Signature of the injected re-vectorization coroutine, in production
# ``KnowledgeBase.vectorize_existing_fact``.
Revectorize = Callable[[str], Awaitable[Mapping[str, Any]]]


def is_empty_document(document: Any) -> bool:
    """True when a stored document carries no usable text.

    ``None`` and whitespace-only are treated as empty: both are unreachable by
    search and both are produced by the #13274 bug.
    """
    return document is None or not str(document).strip()


def fact_id_from_metadata(metadata: Mapping[str, Any] | None) -> str | None:
    """Recover the originating fact id from a row's LlamaIndex metadata."""
    for key in FACT_ID_METADATA_KEYS:
        value = (metadata or {}).get(key)
        if value:
            return str(value)
    return None


@dataclass(frozen=True)
class PoisonedRow:
    """A vector-store row whose document text is empty (#13277)."""

    row_id: str
    fact_id: str | None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def collides_with_fact_id(self) -> bool:
        """True when the row occupies the id a rewrite would target.

        ``collection.add`` is a silent no-op on an existing id, so such a row
        blocks its own replacement and must be deleted first.
        """
        return self.fact_id is not None and self.row_id == self.fact_id


@dataclass
class FactOutcome:
    """What happened (or would happen) to one fact."""

    fact_id: str
    status: str
    reason: str = ""
    poisoned_row_ids: List[str] = field(default_factory=list)
    deleted_row_ids: List[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return self.status in FAILURE_STATUSES


def _pad(values: Sequence[Any] | None, size: int) -> List[Any]:
    """Normalise an optional parallel column from a store response to ``size``."""
    column = list(values or [])
    return column + [None] * (size - len(column))


def _poisoned_from_page(page: Mapping[str, Any]) -> List[PoisonedRow]:
    """Select the empty-document rows out of one ``collection.get`` page."""
    ids = [str(row_id) for row_id in (page.get("ids") or [])]
    documents = _pad(page.get("documents"), len(ids))
    metadatas = _pad(page.get("metadatas"), len(ids))
    rows: List[PoisonedRow] = []
    for row_id, document, metadata in zip(ids, documents, metadatas):
        if not is_empty_document(document):
            continue
        rows.append(PoisonedRow(row_id=row_id, fact_id=fact_id_from_metadata(metadata), metadata=dict(metadata or {})))
    return rows


def scan_poisoned_rows(collection, page_size: int = SCAN_PAGE_SIZE) -> tuple[List[PoisonedRow], int]:
    """Walk the whole collection and return (poisoned rows, rows scanned).

    Read-only. This is the damage-quantification pass: it does not assume the
    reported mechanism, it counts rows whose stored document is actually empty.
    """
    rows: List[PoisonedRow] = []
    scanned = 0
    offset = 0
    while True:
        page = collection.get(include=["documents", "metadatas"], limit=page_size, offset=offset)
        batch_size = len(page.get("ids") or [])
        if not batch_size:
            break
        rows.extend(_poisoned_from_page(page))
        scanned += batch_size
        offset += batch_size
        if batch_size < page_size:
            break
    logger.info("Vector index scan: %d rows examined, %d with an empty document", scanned, len(rows))
    return rows, scanned


def group_by_fact(rows: Iterable[PoisonedRow]) -> tuple[Dict[str, List[PoisonedRow]], List[str]]:
    """Group poisoned rows by fact id, separating rows that name no fact.

    Unlinked rows are returned rather than dropped — they are junk in the index
    that no fact rewrite can replace, and the operator has to see them.
    """
    grouped: Dict[str, List[PoisonedRow]] = {}
    unlinked: List[str] = []
    for row in rows:
        if row.fact_id is None:
            unlinked.append(row.row_id)
            continue
        grouped.setdefault(row.fact_id, []).append(row)
    return grouped, unlinked


def _text(value: Any) -> str:
    """Decode a Redis hash field that may arrive as bytes or str."""
    return value.decode("utf-8") if isinstance(value, bytes) else str(value or "")


def has_reachable_vector(collection, fact_id: str) -> bool:
    """True when *some* non-empty row in the store represents this fact.

    Checks both write shapes: the inline path stores under the fact id, the
    reconciler path stores under a node UUID that references the fact id in
    metadata.
    """
    by_id = collection.get(ids=[fact_id], include=["documents"])
    if any(not is_empty_document(doc) for doc in (by_id.get("documents") or [])):
        return True
    for key in ("document_id", "ref_doc_id"):
        found = collection.get(where={key: fact_id}, include=["documents"])
        if any(not is_empty_document(doc) for doc in (found.get("documents") or [])):
            return True
    return False


def count_unreachable(collection, fact_ids: Iterable[str]) -> List[str]:
    """Return the subset of *fact_ids* with no non-empty row in the store."""
    return [fact_id for fact_id in fact_ids if not has_reachable_vector(collection, fact_id)]


class FactStateStore:
    """Redis-side view of a fact's content and vectorization state (#13277)."""

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def read(self, fact_id: str) -> Dict[str, str]:
        """Return the decoded ``fact:<id>`` hash (empty dict when absent)."""
        raw = await asyncio.to_thread(self._redis.hgetall, "fact:%s" % fact_id)
        return {_text(key): _text(value) for key, value in (raw or {}).items()}

    async def mark_for_retry(self, fact_id: str) -> None:
        """Drop the false ``completed`` stamp and re-queue the fact.

        Only called when a repair attempt failed. Leaving the stamp in place is
        exactly what made the damage permanent (#13274), so a failed repair must
        at minimum restore the fact to the retriable state #12312 intended.
        """
        from background_vectorization import PENDING_SET_KEY

        await asyncio.to_thread(self._redis.hdel, "fact:%s" % fact_id, *VECTORIZATION_STATE_FIELDS)
        await asyncio.to_thread(self._redis.sadd, PENDING_SET_KEY, fact_id)
        logger.warning("Fact %s could not be repaired — cleared status and re-queued for the reconciler", fact_id)


@dataclass
class RepairReport:
    """Before/after evidence for one repair run (#13277)."""

    scope: List[str] = field(default_factory=list)
    unlinked_row_ids: List[str] = field(default_factory=list)
    unreachable_before: List[str] = field(default_factory=list)
    unreachable_after: List[str] = field(default_factory=list)
    outcomes: List[FactOutcome] = field(default_factory=list)
    rows_scanned: int = 0
    poisoned_rows_found: int = 0
    applied: bool = False

    @property
    def failures(self) -> List[FactOutcome]:
        return [outcome for outcome in self.outcomes if outcome.failed]

    def by_status(self, status: str) -> List[FactOutcome]:
        return [outcome for outcome in self.outcomes if outcome.status == status]

    @property
    def touched_fact_ids(self) -> List[str]:
        return [outcome.fact_id for outcome in self.outcomes if outcome.deleted_row_ids or outcome.status == REPAIRED]


class VectorIndexRepair:
    """Rebuild the vectors of facts poisoned with empty documents (#13277).

    Dry-run unless ``apply_changes=True``. Deletion of a poisoned row only ever
    happens once a non-empty replacement has been observed, except for the row
    that squats on the fact id itself — that one blocks its own replacement and
    is empty by definition, so nothing is lost by removing it first.
    """

    def __init__(self, collection, store: FactStateStore, revectorize: Revectorize, *, apply_changes: bool = False):
        self._collection = collection
        self._store = store
        self._revectorize = revectorize
        self._apply = apply_changes

    async def repair_fact(self, fact_id: str, rows: Sequence[PoisonedRow]) -> FactOutcome:
        """Repair a single fact. Never raises; every failure becomes an outcome."""
        row_ids = [row.row_id for row in rows]
        if not rows:
            return FactOutcome(fact_id, ALREADY_CLEAN, "no empty-document rows reference this fact")

        content = (await self._store.read(fact_id)).get("content", "").strip()
        if not content:
            reason = "fact:%s has no content in Redis — the vector cannot be rebuilt from it" % fact_id
            logger.error("UNREPAIRABLE %s: %s", fact_id, reason)
            return FactOutcome(fact_id, NO_REDIS_CONTENT, reason, row_ids)

        if not self._apply:
            return FactOutcome(
                fact_id, WOULD_REPAIR, "would delete %d empty row(s) and re-vectorize" % len(rows), row_ids
            )

        return await self._apply_repair(fact_id, rows, row_ids)

    async def _apply_repair(self, fact_id: str, rows: Sequence[PoisonedRow], row_ids: List[str]) -> FactOutcome:
        """Delete blocking rows, rewrite the vector, verify, then clean orphans."""
        blocking = [row for row in rows if row.collides_with_fact_id]
        orphans = [row for row in rows if not row.collides_with_fact_id]

        deleted = self._delete_rows(fact_id, blocking)

        failure = await self._rewrite_vector(fact_id)
        if failure:
            await self._store.mark_for_retry(fact_id)
            return FactOutcome(fact_id, REVECTORIZE_FAILED, failure, row_ids, deleted)

        if not has_reachable_vector(self._collection, fact_id):
            reason = "re-vectorization reported success but no non-empty row is present for %s" % fact_id
            logger.error("VERIFICATION FAILED %s: %s", fact_id, reason)
            await self._store.mark_for_retry(fact_id)
            return FactOutcome(fact_id, VERIFY_FAILED, reason, row_ids, deleted)

        deleted += self._delete_rows(fact_id, orphans)
        logger.info("Repaired fact %s — removed %d empty row(s)", fact_id, len(deleted))
        return FactOutcome(fact_id, REPAIRED, "", row_ids, deleted)

    def _delete_rows(self, fact_id: str, rows: Sequence[PoisonedRow]) -> List[str]:
        """Delete empty rows by explicit id. Raises rather than hiding a failure."""
        row_ids = [row.row_id for row in rows]
        if not row_ids:
            return []
        self._collection.delete(ids=row_ids)
        logger.info("Deleted %d empty vector row(s) for fact %s: %s", len(row_ids), fact_id, row_ids)
        return row_ids

    async def _rewrite_vector(self, fact_id: str) -> str:
        """Re-vectorize *fact_id*. Returns "" on success, else a failure reason.

        The exception is converted to a reported reason, not swallowed: it is
        logged at error level and surfaces as a REVECTORIZE_FAILED outcome that
        drives a non-zero exit code.
        """
        try:
            result = await self._revectorize(fact_id)
        except Exception as exc:  # noqa: BLE001 - reported as a failure reason, never dropped
            logger.exception("Re-vectorization of fact %s raised", fact_id)
            return "re-vectorization raised %s: %s" % (type(exc).__name__, exc)

        status = (result or {}).get("status")
        if status != "success":
            return "re-vectorization returned status=%r message=%r" % (status, (result or {}).get("message"))
        return ""


def _resolve_scope(grouped: Mapping[str, List[PoisonedRow]], fact_ids: Sequence[str] | None) -> List[str]:
    """Determine which facts this run covers.

    ``fact_ids=None`` is a census over everything the scan found and is only
    ever reachable in dry-run mode — there is deliberately no implicit
    "repair everything" path.
    """
    if fact_ids is None:
        return sorted(grouped)
    return sorted(dict.fromkeys(fact_ids))


def _survey(
    collection, fact_ids: Sequence[str] | None, apply_changes: bool, page_size: int
) -> tuple[Dict[str, List[PoisonedRow]], RepairReport]:
    """Read-only pass: find the damage and record the "before" evidence."""
    rows, scanned = scan_poisoned_rows(collection, page_size=page_size)
    grouped, unlinked = group_by_fact(rows)
    scope = _resolve_scope(grouped, fact_ids)
    report = RepairReport(
        scope=scope,
        unlinked_row_ids=unlinked,
        rows_scanned=scanned,
        poisoned_rows_found=len(rows),
        applied=apply_changes,
        unreachable_before=count_unreachable(collection, scope),
    )
    return grouped, report


async def run_repair(
    collection,
    store: FactStateStore,
    revectorize: Revectorize,
    *,
    fact_ids: Sequence[str] | None = None,
    apply_changes: bool = False,
    page_size: int = SCAN_PAGE_SIZE,
) -> RepairReport:
    """Scan, quantify and (optionally) repair empty-document poisoning.

    Raises ``ValueError`` when a write run is requested without an explicit
    scope: bulk repair is not an available mode.
    """
    if apply_changes and not fact_ids:
        raise ValueError("a write run requires an explicit fact-id scope; bulk repair is not supported")

    grouped, report = _survey(collection, fact_ids, apply_changes, page_size)
    engine = VectorIndexRepair(collection, store, revectorize, apply_changes=apply_changes)
    for fact_id in report.scope:
        report.outcomes.append(await engine.repair_fact(fact_id, grouped.get(fact_id, [])))
    report.unreachable_after = (
        count_unreachable(collection, report.scope) if apply_changes else report.unreachable_before
    )
    return report


def _render_failures(report: RepairReport) -> List[str]:
    """One line per unrepaired fact — never collapsed into a count."""
    lines = ["", "FAILURES (%d) — these facts are still unreachable:" % len(report.failures)]
    for outcome in report.failures:
        lines.append("  %s  [%s] %s" % (outcome.fact_id, outcome.status, outcome.reason))
    return lines


def render_report(report: RepairReport) -> List[str]:
    """Human-readable before/after evidence, printed by the tool itself."""
    mode = "APPLY" if report.applied else "DRY-RUN (no changes written)"
    lines = [
        "=" * 72,
        "KB vector index repair (#13277) — %s" % mode,
        "=" * 72,
        "Vector rows examined            : %d" % report.rows_scanned,
        "Rows with an empty document     : %d" % report.poisoned_rows_found,
        "Distinct facts in scope         : %d" % len(report.scope),
        "Empty rows naming no fact       : %d" % len(report.unlinked_row_ids),
        "Unreachable facts BEFORE        : %d" % len(report.unreachable_before),
        "Unreachable facts AFTER         : %d" % len(report.unreachable_after),
        "",
        "Outcomes: %s" % (", ".join("%s=%d" % (s, len(report.by_status(s))) for s in _ALL_STATUSES) or "none"),
    ]
    if report.touched_fact_ids:
        lines += ["", "Fact ids touched (%d):" % len(report.touched_fact_ids)]
        lines += ["  %s" % fact_id for fact_id in report.touched_fact_ids]
    if report.unlinked_row_ids:
        lines += ["", "Empty rows with no recoverable fact id (%d):" % len(report.unlinked_row_ids)]
        lines += ["  %s" % row_id for row_id in report.unlinked_row_ids]
    if report.failures:
        lines += _render_failures(report)
    return lines
