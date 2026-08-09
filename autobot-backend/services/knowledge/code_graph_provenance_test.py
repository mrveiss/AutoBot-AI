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
    _EXTRACTORS,
    CodeIndexer,
    CodeIndexResult,
    GraphProvenance,
    graph_commits_behind,
    load_graph_provenance,
)

_EMBED_DIM = 384


class _FakeEmbedModel:
    """Returns a fixed-dimension vector, like the real model does."""

    def __init__(self, dim: int = _EMBED_DIM, fail: bool = False):
        self.dim = dim
        self.fail = fail

    def get_text_embedding(self, text: str) -> list[float]:
        if self.fail:
            raise RuntimeError("embedding model unavailable")
        return [0.1] * self.dim


class _FakeCollection:
    """Stand-in for the Chroma collection.

    Rejects a dimension mismatch the way Chroma does, and pins its dimension on
    first insert — the behaviour that made a placeholder embedding both a silent
    no-op on a populated collection and a permanent outage on an empty one.
    """

    def __init__(self, records: dict | None = None, fail_on_get: bool = False, fail_on_upsert: bool = False):
        self.records = dict(records or {})
        self.fail_on_get = fail_on_get
        self.fail_on_upsert = fail_on_upsert
        self.upserts: list[dict] = []
        self.dim: int | None = None

    def upsert(self, ids, embeddings, documents, metadatas):
        if self.fail_on_upsert:
            raise RuntimeError("store unavailable")
        for embedding in embeddings:
            if self.dim is None:
                self.dim = len(embedding)
            elif len(embedding) != self.dim:
                raise ValueError(f"Collection expecting embedding with dimension of {self.dim}, got {len(embedding)}")
        self.upserts.append({"ids": ids, "metadatas": metadatas, "embeddings": embeddings})
        for record_id, metadata in zip(ids, metadatas):
            self.records[record_id] = metadata

    def get(self, ids=None, where=None, include=None):
        if self.fail_on_get:
            raise RuntimeError("store unavailable")
        if ids is not None:
            return {"metadatas": [self.records[i] for i in ids if i in self.records]}
        wanted = (where or {}).get("record_type", {}).get("$eq")
        matched = [(k, m) for k, m in self.records.items() if m.get("record_type") == wanted]
        return {"ids": [k for k, _ in matched], "metadatas": [m for _, m in matched]}


def _indexer(collection, embed_model=None, cache_file=None):
    return CodeIndexer(
        collection=collection,
        embed_model=embed_model or _FakeEmbedModel(),
        cache_file=cache_file or Path("/tmp/unused-13508.json"),
    )


def _provenance(**overrides) -> dict:
    base = {
        "record_type": "graph_provenance",
        "indexed_at_commit": "a" * 40,
        "indexed_at": "2026-08-09T00:00:00+00:00",
        "extractor_version": EXTRACTOR_VERSION,
        "root_dir": "/repo",
        "files_with_extractor": 90,
        "files_total": 100,
        "nodes": 500,
        "edges": 400,
        "resolved_edges": 300,
        "unresolved_edges": 100,
        "last_run_nodes_stored": 500,
        "last_run_failures": 0,
    }
    base.update(overrides)
    return base


# ------------------------------------------------------- absence means unknown


def test_a_collection_with_no_provenance_reads_as_unknown():
    """The constraint the issue is explicit about: pre-existing graphs are not fresh."""
    assert asyncio.run(load_graph_provenance(_FakeCollection())) is None


def test_an_unreadable_store_reads_as_unknown_rather_than_raising():
    assert asyncio.run(load_graph_provenance(_FakeCollection(fail_on_get=True))) is None


def test_a_record_from_an_older_schema_still_loads_field_by_field():
    """Every field has a default, so one missing field degrades one value.

    The first draft had no defaults, which meant adding any field in a future
    version would make every existing record unreadable — the whole record lost to
    reclaim one unknown number.
    """
    partial = {"record_type": "graph_provenance", "indexed_at_commit": "a" * 40, "nodes": 7}

    loaded = asyncio.run(load_graph_provenance(_FakeCollection({_PROVENANCE_ID: partial})))

    assert loaded is not None
    assert loaded.nodes == 7
    assert loaded.files_total == 0, "an absent field must default, not invent"


def test_unrecognised_extra_fields_do_not_break_reading():
    """A newer writer adding a field must not make the record unreadable to this build."""
    loaded = asyncio.run(load_graph_provenance(_FakeCollection({_PROVENANCE_ID: _provenance(some_future="x")})))

    assert loaded is not None
    assert loaded.nodes == 500


