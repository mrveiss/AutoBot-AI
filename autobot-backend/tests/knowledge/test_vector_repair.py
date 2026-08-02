# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Repair of empty-document vector poisoning (#13277).

The damage: ``BackgroundVectorizer`` inserted ``Document(text="")`` for every
fact it reconciled and stamped ``vectorization_status=completed`` (#13274), so
the fixed reconciler skips exactly the rows that need rewriting.

These tests pin the three write-path properties the repair depends on, using
the repo's own ``InMemoryCollection`` adapter — no live ChromaDB or Redis.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from typing import Any, Dict, List

import pytest

from knowledge.backends.memory_adapter import InMemoryCollection
from knowledge.vector_repair import (
    ALREADY_CLEAN,
    NO_REDIS_CONTENT,
    REPAIRED,
    REVECTORIZE_FAILED,
    VERIFY_FAILED,
    WOULD_REPAIR,
    PoisonedRow,
    fact_id_from_metadata,
    group_by_fact,
    has_reachable_vector,
    is_empty_document,
    render_report,
    run_repair,
    scan_poisoned_rows,
)

EMBEDDING = [0.1, 0.2, 0.3]

# Seconds allowed for the out-of-process real-chromadb probe below.
PROBE_TIMEOUT = 120


class FakeFactStore:
    """Stand-in for the Redis ``fact:<id>`` hash."""

    def __init__(self, facts: Dict[str, str]) -> None:
        self._facts = facts
        self.retried: List[str] = []

    async def read(self, fact_id: str) -> Dict[str, str]:
        content = self._facts.get(fact_id)
        return {"content": content} if content is not None else {}

    async def mark_for_retry(self, fact_id: str) -> None:
        self.retried.append(fact_id)


class FakeRevectorizer:
    """Mimics ``KnowledgeBase.vectorize_existing_fact`` on the fixed inline path.

    The inline path writes through ``vector_store.add`` with ``doc_id=fact_id``,
    so the replacement row lands under the fact id itself.
    """

    def __init__(self, store: FakeFactStore, collection, *, fail_with: Exception | None = None, succeed: bool = True):
        self._store = store
        self._collection = collection
        self._fail_with = fail_with
        self._succeed = succeed
        self.calls: List[str] = []

    async def __call__(self, fact_id: str) -> Dict[str, Any]:
        self.calls.append(fact_id)
        if self._fail_with is not None:
            raise self._fail_with
        if not self._succeed:
            return {"status": "error", "message": "embedding backend unavailable"}
        content = (await self._store.read(fact_id)).get("content", "")
        _chroma_add(self._collection, fact_id, content, fact_id)
        return {"status": "success", "vector_indexed": True, "fact_id": fact_id}


def _add(collection, row_id: str, document: str, fact_id: str) -> None:
    """Insert a reconciler-shape row: node UUID id, fact id in the reference keys."""
    metadata = {"document_id": fact_id, "ref_doc_id": fact_id, "doc_id": fact_id, "_node_type": "TextNode"}
    collection.upsert(ids=[row_id], embeddings=[EMBEDDING], documents=[document], metadatas=[metadata])


def _add_inline_shape(collection, fact_id: str, document: str) -> None:
    """Insert a row exactly as the inline writer produces it.

    ``node_to_metadata_dict`` writes ``node.ref_doc_id or "None"``, and the
    inline path builds a TextNode with no source relationship — so all three
    reference keys hold the *literal string* "None" and only ``fact_id`` carries
    the real id. Using ``_add`` here would hide that.
    """
    metadata = {"document_id": "None", "ref_doc_id": "None", "doc_id": "None", "fact_id": fact_id}
    collection.upsert(ids=[fact_id], embeddings=[EMBEDDING], documents=[document], metadatas=[metadata])


def _chroma_add(collection, row_id: str, document: str, fact_id: str) -> None:
    """Insert with real ``chromadb.Collection.add`` semantics: existing id -> silent no-op.

    Verified against the pinned chromadb: ``add`` on an id that already exists
    raises nothing and leaves the stored document untouched. Modelling that
    faithfully is what makes the pre-delete test meaningful.
    """
    if collection.get(ids=[row_id])["ids"]:
        return
    _add(collection, row_id, document, fact_id)


def _poisoned_collection() -> InMemoryCollection:
    """A collection carrying the exact damage shape #13274 produced.

    ``fact-a`` / ``fact-b`` are reconciler orphans (random node id, empty text),
    ``fact-c`` is healthy, and one empty row names no fact at all.
    """
    collection = InMemoryCollection("autobot_memory")
    _add(collection, "node-uuid-1", "", "fact-a")
    _add(collection, "node-uuid-2", "", "fact-b")
    _add(collection, "fact-c", "healthy content", "fact-c")
    collection.upsert(
        ids=["node-orphan"], embeddings=[EMBEDDING], documents=[""], metadatas=[{"_node_type": "TextNode"}]
    )
    return collection


def _wire(collection, facts: Dict[str, str], **kwargs):
    store = FakeFactStore(facts)
    return store, FakeRevectorizer(store, collection, **kwargs)


# --------------------------------------------------------------------------
# Mechanism: what the damage actually looks like
# --------------------------------------------------------------------------


@pytest.mark.parametrize("document", ["", "   ", None])
def test_empty_documents_are_detected(document):
    assert is_empty_document(document) is True


def test_real_content_is_not_flagged():
    assert is_empty_document("some content") is False


def test_fact_id_recovered_from_llamaindex_metadata():
    """The reconciler's rows are keyed by node UUID; the fact id lives in metadata."""
    assert fact_id_from_metadata({"document_id": "fact-a", "ref_doc_id": "fact-a"}) == "fact-a"
    assert fact_id_from_metadata({"ref_doc_id": "fact-b"}) == "fact-b"
    assert fact_id_from_metadata({"_node_type": "TextNode"}) is None


def test_literal_none_reference_is_not_a_fact_id():
    """llama-index writes the string "None" for an absent reference, not a fact.

    Reading it as an id buckets every inline-shape row under a phantom fact
    named ``None``, writes that into the scope file, and stops the row squatting
    on the real fact id from ever being recognised as blocking its own rewrite.
    """
    inline = {"document_id": "None", "doc_id": "None", "ref_doc_id": "None", "fact_id": "fact-real"}

    assert fact_id_from_metadata(inline) == "fact-real"
    assert fact_id_from_metadata({"document_id": "None", "doc_id": "None"}) is None
    assert fact_id_from_metadata({"document_id": "none"}) is None


def test_inline_shape_rows_group_under_their_real_fact():
    collection = InMemoryCollection("autobot_memory")
    _add_inline_shape(collection, "fact-inline", "")

    rows, _ = scan_poisoned_rows(collection)
    grouped, unlinked = group_by_fact(rows)

    assert sorted(grouped) == ["fact-inline"]
    assert unlinked == []
    assert grouped["fact-inline"][0].collides_with_fact_id is True


def test_scan_finds_only_empty_rows():
    rows, scanned = scan_poisoned_rows(_poisoned_collection(), page_size=2)
    assert scanned == 4
    assert {row.row_id for row in rows} == {"node-uuid-1", "node-uuid-2", "node-orphan"}


def test_scan_pages_through_the_whole_collection():
    """A page size smaller than the collection must not truncate the census."""
    collection = InMemoryCollection("autobot_memory")
    for index in range(25):
        _add(collection, "node-%d" % index, "", "fact-%d" % index)
    rows, scanned = scan_poisoned_rows(collection, page_size=4)
    assert scanned == 25
    assert len(rows) == 25


def test_unlinked_rows_are_reported_not_dropped():
    rows, _ = scan_poisoned_rows(_poisoned_collection())
    grouped, unlinked = group_by_fact(rows)
    assert sorted(grouped) == ["fact-a", "fact-b"]
    assert unlinked == ["node-orphan"]


def test_reachability_sees_both_write_shapes():
    collection = _poisoned_collection()
    _add(collection, "node-uuid-3", "reconciler-written content", "fact-d")
    assert has_reachable_vector(collection, "fact-c") is True  # inline shape, id == fact id
    assert has_reachable_vector(collection, "fact-d") is True  # node shape, metadata reference
    assert has_reachable_vector(collection, "fact-a") is False  # only an empty row


# --------------------------------------------------------------------------
# Dry-run is the default
# --------------------------------------------------------------------------


async def test_dry_run_writes_nothing():
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {"fact-a": "content a", "fact-b": "content b"})

    report = await run_repair(collection, store, revectorize)

    assert report.applied is False
    assert revectorize.calls == []
    assert collection.count() == 4
    assert [outcome.status for outcome in report.outcomes] == [WOULD_REPAIR, WOULD_REPAIR]


