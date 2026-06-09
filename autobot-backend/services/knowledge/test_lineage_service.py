# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for LineageService and SynthesisRun.

Issue #4681: Evolutionary lineage tracking — ancestor traversal, best-ancestor
selection, rollback, and version stamping.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing lineage_service
# ---------------------------------------------------------------------------

for _mod in (
    "autobot_shared",
    "autobot_shared.redis_client",
    "autobot_shared.ssot_config",
    "utils",
    "utils.chromadb_client",
):
    if _mod not in sys.modules:
        stub = types.ModuleType(_mod)
        stub.__path__ = []  # type: ignore[attr-defined]
        stub.__package__ = _mod
        sys.modules[_mod] = stub

from services.knowledge.lineage_service import (  # noqa: E402
    LineageService,
    SynthesisRun,
    get_lineage_service,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _entry(
    run_id: str,
    parent_run_id: str | None = None,
    score: float = 0.5,
    collection: str = "kb_synthesis",
    ran_at: str = "2026-01-01T00:00:00+00:00",
) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "parent_run_id": parent_run_id or "",
        "synthesis_ids": [run_id],
        "source_docs": [],
        "source_doc_ids": [],
        "prompt_template": "default",
        "prompt_variant": "default",
        "score": str(score),
        "collection_name": collection,
        "ran_at": ran_at,
        "duration_ms": 100,
        "llm_model": "test_model",
    }


def _make_provenance_log(entries: List[Dict[str, Any]]) -> MagicMock:
    """Build a mock SynthesisProvenanceLog from a flat list of entries.

    - get_recent returns the full list (retained for other callers).
    - get_by_run_id does an O(1) dict lookup by run_id (used by get_ancestors).
    - get_best_run_id_for_collection returns the highest-scoring run_id for the
      collection (used by get_best_ancestor, Issue #4788).
    """
    by_id = {e["run_id"]: e for e in entries if e.get("run_id")}

    async def _get_by_run_id(run_id: str):
        entry = by_id.get(run_id)
        if entry is None:
            return None
        # Normalise parent_run_id the same way SynthesisProvenanceLog does.
        result = dict(entry)
        result.setdefault("parent_run_id", None)
        if result["parent_run_id"] == "":
            result["parent_run_id"] = None
        result.setdefault("prompt_variant", result.get("prompt_template", ""))
        result.setdefault("collection_name", "")
        return result

    async def _get_best_run_id_for_collection(collection_name: str):
        candidates = [e for e in entries if e.get("collection_name") == collection_name and e.get("run_id")]
        if not candidates:
            return None
        best = max(candidates, key=lambda e: float(e.get("score", 0.0)))
        return best["run_id"]

    log = MagicMock()
    log.get_recent = AsyncMock(return_value=entries)
    log.get_by_run_id = AsyncMock(side_effect=_get_by_run_id)
    log.get_best_run_id_for_collection = AsyncMock(side_effect=_get_best_run_id_for_collection)
    return log


def _make_collection_factory(get_result: Dict | None = None):
    """Return an async collection factory mock."""
    col = AsyncMock()
    col.get = AsyncMock(return_value=get_result or {"ids": [], "metadatas": [], "documents": []})
    col.upsert = AsyncMock()
    col.query = AsyncMock(return_value={"ids": [[]], "metadatas": [[]], "documents": [[]]})

    async def factory(name: str):
        return col

    return factory, col


# ---------------------------------------------------------------------------
# Tests: SynthesisRun.from_provenance_entry
# ---------------------------------------------------------------------------


class TestSynthesisRunFromProvenance:
    def test_basic_fields(self) -> None:
        entry = _entry("run-1", score=0.8)
        run = SynthesisRun.from_provenance_entry(entry)
        assert run.run_id == "run-1"
        assert abs(run.score - 0.8) < 1e-6
        assert run.collection_name == "kb_synthesis"

    def test_parent_run_id_empty_string_becomes_none(self) -> None:
        entry = _entry("run-1", parent_run_id="")
        run = SynthesisRun.from_provenance_entry(entry)
        assert run.parent_run_id is None

    def test_parent_run_id_set(self) -> None:
        entry = _entry("run-2", parent_run_id="run-1")
        run = SynthesisRun.from_provenance_entry(entry)
        assert run.parent_run_id == "run-1"

    def test_invalid_ran_at_falls_back_to_now(self) -> None:
        entry = _entry("run-1")
        entry["ran_at"] = "not-a-date"
        run = SynthesisRun.from_provenance_entry(entry)
        assert run.timestamp is not None
        assert run.timestamp.tzinfo is not None

    def test_naive_ran_at_gets_utc_tzinfo(self) -> None:
        entry = _entry("run-1")
        entry["ran_at"] = "2026-01-01T00:00:00"  # no tz
        run = SynthesisRun.from_provenance_entry(entry)
        assert run.timestamp.tzinfo is not None

    def test_output_summary_id_from_synthesis_ids(self) -> None:
        entry = _entry("run-x")
        entry["synthesis_ids"] = ["synth-abc"]
        run = SynthesisRun.from_provenance_entry(entry)
        assert run.output_summary_id == "synth-abc"


