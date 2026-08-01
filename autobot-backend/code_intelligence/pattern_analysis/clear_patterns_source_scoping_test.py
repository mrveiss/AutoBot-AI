# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for the destructive cross-source ``clear_patterns()``
data-loss bug (Issue #12408).

``POST /patterns/storage/clear`` -> ``clear_patterns()`` previously fetched
and deleted every id in the shared ``code_patterns`` ChromaDB collection with
NO source filter -- so clearing one source's patterns silently wiped every
other source's (and AutoBot's own) stored patterns too. This mirrors the
#12384/#12405 read-side scoping fix, applied here to the destructive
write-side clear.

These tests assert the fix end-to-end:
- ``clear_patterns(source_id="A")`` deletes ONLY source A's patterns; source
  B's patterns remain intact;
- omitting ``source_id`` resolves to the ``"default"`` sentinel scope (like
  every other ``/patterns/*`` endpoint), never a full-collection wipe;
- the endpoint layer (``clear_pattern_storage``) threads ``source_id``
  through unchanged.
"""

import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict

import pytest


# ---------------------------------------------------------------------------
# Real-module loading -- mirrors source_scoping_test.py's
# _load_real_pattern_analysis_package() so we exercise real storage.py
# behavior rather than the top-level conftest's MagicMock stub.
# ---------------------------------------------------------------------------
def _load_real_pattern_analysis_package():
    base = Path(__file__).resolve().parent  # code_intelligence/pattern_analysis/
    pkg_name = "_real_pattern_analysis_12408"

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
    """In-memory ChromaDB stand-in with ``where``-scoped delete support,
    reproducing the real fail-closed equality-filter behavior: a ``where``
    condition on a key ABSENT from a record's metadata never matches.

    Extends the style of ``source_scoping_test.py``'s fake with a ``delete``
    method (not needed by the #12384 read-only tests, required here since
    #12408 is about the destructive write path).
    """

    def __init__(self):
        self.ids: list = []
        self.embeddings: list = []
        self.documents: list = []
        self.metadatas: list = []
        self.last_delete_where: Dict[str, Any] | None = None
        self.last_delete_ids: list | None = None

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

    async def get(self, where=None, limit=None, offset=None, include=None):
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

    async def delete(self, *, ids=None, where=None):
        """Mirrors the real adapters (chromadb_adapter/async_chromadb_adapter/
        memory_adapter): forwards ``where`` straight through to a native
        where-scoped delete; ``ids`` deletes those exact ids."""
        self.last_delete_where = where
        self.last_delete_ids = list(ids) if ids is not None else None
        if ids is None and where is None:
            raise ValueError("delete requires ids or where")
        target_indices = self._matched_indices(where) if where is not None else range(len(self.ids))
        target_ids = {self.ids[i] for i in target_indices}
        if ids is not None:
            target_ids &= set(ids)

        keep = [i for i in range(len(self.ids)) if self.ids[i] not in target_ids]
        self.ids = [self.ids[i] for i in keep]
        self.embeddings = [self.embeddings[i] for i in keep]
        self.documents = [self.documents[i] for i in keep]
        self.metadatas = [self.metadatas[i] for i in keep]

    async def count(self) -> int:
        return len(self.ids)


async def _seed_two_sources(collection: _FakeChromaCollection) -> None:
    await collection.add(
        ids=["a1", "a2"],
        embeddings=[[0.1], [0.2]],
        documents=["a1 doc", "a2 doc"],
        metadatas=[
            {"pattern_type": "duplicate", "source_id": "A"},
            {"pattern_type": "regex_opportunity", "source_id": "A"},
        ],
    )
    await collection.add(
        ids=["b1"],
        embeddings=[[0.3]],
        documents=["b1 doc"],
        metadatas=[{"pattern_type": "duplicate", "source_id": "B"}],
    )


class TestClearPatternsSourceScoping:
    async def test_clear_scoped_to_source_deletes_only_that_source(self, pa):
        """Issue #12408: clearing source A must delete ONLY A's patterns --
        B's must remain intact. This is the core data-loss regression."""
        collection = _FakeChromaCollection()
        await _seed_two_sources(collection)
        assert await collection.count() == 3

        success = await pa.storage.clear_patterns(collection=collection, source_id="A")

        assert success is True
        assert collection.ids == ["b1"]
        assert await collection.count() == 1
        remaining = await collection.get(include=["metadatas"])
        assert all(m["source_id"] == "B" for m in remaining["metadatas"])

    async def test_clear_missing_source_id_does_not_wipe_all_sources(self, pa):
        """Issue #12408: omitting source_id must resolve to the "default"
        sentinel scope (matching build_source_scoped_where / every other
        /patterns/* endpoint) -- it must NEVER wipe every source."""
        collection = _FakeChromaCollection()
        await _seed_two_sources(collection)
        # Patterns tagged "default" (e.g. a caller that never set a source).
        await collection.add(
            ids=["d1"],
            embeddings=[[0.4]],
            documents=["d1 doc"],
            metadatas=[{"pattern_type": "duplicate", "source_id": "default"}],
        )
        assert await collection.count() == 4

        success = await pa.storage.clear_patterns(collection=collection)  # no source_id

        assert success is True
        # Only the "default"-scoped pattern is gone; A and B are untouched.
        assert set(collection.ids) == {"a1", "a2", "b1"}
        assert collection.last_delete_where == {"source_id": "default"}

    async def test_clear_uses_where_delete_not_unscoped_ids(self, pa):
        """The fix must call collection.delete(where=...) scoped by
        build_source_scoped_where, never an unfiltered ids=[...] wipe."""
        collection = _FakeChromaCollection()
        await _seed_two_sources(collection)

        await pa.storage.clear_patterns(collection=collection, source_id="A")

        assert collection.last_delete_where == pa.storage.build_source_scoped_where("A")
        assert collection.last_delete_where == {"source_id": "A"}


class TestClearPatternStorageEndpointThreadsSourceId:
    def test_endpoint_signature_accepts_source_id_query_param(self):
        """Issue #12408: the endpoint must accept source_id like every other
        /patterns/* endpoint, not silently ignore/drop it."""
        from api.codebase_analytics.endpoints import pattern_analysis as endpoint_module

        sig = inspect.signature(endpoint_module.clear_pattern_storage)
        assert "source_id" in sig.parameters
