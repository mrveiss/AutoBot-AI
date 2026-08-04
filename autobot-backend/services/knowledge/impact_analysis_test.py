# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for reverse-BFS impact analysis (#13471).

Every test indexes a small fixture repo with :class:`CodeIndexer` against a
minimal in-memory ChromaDB-collection stand-in (real ``get(where=...)``
semantics, not a call-recording mock) so the transitive impact set asserted
against is the *actual* persisted graph, not a hand-built one — the true
transitive set is known by construction of each fixture.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

tree_sitter_available = True
try:
    import tree_sitter_python  # noqa: F401
except ImportError:
    tree_sitter_available = False

requires_tree_sitter = pytest.mark.skipif(not tree_sitter_available, reason="tree-sitter-python not installed")

from services.knowledge.code_indexer import CodeIndexer
from services.knowledge.impact_analysis import find_impact


class _FakeCollection:
    """Minimal in-memory ChromaDB-collection stand-in with real upsert/get(where=)
    semantics (equality plus ``$and``/``$eq``) — the same query shapes
    ``code_indexer``/``impact_analysis`` issue.

    ``autobot-backend/conftest.py`` stubs the real ``chromadb`` package with a
    MagicMock for the whole suite (#MVA-1119 — the real client hangs at
    import time without a local server), so a test wanting real query
    *behaviour* needs its own implementation. Unlike ``code_indexer_test.py``'s
    ``_FakeCollection``, this one filters ``ids`` by *where* too (matching the
    real ChromaDB contract) — this module never reads the ``ids`` array, but a
    stale unfiltered one is a trap for the next reader who does.
    """

    def __init__(self) -> None:
        self._records: dict[str, dict] = {}

    def upsert(self, ids: list[str], embeddings: list, documents: list[str], metadatas: list[dict]) -> None:
        for nid, meta in zip(ids, metadatas):
            self._records[nid] = meta

    def get(self, where: dict | None = None, include: list[str] | None = None) -> dict:
        matched = [(nid, meta) for nid, meta in self._records.items() if _fake_where_matches(meta, where)]
        return {"ids": [nid for nid, _ in matched], "metadatas": [meta for _, meta in matched]}


def _fake_where_matches(meta: dict, where: dict | None) -> bool:
    if not where:
        return True
    if "$and" in where:
        return all(_fake_where_matches(meta, clause) for clause in where["$and"])
    return all(meta.get(key) == (val["$eq"] if isinstance(val, dict) else val) for key, val in where.items())


def _make_indexer(collection: _FakeCollection, tmp_path: Path) -> CodeIndexer:
    embed_model = MagicMock()
    embed_model.get_text_embedding = MagicMock(side_effect=lambda text: [float(len(text) % 7)] * 4)
    return CodeIndexer(collection=collection, embed_model=embed_model, cache_file=tmp_path / ".cache.json")


# ---------------------------------------------------------------------------
# Exact transitive impact set, known by construction of the fixture.
# ---------------------------------------------------------------------------


@requires_tree_sitter
@pytest.mark.asyncio
async def test_find_impact_exact_transitive_set(tmp_path) -> None:
    """a_leaf.target_fn <- b_caller_a.caller_one <- c_caller_b.caller_two <-
    d_caller_c.caller_three is the only chain in this fixture;
    e_other.unrelated calls nothing and must not appear.

    Filenames are prefixed a../b../c../d.. so ``CodeIndexer`` (which resolves
    a call's target against ids known *so far* in its single alphabetical
    pass — see ``_seed_known_ids_from_collection``) processes each callee's
    file before the file that calls it; this is the same ordering
    ``code_indexer_test.py::test_find_callers_traversal`` relies on, not a
    property of this module.
    """
    (tmp_path / "a_leaf.py").write_bytes(b"def target_fn() -> None:\n    pass\n")
    (tmp_path / "b_caller_a.py").write_bytes(b"def caller_one() -> None:\n    target_fn()\n")
    (tmp_path / "c_caller_b.py").write_bytes(b"def caller_two() -> None:\n    caller_one()\n")
    (tmp_path / "d_caller_c.py").write_bytes(b"def caller_three() -> None:\n    caller_two()\n")
    (tmp_path / "e_other.py").write_bytes(b"def unrelated() -> None:\n    pass\n")

    collection = _FakeCollection()
    indexer = _make_indexer(collection, tmp_path)
    result = await indexer.index_directory(str(tmp_path))
    assert result.failed == 0

    impact = await find_impact(collection, root_id="a_leaf.target_fn", max_depth=5)

    assert set(impact.reached) == {"b_caller_a.caller_one", "c_caller_b.caller_two", "d_caller_c.caller_three"}
    assert impact.resolved_edge_count == 3
    assert impact.unresolved_edge_count == 0
    assert impact.depth_capped is False


@requires_tree_sitter
@pytest.mark.asyncio
async def test_find_impact_seeds_members_so_method_callers_reachable(tmp_path) -> None:
    """Asking about the class must still find a caller that only invokes one
    of its methods (#13471's binding requirement: seed root + members)."""
    (tmp_path / "a_widget.py").write_bytes(b"class Widget:\n" b"    def render(self) -> None:\n" b"        pass\n")
    (tmp_path / "b_caller_d.py").write_bytes(b"def caller_four() -> None:\n" b"    w = Widget()\n" b"    w.render()\n")

    collection = _FakeCollection()
    indexer = _make_indexer(collection, tmp_path)
    result = await indexer.index_directory(str(tmp_path))
    assert result.failed == 0

    impact = await find_impact(collection, root_id="a_widget.Widget", max_depth=5)

    assert "b_caller_d.caller_four" in impact.reached
    assert "a_widget.Widget.render" in impact.seed_ids
    assert "a_widget.Widget" in impact.seed_ids