async def test_dry_run_quantifies_the_damage():
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {"fact-a": "content a", "fact-b": "content b"})

    report = await run_repair(collection, store, revectorize)

    assert report.rows_scanned == 4
    assert report.poisoned_rows_found == 3
    assert report.scope == ["fact-a", "fact-b"]
    assert sorted(report.unreachable_before) == ["fact-a", "fact-b"]
    assert report.unlinked_row_ids == ["node-orphan"]


async def test_bulk_write_is_refused():
    """No implicit "repair everything" mode — a write run must name its scope."""
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {"fact-a": "content a"})

    with pytest.raises(ValueError, match="explicit fact-id scope"):
        await run_repair(collection, store, revectorize, apply_changes=True)

    assert revectorize.calls == []


# --------------------------------------------------------------------------
# Applying the repair
# --------------------------------------------------------------------------


async def test_apply_rebuilds_the_vector_and_removes_the_empty_row():
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {"fact-a": "content a", "fact-b": "content b"})

    report = await run_repair(collection, store, revectorize, fact_ids=["fact-a"], apply_changes=True)

    outcome = report.outcomes[0]
    assert outcome.status == REPAIRED
    assert outcome.deleted_row_ids == ["node-uuid-1"]
    assert has_reachable_vector(collection, "fact-a") is True
    assert collection.get(ids=["node-uuid-1"])["ids"] == []