# --------------------------------------- the embedding, and why it is not a placeholder


def _graph_records(nodes: int = 2, edges: int = 2, resolved: int = 1) -> dict:
    records = {f"n{i}": {"record_type": "node"} for i in range(nodes)}
    for i in range(edges):
        records[f"e{i}"] = {"record_type": "edge", "resolved": "true" if i < resolved else "false"}
    return records


def test_the_provenance_record_is_embedded_with_the_real_model():
    """A placeholder vector is not an option, in either direction.

    This record shares the docs collection, whose vector dimension is fixed by its
    first insert. A 1-dimensional placeholder is *rejected* on a populated
    collection — making the whole feature a silent no-op — and, worse, *accepted*
    on an empty one, pinning the shared knowledge collection to dimension 1 and
    permanently breaking every later real upsert.
    """
    collection = _FakeCollection(_graph_records())
    collection.upsert(["seed"], [[0.1] * _EMBED_DIM], ["seed"], [{"record_type": "node"}])

    asyncio.run(_indexer(collection)._write_provenance(".", CodeIndexResult()))

    written = [u for u in collection.upserts if u["ids"] == [_PROVENANCE_ID]]
    assert written, "provenance was rejected by a collection that already had a dimension"
    assert len(written[0]["embeddings"][0]) == _EMBED_DIM


def test_writing_into_an_empty_collection_does_not_pin_its_dimension():
    """The dangerous half: an empty collection accepts whatever it is first given."""
    collection = _FakeCollection()

    asyncio.run(_indexer(collection)._write_provenance(".", CodeIndexResult()))

    assert collection.dim == _EMBED_DIM
    collection.upsert(["n1"], [[0.1] * _EMBED_DIM], ["later real node"], [{"record_type": "node"}])


def test_an_unavailable_embed_model_records_nothing_rather_than_a_placeholder():
    """Better an unknown graph than a poisoned collection."""
    collection = _FakeCollection()

    asyncio.run(_indexer(collection, embed_model=_FakeEmbedModel(fail=True))._write_provenance(".", CodeIndexResult()))

    assert collection.upserts == []
    assert asyncio.run(load_graph_provenance(collection)) is None


# ------------------------------------------------------------ what it records


def test_the_totals_describe_the_graph_not_the_run():
    """The counts are read back from the collection, and that is the whole point.

    Per-run counters would report a healthy graph as empty on any incremental run,
    which is covered directly below.
    """
    collection = _FakeCollection(_graph_records(nodes=5, edges=4, resolved=3))

    asyncio.run(_indexer(collection)._write_provenance(".", CodeIndexResult(success=0)))

    loaded = asyncio.run(load_graph_provenance(collection))
    assert (loaded.nodes, loaded.edges) == (5, 4)
    assert (loaded.resolved_edges, loaded.unresolved_edges) == (3, 1)
    assert loaded.resolution_rate == 0.75


def test_an_incremental_run_does_not_report_the_graph_as_empty():
    """The regression this design exists to prevent.

    A second run over an unchanged tree hash-skips every file and extracts nothing.
    With per-run counters that overwrote a healthy record with ``nodes=0,
    resolution_rate=0.0`` — so the number meant to reveal a resolver regression by
    going down hit zero on every no-op nightly run and could never signal anything.
    """
    collection = _FakeCollection(_graph_records(nodes=5, edges=4, resolved=3))
    indexer = _indexer(collection)

    asyncio.run(indexer._write_provenance(".", CodeIndexResult(success=5)))
    asyncio.run(indexer._write_provenance(".", CodeIndexResult(success=0, skipped=5)))

    loaded = asyncio.run(load_graph_provenance(collection))
    assert loaded.nodes == 5, "an incremental run erased the graph's node count"
    assert loaded.resolution_rate == 0.75


def test_a_run_that_stored_nothing_is_visible_as_such():
    """A failed run must not read as a healthy graph.

    With the embed model down every node upsert fails and nothing reaches the
    collection. The run outcome is recorded beside the graph totals so a consumer
    can tell "graph is empty" from "graph is fine, this run achieved nothing".
    """
    collection = _FakeCollection(_graph_records(nodes=0, edges=0))

    asyncio.run(_indexer(collection)._write_provenance(".", CodeIndexResult(success=0, failed=4)))

    loaded = asyncio.run(load_graph_provenance(collection))
    assert (loaded.last_run_nodes_stored, loaded.last_run_failures) == (0, 4)
    assert loaded.nodes == 0