# ---------------------------------------------------------------------------
# Tests: get_ancestors
# ---------------------------------------------------------------------------


class TestGetAncestors:
    @pytest.mark.asyncio
    async def test_single_run_no_parent(self) -> None:
        entries = [_entry("run-1")]
        log = _make_provenance_log(entries)
        factory, _ = _make_collection_factory()
        svc = LineageService(log, factory)

        chain = await svc.get_ancestors("run-1")
        assert len(chain) == 1
        assert chain[0].run_id == "run-1"

    @pytest.mark.asyncio
    async def test_chain_traversed_correctly(self) -> None:
        entries = [
            _entry("run-3", parent_run_id="run-2"),
            _entry("run-2", parent_run_id="run-1"),
            _entry("run-1"),
        ]
        log = _make_provenance_log(entries)
        factory, _ = _make_collection_factory()
        svc = LineageService(log, factory)

        chain = await svc.get_ancestors("run-3")
        assert [r.run_id for r in chain] == ["run-1", "run-2", "run-3"]

    @pytest.mark.asyncio
    async def test_depth_limit_respected(self) -> None:
        entries = [
            _entry("run-4", parent_run_id="run-3"),
            _entry("run-3", parent_run_id="run-2"),
            _entry("run-2", parent_run_id="run-1"),
            _entry("run-1"),
        ]
        log = _make_provenance_log(entries)
        factory, _ = _make_collection_factory()
        svc = LineageService(log, factory)

        chain = await svc.get_ancestors("run-4", depth=2)
        # At depth=2 we stop after 2 hops: run-4 -> run-3 -> run-2 (3 nodes)
        assert len(chain) == 3
        assert chain[-1].run_id == "run-4"

    @pytest.mark.asyncio
    async def test_missing_run_returns_empty(self) -> None:
        log = _make_provenance_log([])
        factory, _ = _make_collection_factory()
        svc = LineageService(log, factory)

        chain = await svc.get_ancestors("nonexistent")
        assert chain == []

    @pytest.mark.asyncio
    async def test_cycle_protection(self) -> None:
        """Circular parent links must not cause infinite loop."""
        entries = [
            _entry("run-a", parent_run_id="run-b"),
            _entry("run-b", parent_run_id="run-a"),
        ]
        log = _make_provenance_log(entries)
        factory, _ = _make_collection_factory()
        svc = LineageService(log, factory)

        chain = await svc.get_ancestors("run-a", depth=20)
        # Should terminate without infinite loop; both nodes visited at most once
        visited = {r.run_id for r in chain}
        assert len(chain) == len(visited)


# ---------------------------------------------------------------------------
# Tests: get_best_ancestor
# ---------------------------------------------------------------------------


class TestGetBestAncestor:
    @pytest.mark.asyncio
    async def test_returns_highest_score(self) -> None:
        entries = [
            _entry("run-1", score=0.3, collection="kb_synthesis"),
            _entry("run-2", score=0.9, collection="kb_synthesis"),
            _entry("run-3", score=0.6, collection="kb_synthesis"),
        ]
        log = _make_provenance_log(entries)
        factory, _ = _make_collection_factory()
        svc = LineageService(log, factory)

        best = await svc.get_best_ancestor("kb_synthesis")
        assert best is not None
        assert best.run_id == "run-2"

    @pytest.mark.asyncio
    async def test_filters_by_collection(self) -> None:
        entries = [
            _entry("run-A", score=0.99, collection="other_collection"),
            _entry("run-B", score=0.5, collection="kb_synthesis"),
        ]
        log = _make_provenance_log(entries)
        factory, _ = _make_collection_factory()
        svc = LineageService(log, factory)

        best = await svc.get_best_ancestor("kb_synthesis")
        assert best is not None
        assert best.run_id == "run-B"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_runs(self) -> None:
        log = _make_provenance_log([])
        factory, _ = _make_collection_factory()
        svc = LineageService(log, factory)

        best = await svc.get_best_ancestor("kb_synthesis")
        assert best is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_matching_collection(self) -> None:
        entries = [_entry("run-1", collection="other")]
        log = _make_provenance_log(entries)
        factory, _ = _make_collection_factory()
        svc = LineageService(log, factory)

        best = await svc.get_best_ancestor("kb_synthesis")
        assert best is None


# ---------------------------------------------------------------------------
# Tests: get_entity_history
# ---------------------------------------------------------------------------


