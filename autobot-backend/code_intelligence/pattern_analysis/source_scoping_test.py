# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for cross-project ``code_patterns`` ChromaDB leakage
(Issue #12384).

``CodePatternAnalyzer`` stores duplicate/regex-opportunity pattern embeddings
in the global ``code_patterns`` ChromaDB collection with NO source scoping --
a caller reading cached patterns for one project could surface patterns
detected in a different project (or AutoBot's own tree) when they share the
collection. This mirrors the #12356/#12374 fix already applied to
``CrossLanguagePatternDetector`` and the #12384 fix already applied to
``BugPredictor``/``bug_pattern_vectors``.

These tests assert the fix end-to-end:
- every stored pattern's metadata is tagged with ``source_id``;
- the storage-layer query helpers (``search_similar_patterns``,
  ``get_pattern_stats``) and the endpoint-layer where-filter builder
  (``_build_chromadb_where_filter``) always fold ``source_id`` into the query;
- source B's query never returns source A's stored patterns (fail-closed for
  legacy untagged records is proven too).
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict

import pytest

from api.codebase_analytics.endpoints.pattern_analysis import _build_chromadb_where_filter


# ---------------------------------------------------------------------------
# Real-module loading (bypasses the top-level conftest's
# ``code_intelligence.pattern_analysis`` MagicMock stub so we exercise real
# behavior) -- mirrors ``_load_real_detector_class`` in
# cross_language_scoping_test.py. Loads submodules in dependency order so
# their relative imports (``from .types import ...``) resolve.
# ---------------------------------------------------------------------------
def _load_real_pattern_analysis_package():
    base = Path(__file__).resolve().parent  # code_intelligence/pattern_analysis/
    pkg_name = "_real_pattern_analysis_12384"

    if pkg_name not in sys.modules:
        pkg = ModuleType(pkg_name)
        pkg.__path__ = [str(base)]
        pkg.__package__ = pkg_name
        sys.modules[pkg_name] = pkg
        for sub in (
            "types",
            "complexity_analyzer",
            "refactoring_generator",
            "regex_detector",
            "storage",
            "analyzer",
        ):
            spec = importlib.util.spec_from_file_location(f"{pkg_name}.{sub}", base / f"{sub}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"{pkg_name}.{sub}"] = module
            spec.loader.exec_module(module)
            setattr(pkg, sub, module)

    return sys.modules[pkg_name]


@pytest.fixture
def pa():
    return _load_real_pattern_analysis_package()


class _FakeChromaCollection:
    """In-memory ChromaDB stand-in that reproduces the real fail-closed
    equality-filter behavior: a ``where`` condition on a key ABSENT from a
    record's metadata never matches."""

    def __init__(self):
        self.ids: list = []
        self.embeddings: list = []
        self.documents: list = []
        self.metadatas: list = []
        self.last_query_where: Dict[str, Any] | None = None
        self.last_get_where: Dict[str, Any] | None = None

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

    def _matched_indices(self, where):
        return [i for i, m in enumerate(self.metadatas) if where is None or self._matches(m, where)]

    async def query(self, query_embeddings, n_results, where=None, include=None):
        self.last_query_where = where
        matched = self._matched_indices(where)[:n_results]
        return {
            "ids": [[self.ids[i] for i in matched]],
            "documents": [[self.documents[i] for i in matched]],
            "metadatas": [[self.metadatas[i] for i in matched]],
            "distances": [[0.0 for _ in matched]],
        }

    async def get(self, where=None, limit=None, offset=None, include=None):
        self.last_get_where = where
        matched = self._matched_indices(where)
        if offset:
            matched = matched[offset:]
        if limit is not None:
            matched = matched[:limit]
        result: Dict[str, Any] = {"ids": [self.ids[i] for i in matched]}
        if include is None or "metadatas" in include:
            result["metadatas"] = [self.metadatas[i] for i in matched]
        if include and "documents" in include:
            result["documents"] = [self.documents[i] for i in matched]
        return result


# ---------------------------------------------------------------------------
# Endpoint-level where-filter builder
# ---------------------------------------------------------------------------
class TestBuildChromaDBWhereFilter:
    def test_always_includes_source_id(self):
        assert _build_chromadb_where_filter(None, None) == {"source_id": "default"}
        assert _build_chromadb_where_filter(None, None, source_id="A") == {"source_id": "A"}

    def test_folds_extra_conditions_with_and(self):
        where = _build_chromadb_where_filter("duplicate", "high", source_id="A")
        assert where == {"$and": [{"source_id": "A"}, {"pattern_type": "duplicate"}, {"severity": "high"}]}


# ---------------------------------------------------------------------------
# Analyzer-level write-side tagging
# ---------------------------------------------------------------------------
class TestCodePatternAnalyzerSourceTagging:
    def test_default_source_tag_when_unset(self, pa):
        analyzer = pa.analyzer.CodePatternAnalyzer(enable_embedding_storage=False)
        assert analyzer.source_id is None
        assert analyzer._source_tag == "default"

    async def test_duplicate_pattern_metadata_tagged_with_source(self, pa):
        analyzer = pa.analyzer.CodePatternAnalyzer(enable_embedding_storage=False, source_id="A")
        dup = pa.types.DuplicatePattern(
            pattern_type=pa.types.PatternType.DUPLICATE_CODE,
            severity=pa.types.PatternSeverity.HIGH,
            description="clone",
            locations=[pa.types.CodeLocation(file_path="a.py", start_line=1, end_line=5)],
            suggestion="extract",
            confidence=0.9,
            similarity_score=0.95,
            canonical_code="def foo(): pass",
        )
        pattern = await analyzer._prepare_duplicate_pattern_for_storage(dup)
        assert pattern["metadata"]["source_id"] == "A"

    async def test_regex_pattern_metadata_tagged_with_source(self, pa):
        analyzer = pa.analyzer.CodePatternAnalyzer(enable_embedding_storage=False, source_id="A")
        regex_opp = pa.types.RegexOpportunity(
            pattern_type=pa.types.PatternType.REGEX_OPPORTUNITY,
            severity=pa.types.PatternSeverity.LOW,
            description="use regex",
            locations=[pa.types.CodeLocation(file_path="b.py", start_line=1, end_line=1)],
            suggestion="use re",
            confidence=0.8,
            current_code="x.replace('a', 'b')",
            suggested_regex="re.sub(...)",
        )
        pattern = await analyzer._prepare_regex_pattern_for_storage(regex_opp)
        assert pattern["metadata"]["source_id"] == "A"

    def test_default_tag_never_leaks_another_sources_tag(self, pa):
        analyzer_a = pa.analyzer.CodePatternAnalyzer(enable_embedding_storage=False, source_id="A")
        analyzer_default = pa.analyzer.CodePatternAnalyzer(enable_embedding_storage=False)
        assert analyzer_a._source_tag != analyzer_default._source_tag
        assert analyzer_default._source_tag == "default"


# ---------------------------------------------------------------------------
# Storage-level query scoping + end-to-end isolation
# ---------------------------------------------------------------------------
class TestStorageSourceScoping:
    def test_build_source_scoped_where_default_sentinel(self, pa):
        assert pa.storage.build_source_scoped_where(None) == {"source_id": "default"}
        assert pa.storage.build_source_scoped_where("A") == {"source_id": "A"}

    def test_build_source_scoped_where_folds_extra(self, pa):
        where = pa.storage.build_source_scoped_where("A", {"pattern_type": "duplicate"})
        assert where == {"$and": [{"source_id": "A"}, {"pattern_type": "duplicate"}]}

    def test_generate_pattern_id_differs_across_sources(self, pa):
        """Same file_path/start_line/code_hash but different source_id must
        never collide on the same ChromaDB id (would silently overwrite)."""
        base = {"pattern_type": "duplicate", "file_path": "app/main.py", "start_line": 10, "code_hash": "abc123"}
        id_a = pa.storage.generate_pattern_id({**base, "source_id": "A"})
        id_b = pa.storage.generate_pattern_id({**base, "source_id": "B"})
        assert id_a != id_b

    async def test_store_patterns_batch_tags_and_search_filters_by_source(self, pa):
        collection = _FakeChromaCollection()

        patterns_a = [
            {
                "pattern_type": "duplicate",
                "code_content": "def a_only(): pass",
                "embedding": [0.1, 0.2, 0.3],
                "metadata": {"file_path": "a_only.py", "start_line": 1, "source_id": "A"},
            }
        ]
        patterns_b = [
            {
                "pattern_type": "duplicate",
                "code_content": "def b_only(): pass",
                "embedding": [0.1, 0.2, 0.3],
                "metadata": {"file_path": "b_only.py", "start_line": 1, "source_id": "B"},
            }
        ]
        legacy_pattern = [
            {
                "pattern_type": "duplicate",
                "code_content": "def legacy(): pass",
                "embedding": [0.1, 0.2, 0.3],
                "metadata": {"file_path": "legacy.py", "start_line": 1},  # no source_id key at all
            }
        ]

        await pa.storage.store_patterns_batch(patterns_a, collection=collection)
        await pa.storage.store_patterns_batch(patterns_b, collection=collection)
        await pa.storage.store_patterns_batch(legacy_pattern, collection=collection)

        assert all(m.get("source_id") == "A" for m in collection.metadatas[:1])

        results_a = await pa.storage.search_similar_patterns(
            query_embedding=[0.1, 0.2, 0.3],
            collection=collection,
            source_id="A",
            min_similarity=0.0,
        )

        assert collection.last_query_where == {"source_id": "A"}
        docs = {r["document"] for r in results_a}
        assert docs == {"def a_only(): pass"}
        assert "def b_only(): pass" not in docs
        assert "def legacy(): pass" not in docs

    async def test_get_pattern_stats_scoped_to_source(self, pa):
        collection = _FakeChromaCollection()
        await collection.add(
            ids=["a1"],
            embeddings=[[0.1]],
            documents=["a"],
            metadatas=[{"pattern_type": "duplicate", "source_id": "A"}],
        )
        await collection.add(
            ids=["b1", "b2"],
            embeddings=[[0.1], [0.2]],
            documents=["b1", "b2"],
            metadatas=[
                {"pattern_type": "duplicate", "source_id": "B"},
                {"pattern_type": "regex_opportunity", "source_id": "B"},
            ],
        )

        stats_a = await pa.storage.get_pattern_stats(collection=collection, source_id="A")
        assert stats_a["total_patterns"] == 1

        stats_b = await pa.storage.get_pattern_stats(collection=collection, source_id="B")
        assert stats_b["total_patterns"] == 2