def test_an_uncountable_store_leaves_the_previous_record_alone():
    """Rather than replacing it with numbers this run could not verify."""
    collection = _FakeCollection({_PROVENANCE_ID: _provenance()})
    collection.fail_on_get = True

    asyncio.run(_indexer(collection)._write_provenance(".", CodeIndexResult()))

    assert collection.upserts == []


def test_the_record_names_the_tree_it_describes():
    collection = _FakeCollection(_graph_records())

    asyncio.run(_indexer(collection)._write_provenance(".", CodeIndexResult()))

    assert asyncio.run(load_graph_provenance(collection)).root_dir == str(Path(".").resolve())


def test_provenance_overwrites_rather_than_accumulates():
    """One record per collection — a fixed id, so runs replace each other."""
    collection = _FakeCollection(_graph_records())
    indexer = _indexer(collection)

    asyncio.run(indexer._write_provenance(".", CodeIndexResult()))
    asyncio.run(indexer._write_provenance(".", CodeIndexResult()))

    assert [u["ids"] for u in collection.upserts if u["ids"] == [_PROVENANCE_ID]] == [
        [_PROVENANCE_ID],
        [_PROVENANCE_ID],
    ]


def test_a_failed_provenance_write_does_not_fail_the_run():
    """A graph that indexed correctly must not be reported as broken bookkeeping."""
    asyncio.run(_indexer(_FakeCollection(fail_on_upsert=True))._write_provenance(".", CodeIndexResult()))


def test_extractor_coverage_is_named_for_what_it_measures():
    """It says a grammar exists, never that extraction succeeded."""
    loaded = GraphProvenance(**{k: v for k, v in _provenance().items() if k != "record_type"})

    assert loaded.extractor_coverage == 0.9
    assert loaded.resolution_rate == 0.75


def test_ratios_do_not_divide_by_zero_on_an_empty_graph():
    empty = GraphProvenance()

    assert empty.extractor_coverage == 0.0
    assert empty.resolution_rate == 0.0


# ------------------------------------------- index_directory produces the record


class _CountingIndexer(CodeIndexer):
    """Drives index_directory's bookkeeping without ChromaDB or an embed model."""

    async def index_file(self, path, root_dir=None, force=False):
        return CodeIndexResult(success=1)


def test_index_directory_writes_a_record_reflecting_the_tree_it_walked(tmp_path):
    """Binds the record to a real walk.

    Without this every line the feature adds to ``index_directory`` could be
    deleted and only the unit tests on hand-built results would notice — which is
    exactly how the per-run/per-graph confusion above survived the first draft.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "s.sh").write_text("echo hi\n", encoding="utf-8")
    collection = _FakeCollection(_graph_records(nodes=3, edges=2, resolved=2))
    indexer = _CountingIndexer(
        collection=collection, embed_model=_FakeEmbedModel(), cache_file=tmp_path / "hashes.json"
    )

    result = asyncio.run(indexer.index_directory(str(tmp_path)))

    assert (result.files_with_extractor, result.files_total) == (2, 3)
    loaded = asyncio.run(load_graph_provenance(collection))
    assert loaded is not None, "index_directory did not record provenance"
    assert (loaded.files_with_extractor, loaded.files_total) == (2, 3)
    assert loaded.extractor_coverage == 2 / 3
    assert loaded.nodes == 3, "the record did not take its totals from the collection"
    assert loaded.last_run_nodes_stored == 2
    assert loaded.root_dir == str(tmp_path.resolve())


# ------------------------------------------------- "how stale is this graph?"


@pytest.fixture
def git_repo(tmp_path):
    """A real two-commit repo — the distance question is about git, so use git."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "a@b.c"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    (tmp_path / "f.txt").write_text("1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "one"], check=True)
    first = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    (tmp_path / "f.txt").write_text("2\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qam", "two"], check=True)
    return tmp_path, first


def _behind(records: dict, repo) -> "int | None":
    return asyncio.run(graph_commits_behind(_FakeCollection(records), str(repo)))


def test_a_consumer_learns_the_distance_without_rewalking_the_repo(git_repo):
    """AC: "graph is N commits behind HEAD", from the record plus one git call."""
    repo, first_commit = git_repo

    assert _behind({_PROVENANCE_ID: _provenance(indexed_at_commit=first_commit, root_dir=str(repo))}, repo) == 1


def test_a_current_graph_reports_zero_not_unknown(git_repo):
    repo, _ = git_repo
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()

    assert _behind({_PROVENANCE_ID: _provenance(indexed_at_commit=head, root_dir=str(repo))}, repo) == 0