async def test_apply_reports_before_and_after_counts():
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {"fact-a": "content a", "fact-b": "content b"})

    report = await run_repair(collection, store, revectorize, fact_ids=["fact-a", "fact-b"], apply_changes=True)

    assert sorted(report.unreachable_before) == ["fact-a", "fact-b"]
    assert report.unreachable_after == []
    assert sorted(report.touched_fact_ids) == ["fact-a", "fact-b"]


async def test_scope_is_honoured_exactly():
    """A fact outside the requested scope is left completely alone."""
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {"fact-a": "content a", "fact-b": "content b"})

    await run_repair(collection, store, revectorize, fact_ids=["fact-a"], apply_changes=True)

    assert revectorize.calls == ["fact-a"]
    assert collection.get(ids=["node-uuid-2"])["documents"] == [""]


async def test_row_squatting_on_the_fact_id_is_cleared_before_the_rewrite():
    """``collection.add`` is a silent no-op on an existing id — the row must go first.

    Without the pre-delete the rewrite reports success and the document stays
    empty, which is precisely the failure mode this tool exists to undo.
    """
    collection = InMemoryCollection("autobot_memory")
    _add(collection, "fact-x", "", "fact-x")
    store, revectorize = _wire(collection, {"fact-x": "recovered content"})

    report = await run_repair(collection, store, revectorize, fact_ids=["fact-x"], apply_changes=True)

    assert report.outcomes[0].status == REPAIRED
    assert collection.get(ids=["fact-x"])["documents"] == ["recovered content"]


@pytest.mark.real_kb
def test_chromadb_add_on_an_existing_id_is_a_silent_no_op():
    """The load-bearing assumption behind the pre-delete, pinned against real chromadb.

    Re-running the reconciler over a poisoned row provably cannot fix it: ``add``
    on an existing id neither raises nor overwrites. If that ever changes, the
    delete-first step here can be simplified — this test is the tripwire.

    Runs in a clean subprocess because ``autobot-backend/conftest.py`` replaces
    ``chromadb`` with a package stub for the whole suite (#MVA-1119), so an
    in-process probe would assert against a MagicMock.
    """
    probe = textwrap.dedent("""
        import chromadb
        collection = chromadb.EphemeralClient().create_collection("repair_probe")
        meta = {"document_id": "fact-x"}
        collection.add(ids=["fact-x"], embeddings=[[0.1, 0.2, 0.3]], documents=[""], metadatas=[meta])
        collection.add(ids=["fact-x"], embeddings=[[0.4, 0.5, 0.6]], documents=["rewritten"], metadatas=[meta])
        stored = collection.get(ids=["fact-x"], include=["documents"])["documents"]
        print("DOC=%r COUNT=%d" % (stored[0], collection.count()))
        """)
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=PROBE_TIMEOUT)

    if "ModuleNotFoundError" in result.stderr:
        pytest.skip("real chromadb is not installed in this environment")
    # Any other non-zero exit is a real signal — e.g. chroma starting to raise on
    # a duplicate id. Skipping on it would silently disarm this tripwire.
    assert result.returncode == 0, result.stderr
    assert "DOC='' COUNT=1" in result.stdout, result.stdout


# --------------------------------------------------------------------------
# Idempotency
# --------------------------------------------------------------------------