class TestGetEntityHistory:
    @pytest.mark.asyncio
    async def test_returns_versions_sorted_ascending(self) -> None:
        col_result = {
            "ids": ["e1_v2", "e1_v1"],
            "metadatas": [
                {"entity_id": "e1", "lineage_version": 2},
                {"entity_id": "e1", "lineage_version": 1},
            ],
            "documents": ["v2 content", "v1 content"],
        }
        log = _make_provenance_log([])
        factory, col = _make_collection_factory(col_result)
        svc = LineageService(log, factory)

        history = await svc.get_entity_history("e1")
        assert len(history) == 2
        assert history[0]["lineage_version"] == 1
        assert history[1]["lineage_version"] == 2

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_history(self) -> None:
        log = _make_provenance_log([])
        factory, _ = _make_collection_factory()  # returns empty ids
        svc = LineageService(log, factory)

        history = await svc.get_entity_history("nonexistent")
        assert history == []

    @pytest.mark.asyncio
    async def test_handles_collection_error(self) -> None:
        log = _make_provenance_log([])

        async def broken_factory(name: str) -> None:
            raise RuntimeError("ChromaDB unavailable")

        svc = LineageService(log, broken_factory)
        history = await svc.get_entity_history("e1")
        assert history == []


# ---------------------------------------------------------------------------
# Tests: rollback_entity
# ---------------------------------------------------------------------------


class TestRollbackEntity:
    @pytest.mark.asyncio
    async def test_rollback_raises_when_version_not_found(self) -> None:
        log = _make_provenance_log([])
        factory, _ = _make_collection_factory()  # empty history
        svc = LineageService(log, factory)

        with pytest.raises(ValueError, match="No version"):
            await svc.rollback_entity("e1", to_version=5)

    @pytest.mark.asyncio
    async def test_rollback_raises_when_no_source_collection(self) -> None:
        col_result = {
            "ids": ["e1_v1"],
            "metadatas": [{"entity_id": "e1", "lineage_version": 1}],  # no lineage_source_collection
            "documents": ["v1 content"],
        }
        log = _make_provenance_log([])
        factory, _ = _make_collection_factory(col_result)
        svc = LineageService(log, factory)

        with pytest.raises(ValueError, match="no lineage_source_collection"):
            await svc.rollback_entity("e1", to_version=1)

    @pytest.mark.asyncio
    async def test_rollback_upserts_to_live_collection(self):
        col_result = {
            "ids": ["e1_v1"],
            "metadatas": [
                {
                    "entity_id": "e1",
                    "lineage_version": 1,
                    "lineage_source_collection": "kb_synthesis",
                }
            ],
            "documents": ["v1 content"],
        }
        history_col = AsyncMock()
        history_col.get = AsyncMock(return_value=col_result)
        history_col.upsert = AsyncMock()

        live_col = AsyncMock()
        live_col.get = AsyncMock(return_value={"ids": [], "metadatas": []})
        live_col.upsert = AsyncMock()

        call_count = 0

        async def smart_factory(name: str):
            nonlocal call_count
            call_count += 1
            if name == "kb_entity_history":
                return history_col
            return live_col

        log = _make_provenance_log([])
        svc = LineageService(log, smart_factory)
        await svc.rollback_entity("e1", to_version=1)

        live_col.upsert.assert_awaited_once()
        call_kwargs = live_col.upsert.call_args.kwargs
        assert call_kwargs["ids"] == ["e1"]
        assert call_kwargs["documents"] == ["v1 content"]


# ---------------------------------------------------------------------------
# Tests: stamp_entity_version
# ---------------------------------------------------------------------------


class TestStampEntityVersion:
    @pytest.mark.asyncio
    async def test_upserts_version_to_history_collection(self) -> None:
        log = _make_provenance_log([])
        factory, col = _make_collection_factory()
        svc = LineageService(log, factory)

        await svc.stamp_entity_version(
            entity_id="e1",
            content="Some content",
            metadata={"doc_type": "architecture"},
            source_run_id="run-1",
            source_collection="kb_synthesis",
        )

        col.upsert.assert_awaited_once()
        call_kwargs = col.upsert.call_args.kwargs
        assert "e1_v" in call_kwargs["ids"][0]
        assert call_kwargs["documents"] == ["Some content"]
        meta = call_kwargs["metadatas"][0]
        assert meta["entity_id"] == "e1"
        assert meta["lineage_source_run_id"] == "run-1"
        assert meta["lineage_source_collection"] == "kb_synthesis"

    @pytest.mark.asyncio
    async def test_swallows_collection_error(self) -> None:
        log = _make_provenance_log([])

        async def broken_factory(name: str) -> None:
            raise RuntimeError("ChromaDB unavailable")

        svc = LineageService(log, broken_factory)
        # Must not raise
        await svc.stamp_entity_version("e1", "content", {}, "run-1", "col")


# ---------------------------------------------------------------------------
# Tests: get_lineage_service singleton
# ---------------------------------------------------------------------------


def test_get_lineage_service_singleton() -> None:
    import services.knowledge.lineage_service as _mod

    _mod._lineage_service = None
    log = _make_provenance_log([])
    factory, _ = _make_collection_factory()

    svc1 = get_lineage_service(log, factory)
    svc2 = get_lineage_service(MagicMock(), factory)

    assert svc1 is svc2
