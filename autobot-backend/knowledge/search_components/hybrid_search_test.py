# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for HybridSearcher RRF provenance (Issue #17207).

Covers:
- process_rrf_results records each view's rank and contribution
- a fact found by 3 views is distinguishable from a fact found by 1
- legacy callers omitting ``contributions`` keep the previous behaviour
- a later view's fields are merged, not discarded; the first view wins on conflict
- a view that ran and returned nothing is distinguishable from one that never ran
- one failing view no longer collapses the search into a semantic-only re-run
- every view failing still propagates, as before
- score / rrf_score values and result ordering are unchanged (regression pin)
"""

from unittest.mock import AsyncMock, patch

import pytest

from knowledge.search_components.hybrid_search import (
    VIEW_STATUS_FAILED,
    VIEW_STATUS_OK,
    HybridSearcher,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fact(fact_id: str, **extra):
    """A result shaped the way the retrieval legs emit them."""
    return {"metadata": {"fact_id": fact_id}, **extra}


def _searcher(semantic=None, keyword=None) -> HybridSearcher:
    """Build a searcher whose retrieval views return the supplied fixtures."""
    return HybridSearcher(
        semantic_search_func=AsyncMock(return_value=semantic if semantic is not None else []),
        keyword_search_func=AsyncMock(return_value=keyword if keyword is not None else []),
    )


K = HybridSearcher.RRF_K
SEM = HybridSearcher.VIEW_SEMANTIC
KW = HybridSearcher.VIEW_KEYWORD


# ---------------------------------------------------------------------------
# Provenance capture
# ---------------------------------------------------------------------------


class TestProvenanceCapture:
    def test_records_rank_and_contribution_per_view(self):
        """Each view should retain its rank and reciprocal-rank contribution."""
        searcher = _searcher()
        scores, result_map, contributions = {}, {}, {}

        searcher.process_rrf_results([_fact("A"), _fact("B")], scores, result_map, K, SEM, contributions)

        assert contributions["A"][SEM] == {"rank": 0, "contribution": 1 / (K + 1)}
        assert contributions["B"][SEM] == {"rank": 1, "contribution": 1 / (K + 2)}

    def test_three_views_distinguishable_from_one(self):
        """A fact agreed on by 3 views must not look like a fact found by 1."""
        searcher = _searcher()
        scores, result_map, contributions = {}, {}, {}

        for view in ("sem", "kw", "graph"):
            searcher.process_rrf_results([_fact("agreed")], scores, result_map, K, view, contributions)
        searcher.process_rrf_results([_fact("lonely")], scores, result_map, K, "sem", contributions)

        assert len(contributions["agreed"]) == 3
        assert len(contributions["lonely"]) == 1
        assert set(contributions["agreed"]) == {"sem", "kw", "graph"}

    def test_view_count_surfaces_on_results(self):
        """Fused results should expose the number and identities of contributing views."""
        searcher = _searcher()
        scores, result_map, contributions = {}, {}, {}
        searcher.process_rrf_results([_fact("A")], scores, result_map, K, SEM, contributions)
        searcher.process_rrf_results([_fact("A")], scores, result_map, K, KW, contributions)

        built = searcher.build_rrf_results(scores, result_map, 10, contributions)

        assert built[0]["view_count"] == 2
        assert set(built[0]["view_contributions"]) == {SEM, KW}

    def test_legacy_caller_without_contributions_unchanged(self):
        """Omitting the accumulator must behave exactly as before Issue #17207."""
        searcher = _searcher()
        scores, result_map = {}, {}

        searcher.process_rrf_results([_fact("A"), _fact("B")], scores, result_map, K, SEM)

        assert scores == {"A": 1 / (K + 1), "B": 1 / (K + 2)}
        built = searcher.build_rrf_results(scores, result_map, 10)
        assert built[0]["view_contributions"] == {}
        assert built[0]["view_count"] == 0


# ---------------------------------------------------------------------------
# Result merging
# ---------------------------------------------------------------------------


