# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The code graph records how and when it was built (#13508).

Every other honesty guarantee in this track is per-query: the call-graph endpoint
reports ``files_scanned``/``truncated``, impact analysis reports ``depth_capped``.
Those disclose *the query's* limits. None disclosed *the graph's*, so a perfectly
reported query over a three-week-old graph was still a confidently wrong answer.

The load-bearing property throughout is that **absence reads as unknown, never as
fresh**. A collection indexed before this existed, a store that cannot be read, a
record from a schema this build does not understand — all resolve to ``None``, and
a caller that cannot tell "current" from "unknown" is back where it started.
"""

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from services.knowledge.code_indexer import (
    _CACHE_VERSION_KEY,
    _PROVENANCE_ID,
    EXTRACTOR_VERSION,
    CodeIndexer,
    CodeIndexResult,
    GraphProvenance,
    graph_commits_behind,
    load_graph_provenance,
)


class _FakeCollection:
    """Minimal stand-in for the Chroma collection: records upserts, serves gets."""

    def __init__(self, records: dict | None = None, fail_on_get: bool = False, fail_on_upsert: bool = False):
        self.records = dict(records or {})
        self.fail_on_get = fail_on_get
        self.fail_on_upsert = fail_on_upsert
        self.upserts: list[dict] = []

    def upsert(self, ids, embeddings, documents, metadatas):
        if self.fail_on_upsert:
            raise RuntimeError("store unavailable")
        self.upserts.append({"ids": ids, "metadatas": metadatas})
        for record_id, metadata in zip(ids, metadatas):
            self.records[record_id] = metadata

    def get(self, ids, include=None):
        if self.fail_on_get:
            raise RuntimeError("store unavailable")
        return {"metadatas": [self.records[i] for i in ids if i in self.records]}


def _provenance(**overrides) -> dict:
    base = {
        "record_type": "graph_provenance",
        "indexed_at_commit": "a" * 40,
        "indexed_at": "2026-08-09T00:00:00+00:00",
        "extractor_version": EXTRACTOR_VERSION,
        "files_indexed": 90,
        "files_total": 100,
        "nodes": 500,
        "edges": 400,
        "resolved_edges": 300,
        "unresolved_edges": 100,
    }
    base.update(overrides)
    return base


# ------------------------------------------------------- absence means unknown


def test_a_collection_with_no_provenance_reads_as_unknown():
    """The constraint the issue is explicit about: pre-existing graphs are not fresh."""
    assert load_graph_provenance(_FakeCollection()) is None


def test_an_unreadable_store_reads_as_unknown_rather_than_raising():
    assert load_graph_provenance(_FakeCollection(fail_on_get=True)) is None


def test_a_record_missing_required_fields_reads_as_unknown():
    """A half-written or older-schema record must not be reported as a graph state."""
    partial = {"record_type": "graph_provenance", "indexed_at_commit": "a" * 40}

    assert load_graph_provenance(_FakeCollection({_PROVENANCE_ID: partial})) is None


def test_unrecognised_extra_fields_do_not_break_reading():
    """A newer writer adding a field must not make the record unreadable to this build."""
    record = _provenance(some_future_field="ignored")

    loaded = load_graph_provenance(_FakeCollection({_PROVENANCE_ID: record}))

    assert loaded is not None
    assert loaded.nodes == 500


# ------------------------------------------------------------ what it records


def test_a_completed_run_records_every_field():
    collection = _FakeCollection()
    indexer = CodeIndexer(collection=collection, embed_model=None, cache_file=Path("/tmp/unused-13508.json"))
    aggregate = CodeIndexResult(files_indexed=3, files_total=5, nodes=12, edges=9, resolved_edges=7, unresolved_edges=2)

    asyncio.run(indexer._write_provenance(".", aggregate))

    loaded = load_graph_provenance(collection)
    assert loaded is not None
    assert (loaded.files_indexed, loaded.files_total) == (3, 5)
    assert (loaded.nodes, loaded.edges) == (12, 9)
    assert (loaded.resolved_edges, loaded.unresolved_edges) == (7, 2)
    assert loaded.extractor_version == EXTRACTOR_VERSION
    assert loaded.indexed_at, "no timestamp recorded"


def test_provenance_overwrites_rather_than_accumulates():
    """One record per collection — a fixed id, so runs replace each other."""
    collection = _FakeCollection()
    indexer = CodeIndexer(collection=collection, embed_model=None, cache_file=Path("/tmp/unused-13508.json"))

    asyncio.run(indexer._write_provenance(".", CodeIndexResult(nodes=1)))
    asyncio.run(indexer._write_provenance(".", CodeIndexResult(nodes=2)))

    assert [u["ids"] for u in collection.upserts] == [[_PROVENANCE_ID], [_PROVENANCE_ID]]
    assert load_graph_provenance(collection).nodes == 2


def test_a_failed_provenance_write_does_not_fail_the_run():
    """A graph that indexed correctly must not be reported as broken bookkeeping."""
    indexer = CodeIndexer(
        collection=_FakeCollection(fail_on_upsert=True), embed_model=None, cache_file=Path("/tmp/unused-13508.json")
    )

    asyncio.run(indexer._write_provenance(".", CodeIndexResult(nodes=1)))  # must not raise


def test_the_roll_ups_are_ratios_a_consumer_can_act_on():
    loaded = GraphProvenance(**{k: v for k, v in _provenance().items() if k != "record_type"})

    assert loaded.coverage == 0.9
    assert loaded.resolution_rate == 0.75


def test_ratios_do_not_divide_by_zero_on_an_empty_run():
    empty = GraphProvenance(
        indexed_at_commit="",
        indexed_at="2026-08-09T00:00:00+00:00",
        extractor_version=EXTRACTOR_VERSION,
        files_indexed=0,
        files_total=0,
        nodes=0,
        edges=0,
        resolved_edges=0,
        unresolved_edges=0,
    )

    assert empty.coverage == 0.0
    assert empty.resolution_rate == 0.0


# ------------------------------------------------- "how stale is this graph?"


@pytest.fixture
def git_repo(tmp_path):
    """A real two-commit repo — the distance question is about git, so use git."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name in ("git config user.email a@b.c", "git config user.name t"):
        subprocess.run(["git", "-C", str(tmp_path), *name.split()[1:]], check=True)
    (tmp_path / "f.txt").write_text("1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "one"], check=True)
    first = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    (tmp_path / "f.txt").write_text("2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qam", "two"], check=True)
    return tmp_path, first