async def test_second_run_is_a_no_op():
    """The owner's requirement: re-running must change nothing and write nothing."""
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {"fact-a": "content a", "fact-b": "content b"})
    scope = ["fact-a", "fact-b"]

    first = await run_repair(collection, store, revectorize, fact_ids=scope, apply_changes=True)
    assert [outcome.status for outcome in first.outcomes] == [REPAIRED, REPAIRED]

    snapshot = collection.get(include=["documents", "metadatas"])
    calls_after_first = list(revectorize.calls)

    second = await run_repair(collection, store, revectorize, fact_ids=scope, apply_changes=True)

    assert [outcome.status for outcome in second.outcomes] == [ALREADY_CLEAN, ALREADY_CLEAN]
    assert second.unreachable_before == [] and second.unreachable_after == []
    assert revectorize.calls == calls_after_first, "second run must not re-vectorize"
    assert collection.get(include=["documents", "metadatas"]) == snapshot, "second run must not mutate the store"


async def test_a_fact_with_no_row_at_all_is_rebuilt_not_called_clean():
    """The interrupted-repair window: no empty row left, and no vector either.

    ``already_clean`` must mean "verified present", never "found nothing" — the
    census cannot see such a fact, so a false all-clear here is unrecoverable.
    """
    collection = InMemoryCollection("autobot_memory")
    store, revectorize = _wire(collection, {"fact-gone": "recoverable content"})

    report = await run_repair(collection, store, revectorize, fact_ids=["fact-gone"], apply_changes=True)

    assert report.outcomes[0].status == REPAIRED
    assert revectorize.calls == ["fact-gone"]
    assert report.unreachable_before == ["fact-gone"]
    assert report.unreachable_after == []


async def test_rerunning_after_a_failed_run_completes_the_repair():
    """The exact cycle a reviewer reproduced: fail after the delete, then re-run.

    Run 1 removes the blocking row and then fails to rebuild, leaving the fact
    with no row at all. Run 2 must finish the job rather than report success
    over a fact that is missing from the index.
    """
    collection = InMemoryCollection("autobot_memory")
    _add_inline_shape(collection, "fact-x", "")
    store = FakeFactStore({"fact-x": "recoverable content"})
    failing = FakeRevectorizer(store, collection, fail_with=RuntimeError("backend down"))

    first = await run_repair(collection, store, failing, fact_ids=["fact-x"], apply_changes=True)
    assert first.outcomes[0].status == REVECTORIZE_FAILED
    assert first.outcomes[0].deleted_row_ids == ["fact-x"]
    assert has_reachable_vector(collection, "fact-x") is False

    recovered = await run_repair(
        collection, store, FakeRevectorizer(store, collection), fact_ids=["fact-x"], apply_changes=True
    )

    assert recovered.outcomes[0].status == REPAIRED
    assert recovered.unreachable_after == []
    assert collection.get(ids=["fact-x"])["documents"] == ["recoverable content"]


async def test_dry_run_plans_a_rebuild_for_a_missing_fact():
    collection = InMemoryCollection("autobot_memory")
    store, revectorize = _wire(collection, {"fact-gone": "recoverable content"})

    report = await run_repair(collection, store, revectorize, fact_ids=["fact-gone"])

    assert report.outcomes[0].status == WOULD_REPAIR
    assert "no vector present" in report.outcomes[0].reason
    assert revectorize.calls == []


async def test_already_clean_requires_a_verified_non_empty_row():
    collection = InMemoryCollection("autobot_memory")
    _add(collection, "node-ok", "healthy content", "fact-ok")
    store, revectorize = _wire(collection, {"fact-ok": "healthy content"})

    report = await run_repair(collection, store, revectorize, fact_ids=["fact-ok"], apply_changes=True)

    assert report.outcomes[0].status == ALREADY_CLEAN
    assert "non-empty row is present" in report.outcomes[0].reason
    assert revectorize.calls == []


async def test_a_missing_fact_without_redis_content_is_still_reported():
    """No row, no content: unrepairable, and it must not read as clean."""
    collection = InMemoryCollection("autobot_memory")
    store, revectorize = _wire(collection, {})

    report = await run_repair(collection, store, revectorize, fact_ids=["fact-gone"], apply_changes=True)

    assert report.outcomes[0].status == NO_REDIS_CONTENT
    assert report.unreachable_after == ["fact-gone"]