class TestResultMerging:
    def test_later_view_fields_are_merged(self):
        """Fields unique to a later view should survive result fusion."""
        searcher = _searcher()
        scores, result_map, contributions = {}, {}, {}

        searcher.process_rrf_results([_fact("A", content="sem")], scores, result_map, K, SEM, contributions)
        searcher.process_rrf_results(
            [_fact("A", content="kw", keyword_score=0.9)], scores, result_map, K, KW, contributions
        )

        assert result_map["A"]["keyword_score"] == 0.9, "later view's field was discarded"

    def test_first_view_wins_on_conflict(self):
        """A later view should not overwrite fields captured from the first view."""
        searcher = _searcher()
        scores, result_map, contributions = {}, {}, {}

        searcher.process_rrf_results([_fact("A", content="sem")], scores, result_map, K, SEM, contributions)
        searcher.process_rrf_results([_fact("A", content="kw")], scores, result_map, K, KW, contributions)

        assert result_map["A"]["content"] == "sem"

    def test_nested_metadata_from_a_later_view_survives(self):
        """A later view's unique metadata field must not be lost to the first view's dict.

        Both legs always supply ``metadata`` (it carries fact_id), so a flat
        ``setdefault`` treats it as an already-present key and discards the later
        view's whole mapping -- the field-level loss #17207 exists to stop, one
        level down.
        """
        searcher = _searcher()
        scores, result_map, contributions = {}, {}, {}

        sem = _fact("A")
        kw = _fact("A")
        kw["metadata"]["source"] = "keyword-index"
        searcher.process_rrf_results([sem], scores, result_map, K, SEM, contributions)
        searcher.process_rrf_results([kw], scores, result_map, K, KW, contributions)

        assert result_map["A"]["metadata"]["source"] == "keyword-index"
        assert result_map["A"]["metadata"]["fact_id"] == "A"

    def test_first_view_wins_on_a_nested_conflict(self):
        """Merging nested mappings must not weaken first-view-wins for conflicts."""
        searcher = _searcher()
        scores, result_map, contributions = {}, {}, {}

        sem = _fact("A")
        sem["metadata"]["source"] = "semantic-index"
        kw = _fact("A")
        kw["metadata"]["source"] = "keyword-index"
        searcher.process_rrf_results([sem], scores, result_map, K, SEM, contributions)
        searcher.process_rrf_results([kw], scores, result_map, K, KW, contributions)

        assert result_map["A"]["metadata"]["source"] == "semantic-index"


# ---------------------------------------------------------------------------
# View execution status -- "found nothing" is not "did not look"
# ---------------------------------------------------------------------------


class TestViewStatus:
    @pytest.mark.asyncio
    async def test_empty_view_distinguishable_from_failed_view(self):
        """Status should distinguish a successful empty view from a failed view."""
        empty = _searcher(semantic=[_fact("A")], keyword=[])
        _, empty_status = await empty.search_with_provenance("q", 5)

        broken = HybridSearcher(
            semantic_search_func=AsyncMock(return_value=[_fact("A")]),
            keyword_search_func=AsyncMock(side_effect=RuntimeError("redis down")),
        )
        _, broken_status = await broken.search_with_provenance("q", 5)

        assert empty_status["views"][KW] == {"status": VIEW_STATUS_OK, "hit_count": 0, "error": None}
        assert broken_status["views"][KW]["status"] == VIEW_STATUS_FAILED
        assert "redis down" in broken_status["views"][KW]["error"]

    @pytest.mark.asyncio
    async def test_surviving_view_kept_without_semantic_rerun(self):
        """One failing leg must not discard the other, nor re-run the survivor."""
        semantic = AsyncMock(return_value=[_fact("A")])
        searcher = HybridSearcher(
            semantic_search_func=semantic,
            keyword_search_func=AsyncMock(side_effect=RuntimeError("boom")),
        )

        results, status = await searcher.search_with_provenance("q", 5)

        assert [r["metadata"]["fact_id"] for r in results] == ["A"]
        assert semantic.await_count == 1, "semantic leg was re-run by the fallback path"
        assert status["fused"] is True
        assert status["views"][SEM]["status"] == VIEW_STATUS_OK

    @pytest.mark.asyncio
    async def test_all_views_failing_propagates(self):
        """Total retrieval failure should remain visible to the caller."""
        searcher = HybridSearcher(
            semantic_search_func=AsyncMock(side_effect=RuntimeError("sem down")),
            keyword_search_func=AsyncMock(side_effect=RuntimeError("kw down")),
        )

        with pytest.raises(RuntimeError):
            await searcher.search_with_provenance("q", 5)

    @pytest.mark.asyncio
    async def test_fusion_failure_falls_back_and_says_so(self):
        """Fusion errors should trigger semantic fallback and an explicit status."""
        searcher = _searcher(semantic=[_fact("A")], keyword=[_fact("B")])

        with patch.object(searcher, "build_rrf_results", side_effect=RuntimeError("fuse fail")):
            results, status = await searcher.search_with_provenance("q", 5)

        assert status["fused"] is False
        assert "fuse fail" in status["error"]
        assert [r["metadata"]["fact_id"] for r in results] == ["A"]

    @pytest.mark.asyncio
    async def test_fusion_failure_keeps_what_the_views_already_reported(self):
        """A fusion error must not throw away view status that was already classified.

        The views ran, succeeded and were classified before fusion raised. Reporting
        ``views: {}`` there says "nothing is known about the views" when in fact
        everything is -- the same collapse of "did not look" into "found nothing"
        this whole change exists to stop, one level up.
        """
        searcher = _searcher(semantic=[_fact("A")], keyword=[_fact("B")])

        with patch.object(searcher, "build_rrf_results", side_effect=RuntimeError("fuse fail")):
            _results, status = await searcher.search_with_provenance("q", 5)

        assert set(status["views"]) == {SEM, KW}, "the classified view status was discarded on a fusion failure"
        assert all(v["status"] == "ok" for v in status["views"].values())

    @pytest.mark.asyncio
    async def test_total_view_failure_still_reports_no_view_status(self):
        """The contrast: when the views themselves fail there IS nothing to keep.

        _run_views raises before returning, so no classification exists. An empty
        views map here is the honest answer, not a discarded one.
        """
        searcher = _searcher()
        searcher.semantic_search = AsyncMock(side_effect=RuntimeError("sem down"))
        searcher.keyword_search = AsyncMock(side_effect=RuntimeError("kw down"))

        with pytest.raises(RuntimeError):
            await searcher.search_with_provenance("q", 5)

    @pytest.mark.asyncio
    async def test_fallback_results_carry_the_documented_keys(self):
        """The degraded path must not hand back a different result shape.

        The fused path always attaches ``view_contributions`` and ``view_count``. If
        the fallback omits them, a caller reading them unconditionally raises
        KeyError only when fusion has already failed -- the moment it is least
        likely to be noticed. They are empty, not invented: no fusion ran, so no
        view agreement was measured, and ``fused`` is what says so.
        """
        searcher = _searcher(semantic=[_fact("A")], keyword=[_fact("B")])

        with patch.object(searcher, "build_rrf_results", side_effect=RuntimeError("fuse fail")):
            results, status = await searcher.search_with_provenance("q", 5)

        assert results, "fallback returned nothing, so the shape assertion would be vacuous"
        for result in results:
            assert result["view_contributions"] == {}
            assert result["view_count"] == 0
        assert status["fused"] is False, "an empty map here means not-fused, not no-agreement"


