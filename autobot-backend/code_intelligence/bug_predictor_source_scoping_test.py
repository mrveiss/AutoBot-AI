# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for cross-project ``bug_pattern_vectors`` ChromaDB leakage
(Issue #12384).

``BugPredictor`` learns bug patterns from git history and stores their
embeddings in the global ``bug_pattern_vectors`` ChromaDB collection with NO
source scoping -- a semantic-similarity query for one project could surface
bug patterns learned from a different project (or AutoBot's own tree) when
they share the collection. This mirrors the #12356/#12374 fix already applied
to ``CrossLanguagePatternDetector``.

These tests assert the fix end-to-end:
- every stored pattern's metadata is tagged with ``source_id``;
- the semantic-similarity query filters by ``source_id``;
- source B's query never returns source A's stored patterns (fail-closed for
  legacy untagged records is proven too).
"""

import importlib.util
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Real-module loading (bypasses the top-level conftest's
# ``code_intelligence.bug_predictor`` MagicMock stub so we exercise real
# behavior) -- mirrors ``_load_real_detector_class`` in
# cross_language_scoping_test.py.
# ---------------------------------------------------------------------------
def _load_real_bug_predictor_module():
    base = Path(__file__).resolve().parent  # code_intelligence/
    mod_name = "_real_bug_predictor_12384"

    if mod_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(mod_name, base / "bug_predictor.py")
        module = importlib.util.module_from_spec(spec)
        module.__package__ = "code_intelligence"
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(mod_name, None)
            raise

    return sys.modules[mod_name]


class _FakeChromaCollection:
    """In-memory ChromaDB stand-in that reproduces the real fail-closed
    equality-filter behavior: a ``where`` condition on a key ABSENT from a
    record's metadata never matches (mirrors real ChromaDB semantics relied
    on by the #12356/#12374/#12384 fixes)."""

    def __init__(self):
        self.ids: list = []
        self.embeddings: list = []
        self.documents: list = []
        self.metadatas: list = []
        self.last_query_where: dict | None = None

    async def add(self, ids, embeddings, documents, metadatas=None):
        self.ids.extend(ids)
        self.embeddings.extend(embeddings)
        self.documents.extend(documents)
        self.metadatas.extend(metadatas or [{} for _ in ids])

    @staticmethod
    def _matches(meta: dict, cond: dict) -> bool:
        if "$and" in cond:
            return all(_FakeChromaCollection._matches(meta, c) for c in cond["$and"])
        ((key, value),) = cond.items()
        return meta.get(key) == value  # absent key -> None != value -> no match

    async def query(self, query_embeddings, n_results, where=None):
        self.last_query_where = where
        matched = [i for i, m in enumerate(self.metadatas) if where is None or self._matches(m, where)]
        matched = matched[:n_results]
        return {
            "ids": [[self.ids[i] for i in matched]],
            "documents": [[self.documents[i] for i in matched]],
            "metadatas": [[self.metadatas[i] for i in matched]],
            "distances": [[0.0 for _ in matched]],
        }


@pytest.fixture
def bug_predictor_cls():
    return _load_real_bug_predictor_module().BugPredictor


class TestBugPredictorSourceScoping:
    """The predictor must tag stored patterns and filter queries by source_id."""

    def test_default_source_tag_when_unset(self, bug_predictor_cls):
        predictor = bug_predictor_cls()
        assert predictor.source_id is None
        assert predictor._source_tag == "default"

    def test_source_tag_set_from_source_id(self, bug_predictor_cls):
        predictor = bug_predictor_cls(source_id="A")
        assert predictor.source_id == "A"
        assert predictor._source_tag == "A"

    def test_stored_pattern_metadata_tagged_with_source(self, bug_predictor_cls):
        predictor_a = bug_predictor_cls(source_id="A")
        bug_patterns = [{"id": "p1", "file": "app.py", "message": "fix crash"}]
        texts = ["Bug fix in app.py: fix crash"]
        embeddings = [[0.1, 0.2, 0.3]]

        ids, embs, txts, metadatas = predictor_a._filter_valid_embeddings(bug_patterns, texts, embeddings)

        assert ids == ["p1"]
        assert metadatas == [{"file": "app.py", "source_id": "A"}]

        predictor_default = bug_predictor_cls()  # no source_id -> "default", never another source's tag
        _, _, _, metadatas_default = predictor_default._filter_valid_embeddings(bug_patterns, texts, embeddings)
        assert metadatas_default[0]["source_id"] == "default"

    async def test_query_filters_matches_by_source(self, bug_predictor_cls, monkeypatch):
        predictor_a = bug_predictor_cls(source_id="A", use_semantic_analysis=False)
        # Force the mixin's metrics/lock bookkeeping to exist without a real
        # ChromaDB/Redis stack -- semantic analysis is exercised directly via
        # the mixin methods below, independent of use_semantic_analysis.
        predictor_a._init_infrastructure(collection_name="bug_pattern_vectors_test")
        predictor_a.use_semantic_analysis = True

        fake_collection = _FakeChromaCollection()
        predictor_a._chromadb_collection = fake_collection

        async def _fake_get_embedding(_text):
            return [0.1, 0.2, 0.3]

        monkeypatch.setattr(predictor_a, "_get_embedding", _fake_get_embedding)

        await predictor_a._analyze_file_semantic_async(__file__)

        assert fake_collection.last_query_where == {"source_id": "A"}

    async def test_one_source_never_reads_anothers_patterns(self, bug_predictor_cls):
        """End-to-end: store patterns for A and B in the same collection;
        querying as A must never see B's (or legacy untagged) records."""
        predictor_a = bug_predictor_cls(source_id="A", use_semantic_analysis=False)
        predictor_a._init_infrastructure(collection_name="bug_pattern_vectors_test")
        predictor_a.use_semantic_analysis = True

        shared_collection = _FakeChromaCollection()
        predictor_a._chromadb_collection = shared_collection

        # Seed source B's pattern directly (as if predictor_b had stored it).
        await shared_collection.add(
            ids=["b1"],
            embeddings=[[0.1, 0.2, 0.3]],
            documents=["Bug fix in b_only.py: leak"],
            metadatas=[{"file": "b_only.py", "source_id": "B"}],
        )
        # And a pre-#12384 legacy record with no source_id key at all.
        await shared_collection.add(
            ids=["legacy1"],
            embeddings=[[0.1, 0.2, 0.3]],
            documents=["Bug fix in legacy.py: old"],
            metadatas=[{"file": "legacy.py"}],
        )
        # Seed source A's own pattern via the real write path.
        bug_patterns = [{"id": "a1", "file": "a_only.py", "message": "fix a"}]
        texts = ["Bug fix in a_only.py: fix a"]
        embeddings = [[0.1, 0.2, 0.3]]
        ids, embs, txts, metadatas = predictor_a._filter_valid_embeddings(bug_patterns, texts, embeddings)
        await predictor_a._store_vectors(ids=ids, embeddings=embs, documents=txts, metadatas=metadatas)

        # Query directly with A's scope tag -- the same call
        # `_analyze_file_semantic_async` makes internally.
        similar = await predictor_a._query_similar(
            [0.1, 0.2, 0.3],
            n_results=5,
            where={"source_id": predictor_a._source_tag},
            min_similarity=0.6,
        )

        assert shared_collection.last_query_where == {"source_id": "A"}
        returned_ids = {r["id"] for r in similar}
        # Fail-closed: neither B's tagged record nor the legacy untagged
        # record leak into A's similarity results -- only A's own pattern is
        # visible.
        assert returned_ids == {"a1"}
        assert "b1" not in returned_ids
        assert "legacy1" not in returned_ids