def test_a_commit_absent_from_this_history_is_unanswerable_not_zero(git_repo):
    """After a rebase or force-push the recorded commit is gone.

    ``0`` would be the worst answer available: it reads as "current" for a graph
    built on a commit that no longer exists.
    """
    repo, _ = git_repo

    assert _behind({_PROVENANCE_ID: _provenance(indexed_at_commit="b" * 40, root_dir=str(repo))}, repo) is None


def test_a_graph_built_by_another_extractor_version_is_unanswerable(git_repo):
    """Commit distance says nothing about a graph this build cannot trust.

    The hash cache already refuses to reuse work across a version bump; reporting
    "0 commits behind" for the same graph would undo that at the read side.
    """
    repo, _ = git_repo
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    record = _provenance(indexed_at_commit=head, root_dir=str(repo), extractor_version=EXTRACTOR_VERSION + 1)

    assert _behind({_PROVENANCE_ID: record}, repo) is None


def test_a_record_describing_another_tree_is_unanswerable(git_repo):
    """One fixed id per collection, so indexing a subdirectory replaces the record.

    Answering with the subtree's commit for a whole-repo question would be
    confident and wrong.
    """
    repo, first_commit = git_repo

    assert (
        _behind({_PROVENANCE_ID: _provenance(indexed_at_commit=first_commit, root_dir="/some/other/tree")}, repo)
        is None
    )


def test_a_commit_that_is_not_a_sha_never_reaches_git(git_repo):
    """The one untrusted string on this path is validated at the boundary."""
    repo, _ = git_repo

    assert (
        _behind({_PROVENANCE_ID: _provenance(indexed_at_commit="--upload-pack=evil", root_dir=str(repo))}, repo) is None
    )


def test_no_provenance_is_unanswerable(git_repo):
    repo, _ = git_repo

    assert asyncio.run(graph_commits_behind(_FakeCollection(), str(repo))) is None


def test_a_non_git_directory_is_unanswerable_not_an_error(tmp_path):
    assert _behind({_PROVENANCE_ID: _provenance(root_dir=str(tmp_path))}, tmp_path) is None


# --------------------------------------- a version bump invalidates the cache


def _cache_file(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "hashes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_cache_written_by_this_version_is_reused(tmp_path):
    cache = _cache_file(tmp_path, {"a.py": "hash-a", _CACHE_VERSION_KEY: EXTRACTOR_VERSION})

    assert _indexer(_FakeCollection(), cache_file=cache)._hash_cache == {"a.py": "hash-a"}


def test_a_version_bump_discards_the_whole_cache(tmp_path):
    """AC: bumping the version rebuilds rather than skipping on hash match.

    A content hash answers "did this file change". It cannot answer "did the thing
    that reads this file change" — so without this gate a bumped extractor would
    skip every unchanged file and the graph would stay built by the old one.
    """
    cache = _cache_file(tmp_path, {"a.py": "hash-a", _CACHE_VERSION_KEY: EXTRACTOR_VERSION - 1})

    assert _indexer(_FakeCollection(), cache_file=cache)._hash_cache == {}


def test_a_cache_predating_versioning_is_discarded(tmp_path):
    """Caches written before #13508 carry no version and cannot be vouched for."""
    cache = _cache_file(tmp_path, {"a.py": "hash-a"})

    assert _indexer(_FakeCollection(), cache_file=cache)._hash_cache == {}


def test_the_version_marker_round_trips_and_is_not_a_file_entry(tmp_path):
    cache = tmp_path / "hashes.json"
    indexer = _indexer(_FakeCollection(), cache_file=cache)
    indexer._hash_cache = {"a.py": "hash-a"}

    indexer._save_cache()
    written = json.loads(cache.read_text(encoding="utf-8"))

    assert written[_CACHE_VERSION_KEY] == EXTRACTOR_VERSION
    assert _indexer(_FakeCollection(), cache_file=cache)._hash_cache == {"a.py": "hash-a"}


def test_the_marker_can_never_collide_with_a_real_path(tmp_path):
    """It is keyed on a string no relative path can be, not merely an unlikely one."""
    assert Path(_CACHE_VERSION_KEY).suffix not in _EXTRACTORS


def test_a_corrupt_cache_file_is_discarded_not_fatal(tmp_path):
    cache = tmp_path / "hashes.json"
    cache.write_text("{not json", encoding="utf-8")

    assert _indexer(_FakeCollection(), cache_file=cache)._hash_cache == {}