async def test_second_dry_run_finds_nothing_left():
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {"fact-a": "content a", "fact-b": "content b"})

    await run_repair(collection, store, revectorize, fact_ids=["fact-a", "fact-b"], apply_changes=True)
    census = await run_repair(collection, store, revectorize)

    assert census.scope == []
    assert census.poisoned_rows_found == 1  # only the unlinked row, which no fact can rebuild


# --------------------------------------------------------------------------
# Loud failure — nothing is skipped quietly
# --------------------------------------------------------------------------


async def test_fact_without_redis_content_is_reported_not_skipped():
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {})

    report = await run_repair(collection, store, revectorize, fact_ids=["fact-a"], apply_changes=True)

    outcome = report.outcomes[0]
    assert outcome.status == NO_REDIS_CONTENT
    assert "no content in Redis" in outcome.reason
    assert report.failures == [outcome]
    assert collection.get(ids=["node-uuid-1"])["ids"] == ["node-uuid-1"], "evidence must be preserved"


async def test_revectorization_exception_becomes_a_reported_failure():
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {"fact-a": "content a"}, fail_with=RuntimeError("ollama refused"))

    report = await run_repair(collection, store, revectorize, fact_ids=["fact-a"], apply_changes=True)

    outcome = report.outcomes[0]
    assert outcome.status == REVECTORIZE_FAILED
    assert "RuntimeError" in outcome.reason and "ollama refused" in outcome.reason
    assert store.retried == ["fact-a"], "a failed fact must be re-queued, not left stamped completed"


async def test_revectorization_error_status_is_a_failure():
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {"fact-a": "content a"}, succeed=False)

    report = await run_repair(collection, store, revectorize, fact_ids=["fact-a"], apply_changes=True)

    assert report.outcomes[0].status == REVECTORIZE_FAILED
    assert "embedding backend unavailable" in report.outcomes[0].reason


async def test_success_without_a_real_vector_is_caught_by_verification():
    """A backend that claims success but writes nothing must not be believed."""
    collection = _poisoned_collection()
    store = FakeFactStore({"fact-a": "content a"})

    async def lying_revectorize(fact_id: str) -> Dict[str, Any]:
        return {"status": "success", "vector_indexed": True, "fact_id": fact_id}

    report = await run_repair(collection, store, lying_revectorize, fact_ids=["fact-a"], apply_changes=True)

    outcome = report.outcomes[0]
    assert outcome.status == VERIFY_FAILED
    assert store.retried == ["fact-a"]
    assert report.unreachable_after == ["fact-a"], "the report must not claim a repair that did not happen"


async def test_delete_failure_propagates_rather_than_being_swallowed():
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {"fact-a": "content a"})

    def exploding_delete(**kwargs):
        raise OSError("chroma sqlite is read-only")

    collection.delete = exploding_delete

    with pytest.raises(OSError, match="read-only"):
        await run_repair(collection, store, revectorize, fact_ids=["fact-a"], apply_changes=True)


# --------------------------------------------------------------------------
# Operator-facing output
# --------------------------------------------------------------------------


async def test_report_prints_before_after_and_touched_ids():
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {"fact-a": "content a", "fact-b": "content b"})

    report = await run_repair(collection, store, revectorize, fact_ids=["fact-a"], apply_changes=True)
    text = "\n".join(render_report(report))

    assert "Unreachable facts BEFORE        : 1" in text
    assert "Unreachable facts AFTER         : 0" in text
    assert "fact-a" in text
    assert "APPLY" in text


async def test_dry_run_report_says_nothing_was_written():
    collection = _poisoned_collection()
    store, revectorize = _wire(collection, {"fact-a": "content a", "fact-b": "content b"})

    text = "\n".join(render_report(await run_repair(collection, store, revectorize)))

    assert "DRY-RUN (no changes written)" in text
    assert "Empty rows naming no fact       : 1" in text


def test_failures_are_listed_individually():
    from knowledge.vector_repair import FactOutcome, RepairReport

    report = RepairReport(outcomes=[FactOutcome("fact-z", NO_REDIS_CONTENT, "gone", ["node-9"])])
    text = "\n".join(render_report(report))

    assert "FAILURES (1)" in text
    assert "fact-z" in text and "gone" in text


def test_collision_detection_matches_the_two_write_shapes():
    assert PoisonedRow("fact-a", "fact-a").collides_with_fact_id is True
    assert PoisonedRow("node-uuid-1", "fact-a").collides_with_fact_id is False
    assert PoisonedRow("node-orphan", None).collides_with_fact_id is False