# ---------------------------------------------------------------------------
# Cycles — the graph is not a DAG (mutual recursion terminates and reports).
# ---------------------------------------------------------------------------


@requires_tree_sitter
@pytest.mark.asyncio
async def test_find_impact_handles_cycles(tmp_path) -> None:
    """func_a calls func_b and func_b calls func_a. The walk must terminate
    (the test itself would hang past its timeout otherwise) and must still
    report the edge that closes the cycle."""
    (tmp_path / "cyclic.py").write_bytes(
        b"def func_a() -> None:\n" b"    func_b()\n\n" b"def func_b() -> None:\n" b"    func_a()\n"
    )

    collection = _FakeCollection()
    indexer = _make_indexer(collection, tmp_path)
    result = await indexer.index_directory(str(tmp_path))
    assert result.failed == 0

    impact = await find_impact(collection, root_id="cyclic.func_a", max_depth=5)

    assert impact.reached == ["cyclic.func_b"]
    assert impact.depth_capped is False
    assert impact.resolved_edge_count == 2
    pairs = {(e["source_id"], e["target_id"]) for e in impact.edges}
    assert pairs == {("cyclic.func_b", "cyclic.func_a"), ("cyclic.func_a", "cyclic.func_b")}


# ---------------------------------------------------------------------------
# Ambiguous/unresolved edges are reported, never silently followed or dropped.
# ---------------------------------------------------------------------------


@requires_tree_sitter
@pytest.mark.asyncio
async def test_find_impact_reports_ambiguous_edge_not_silently_dropped(tmp_path) -> None:
    """Two functions named ``process`` exist; a caller with no import context
    calling ``process()`` cannot be resolved to either — it must show up in
    ``skipped_edges``, not in ``reached`` (not followed) and not vanish
    (not dropped). Filenames prefixed a../b../c.. so both ``process``
    definitions are known before ``c_caller_amb.py`` resolves its call —
    otherwise the ambiguity (2 candidates) would look like a 0-candidate
    unresolved call instead (see the ordering note on the exact-set test)."""
    (tmp_path / "a_process_one.py").write_bytes(b"def process() -> None:\n    pass\n")
    (tmp_path / "b_process_two.py").write_bytes(b"def process() -> None:\n    pass\n")
    (tmp_path / "c_caller_amb.py").write_bytes(b"def call_process() -> None:\n    process()\n")

    collection = _FakeCollection()
    indexer = _make_indexer(collection, tmp_path)
    result = await indexer.index_directory(str(tmp_path))
    assert result.failed == 0

    impact = await find_impact(collection, root_id="a_process_one.process", max_depth=3)

    assert impact.reached == []
    assert impact.resolved_edge_count == 0
    assert impact.unresolved_edge_count == 1
    skipped = impact.skipped_edges[0]
    assert skipped["source_id"] == "c_caller_amb.call_process"
    assert skipped["target_name"] == "process"
    assert skipped["origin"] == "ambiguous"
    assert skipped["candidate_count"] == 2


# ---------------------------------------------------------------------------
# Depth cap — a truncated walk must say so, not report as if it were complete.
# ---------------------------------------------------------------------------


@requires_tree_sitter
@pytest.mark.asyncio
async def test_find_impact_depth_cap_is_visible(tmp_path) -> None:
    """A 4-hop chain, walked with max_depth=2, must reach only the first two
    hops and clearly flag that hops 3-4 were never examined. The same
    fixture walked without a cap proves hops 3-4 do exist, so the cut is the
    depth limit, not a fixture-wiring gap. Filenames prefixed a../e.. so each
    callee's file is indexed before its caller's (see the ordering note on
    the exact-set test)."""
    (tmp_path / "a_leaf2.py").write_bytes(b"def target_fn2() -> None:\n    pass\n")
    (tmp_path / "b_hop1.py").write_bytes(b"def hop_one() -> None:\n    target_fn2()\n")
    (tmp_path / "c_hop2.py").write_bytes(b"def hop_two() -> None:\n    hop_one()\n")
    (tmp_path / "d_hop3.py").write_bytes(b"def hop_three() -> None:\n    hop_two()\n")
    (tmp_path / "e_hop4.py").write_bytes(b"def hop_four() -> None:\n    hop_three()\n")

    collection = _FakeCollection()
    indexer = _make_indexer(collection, tmp_path)
    result = await indexer.index_directory(str(tmp_path))
    assert result.failed == 0

    capped = await find_impact(collection, root_id="a_leaf2.target_fn2", max_depth=2)
    assert set(capped.reached) == {"b_hop1.hop_one", "c_hop2.hop_two"}
    assert capped.depth_capped is True
    assert capped.depth_capped_frontier == ["c_hop2.hop_two"]
    assert capped.max_depth == 2
    assert capped.depth_reached == 2

    uncapped = await find_impact(collection, root_id="a_leaf2.target_fn2", max_depth=10)
    assert set(uncapped.reached) == {
        "b_hop1.hop_one",
        "c_hop2.hop_two",
        "d_hop3.hop_three",
        "e_hop4.hop_four",
    }
    assert uncapped.depth_capped is False