def test_a_consumer_learns_the_distance_without_rewalking_the_repo(git_repo):
    """AC: "graph is N commits behind HEAD", answered from the record plus one git call."""
    repo, first_commit = git_repo
    collection = _FakeCollection({_PROVENANCE_ID: _provenance(indexed_at_commit=first_commit)})

    assert graph_commits_behind(collection, str(repo)) == 1


def test_a_current_graph_reports_zero_not_unknown(git_repo):
    repo, _ = git_repo
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    collection = _FakeCollection({_PROVENANCE_ID: _provenance(indexed_at_commit=head)})

    assert graph_commits_behind(collection, str(repo)) == 0


def test_a_commit_absent_from_this_history_is_unanswerable_not_zero(git_repo):
    """After a rebase or force-push the recorded commit is gone.

    Returning a number there would be a fabrication, and 0 would be the worst of
    them — it reads as "current" for a graph built on a commit that no longer
    exists.
    """
    repo, _ = git_repo
    collection = _FakeCollection({_PROVENANCE_ID: _provenance(indexed_at_commit="b" * 40)})

    assert graph_commits_behind(collection, str(repo)) is None


def test_no_provenance_is_unanswerable(git_repo):
    repo, _ = git_repo

    assert graph_commits_behind(_FakeCollection(), str(repo)) is None


def test_a_non_git_directory_is_unanswerable_not_an_error(tmp_path):
    collection = _FakeCollection({_PROVENANCE_ID: _provenance()})

    assert graph_commits_behind(collection, str(tmp_path)) is None


# --------------------------------------- a version bump invalidates the cache


def _cache_file(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "hashes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_cache_written_by_this_version_is_reused(tmp_path):
    cache = _cache_file(tmp_path, {"a.py": "hash-a", _CACHE_VERSION_KEY: EXTRACTOR_VERSION})

    indexer = CodeIndexer(collection=_FakeCollection(), embed_model=None, cache_file=cache)

    assert indexer._hash_cache == {"a.py": "hash-a"}


def test_a_version_bump_discards_the_whole_cache(tmp_path):
    """AC: bumping the version rebuilds rather than skipping on a hash match.

    A content hash answers "did this file change". It cannot answer "did the thing
    that reads this file change" — so without this gate a bumped extractor would
    skip every unchanged file and the graph would stay built by the old one.
    """
    cache = _cache_file(tmp_path, {"a.py": "hash-a", _CACHE_VERSION_KEY: EXTRACTOR_VERSION - 1})

    indexer = CodeIndexer(collection=_FakeCollection(), embed_model=None, cache_file=cache)

    assert indexer._hash_cache == {}


def test_a_cache_predating_versioning_is_discarded(tmp_path):
    """Caches written before #13508 carry no version and must not be trusted."""
    cache = _cache_file(tmp_path, {"a.py": "hash-a"})

    indexer = CodeIndexer(collection=_FakeCollection(), embed_model=None, cache_file=cache)

    assert indexer._hash_cache == {}


def test_the_version_marker_is_written_back_and_is_not_a_file_entry(tmp_path):
    cache = tmp_path / "hashes.json"
    indexer = CodeIndexer(collection=_FakeCollection(), embed_model=None, cache_file=cache)
    indexer._hash_cache = {"a.py": "hash-a"}

    indexer._save_cache()
    written = json.loads(cache.read_text(encoding="utf-8"))

    assert written[_CACHE_VERSION_KEY] == EXTRACTOR_VERSION
    assert _CACHE_VERSION_KEY.startswith("::"), "the marker must not look like a relative path"
    assert CodeIndexer(collection=_FakeCollection(), embed_model=None, cache_file=cache)._hash_cache == {
        "a.py": "hash-a"
    }


def test_a_corrupt_cache_file_is_discarded_not_fatal(tmp_path):
    cache = tmp_path / "hashes.json"
    cache.write_text("{not json", encoding="utf-8")

    assert CodeIndexer(collection=_FakeCollection(), embed_model=None, cache_file=cache)._hash_cache == {}