# ---------------------------------------------------------------------------
# Regression pin -- ranking behaviour is unchanged by Issue #17207
# ---------------------------------------------------------------------------


class TestRankingUnchanged:
    @pytest.mark.asyncio
    async def test_scores_and_ordering_match_rrf_definition(self):
        """B is found by both views, so it must outrank A and C.

        Values are derived from the RRF definition (1 / (k + rank + 1)), not from the
        implementation, so this pins behaviour rather than restating the code.
        """
        searcher = _searcher(
            semantic=[_fact("A"), _fact("B")],
            keyword=[_fact("B"), _fact("C")],
        )

        results, status = await searcher.search_with_provenance("q", 10)

        assert [r["metadata"]["fact_id"] for r in results] == ["B", "A", "C"]
        by_id = {r["metadata"]["fact_id"]: r for r in results}
        assert by_id["A"]["rrf_score"] == pytest.approx(1 / (K + 1))
        assert by_id["B"]["rrf_score"] == pytest.approx(1 / (K + 2) + 1 / (K + 1))
        assert by_id["C"]["rrf_score"] == pytest.approx(1 / (K + 2))
        assert by_id["B"]["score"] == pytest.approx(1.0)
        assert by_id["B"]["view_count"] == 2
        assert by_id["A"]["view_count"] == 1
        assert status["views"][SEM]["hit_count"] == 2

    @pytest.mark.asyncio
    async def test_search_returns_bare_list(self):
        """The public ``search`` contract is unchanged -- still a list of results."""
        searcher = _searcher(semantic=[_fact("A")], keyword=[])

        results = await searcher.search("q", 5)

        assert isinstance(results, list)
        assert results[0]["metadata"]["fact_id"] == "A"

    @pytest.mark.asyncio
    async def test_board_filter_merged_into_semantic_where_clause(self):
        """Issue #3242 behaviour must survive the refactor."""
        semantic = AsyncMock(return_value=[])
        searcher = HybridSearcher(semantic, AsyncMock(return_value=[]))

        await searcher.search_with_provenance("q", 5, category="docs", board_filter={"board": "b1"})

        assert semantic.await_args.kwargs["filters"] == {"category": "docs", "board": "b1"}
