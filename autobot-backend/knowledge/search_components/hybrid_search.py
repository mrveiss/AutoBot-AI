# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Hybrid Search Module

Issue #381: Extracted from search.py god class refactoring.
Contains hybrid search with Reciprocal Rank Fusion (RRF).

Issue #17207: fusion preserves per-view provenance. RRF previously accumulated every
retrieval leg into a single float, so an item found by one view at rank 0 and an item
found by three views at rank 5 were indistinguishable once fused. Agreement across
independent views is the strongest relevance signal available without labels, so each
view's rank and contribution is now recorded per item alongside the existing scalar.

Ranking behaviour is unchanged here: ``score`` and ``rrf_score`` keep their meaning and
ordering. Consuming multiplicity to alter ranking is #17208.
"""

import asyncio
from typing import Any, Callable, Coroutine, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Per-view outcome markers. ``OK`` means the view ran to completion, so a zero hit count
# under ``OK`` is a real "searched and found nothing". ``FAILED`` means the view never
# looked, which must never be readable as an empty result.
VIEW_STATUS_OK = "ok"
VIEW_STATUS_FAILED = "failed"

# fact_id -> view -> {"rank": int, "contribution": float}
ContributionMap = Dict[str, Dict[str, Dict[str, float]]]


class HybridSearcher:
    """
    Performs hybrid search combining semantic and keyword results.

    Uses Reciprocal Rank Fusion (RRF) to combine rankings from
    different search methods for improved relevance.
    """

    # Standard RRF constant
    RRF_K = 60

    # View identities. These double as the ``prefix`` used to synthesise a fallback id
    # for results carrying neither ``metadata.fact_id`` nor ``node_id``, so their values
    # are load-bearing and must not be renamed casually.
    VIEW_SEMANTIC = "sem"
    VIEW_KEYWORD = "kw"

    def __init__(
        self,
        semantic_search_func: Callable[..., Coroutine],
        keyword_search_func: Callable[..., Coroutine],
    ):
        """
        Initialize hybrid searcher.

        Args:
            semantic_search_func: Async function for semantic search
            keyword_search_func: Async function for keyword search
        """
        self.semantic_search = semantic_search_func
        self.keyword_search = keyword_search_func

    def process_rrf_results(
        self,
        results: List[Dict[str, Any]],
        rrf_scores: Dict[str, float],
        result_map: Dict[str, Dict[str, Any]],
        k: int,
        prefix: str,
        contributions: ContributionMap | None = None,
    ) -> None:
        """Process results for RRF scoring. Issue #281: Extracted helper.

        Issue #17207: records each view's rank and contribution in ``contributions``
        rather than folding them irreversibly into ``rrf_scores``. Later views also
        merge their fields into an already-seen result instead of being discarded
        outright -- first view still wins on conflict, so existing keys are untouched.

        Args:
            contributions: Optional per-view provenance accumulator. Omitted by legacy
                callers, in which case behaviour is exactly as before. ``prefix`` is the
                view identity it is keyed by.
        """
        for rank, result in enumerate(results):
            fact_id = result.get("metadata", {}).get("fact_id") or result.get("node_id", f"{prefix}_{rank}")
            contribution = 1 / (k + rank + 1)
            rrf_scores[fact_id] = rrf_scores.get(fact_id, 0) + contribution
            if contributions is not None:
                contributions.setdefault(fact_id, {})[prefix] = {
                    "rank": rank,
                    "contribution": contribution,
                }
            if fact_id not in result_map:
                result_map[fact_id] = dict(result)
            else:
                self._merge_view_result(result_map[fact_id], result)

    @staticmethod
    def _merge_view_result(existing: Dict[str, Any], incoming: Dict[str, Any]) -> None:
        """Fill fields the first view did not supply, never overwriting what it did.

        Issue #17207: previously a later view's result object was dropped entirely, so
        any view-specific field it carried was lost.

        Nested mappings are merged by the same rule rather than kept whole. A flat
        ``setdefault`` treats ``metadata`` as one opaque value, so a later view's
        ``metadata.source`` was still discarded whenever the first view supplied any
        ``metadata`` at all -- the same field-level loss this helper exists to stop,
        one level down. Scalar conflicts are unchanged: the first view still wins.
        """
        for key, value in incoming.items():
            if key not in existing:
                existing[key] = value
                continue
            current = existing[key]
            if isinstance(current, dict) and isinstance(value, dict):
                HybridSearcher._merge_view_result(current, value)

    def build_rrf_results(
        self,
        rrf_scores: Dict[str, float],
        result_map: Dict[str, Dict[str, Any]],
        limit: int,
        contributions: ContributionMap | None = None,
    ) -> List[Dict[str, Any]]:
        """Build final RRF-ranked results. Issue #281: Extracted helper.

        Issue #17207: attaches ``view_contributions`` and ``view_count`` to each result.
        Ordering and the ``score`` / ``rrf_score`` values are unchanged.
        """
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
        max_rrf = max(rrf_scores.values()) if rrf_scores else 1
        results = []
        for fact_id in sorted_ids[:limit]:
            result = result_map[fact_id].copy()
            result["score"] = rrf_scores[fact_id] / max_rrf
            result["rrf_score"] = rrf_scores[fact_id]
            per_view = (contributions or {}).get(fact_id, {})
            result["view_contributions"] = per_view
            result["view_count"] = len(per_view)
            results.append(result)
        return results

    @staticmethod
    def _build_semantic_filters(category: str | None, board_filter: Dict[str, Any] | None) -> Dict[str, Any] | None:
        """Merge category and board scoping into one ChromaDB ``where`` clause.

        Issue #3242: board_filter is merged with category so ChromaDB scopes results to
        the requested board.
        """
        filter_parts: Dict[str, Any] = {}
        if category:
            filter_parts["category"] = category
        if board_filter:
            filter_parts.update(board_filter)
        return filter_parts or None

    @staticmethod
    def _classify_view_outcome(view: str, outcome: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Turn one ``gather`` outcome into that view's results and status."""
        if isinstance(outcome, BaseException):
            logger.error("Hybrid search view '%s' failed: %s", view, outcome)
            return [], {"status": VIEW_STATUS_FAILED, "hit_count": 0, "error": str(outcome)}
        return list(outcome), {"status": VIEW_STATUS_OK, "hit_count": len(outcome), "error": None}

    async def _run_views(
        self,
        query: str,
        limit: int,
        category: str | None,
        semantic_filters: Dict[str, Any] | None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """Run every view in parallel, recording each one's outcome separately.

        Issue #17207: a single failing leg no longer collapses the whole search into a
        semantic-only re-run. The surviving view's results are kept and the failed view
        is reported as FAILED, so callers can tell "this view found nothing" from "this
        view never ran". If every view fails the first error is re-raised, preserving
        the previous propagation behaviour for total failure.
        """
        semantic_task = asyncio.create_task(
            self.semantic_search(query, top_k=limit, filters=semantic_filters, mode="vector")
        )
        keyword_task = asyncio.create_task(self.keyword_search(query, limit, category))
        outcomes = await asyncio.gather(semantic_task, keyword_task, return_exceptions=True)

        legs: List[List[Dict[str, Any]]] = []
        views: Dict[str, Dict[str, Any]] = {}
        for view, outcome in zip((self.VIEW_SEMANTIC, self.VIEW_KEYWORD), outcomes):
            leg, status = self._classify_view_outcome(view, outcome)
            legs.append(leg)
            views[view] = status

        if all(status["status"] == VIEW_STATUS_FAILED for status in views.values()):
            raise next(o for o in outcomes if isinstance(o, BaseException))

        return legs[0], legs[1], {"fused": True, "error": None, "views": views}

    async def search_with_provenance(
        self,
        query: str,
        limit: int,
        category: str | None = None,
        board_filter: Dict[str, Any] | None = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Hybrid search returning results alongside per-view execution status.

        Issue #17207: ``search`` returns only the result list, which cannot express
        which views ran when the result list is empty -- exactly the case where the
        distinction matters most. This variant returns both.

        Returns:
            (results, status) where status is
            ``{"fused": bool, "error": str | None, "views": {view: {...}}}``
        """
        semantic_filters = self._build_semantic_filters(category, board_filter)
        # Bound outside the try: when the failure is in FUSION rather than in the
        # views, the views already ran and were classified, and discarding that is
        # the exact loss this issue is about. Total view failure leaves it empty,
        # because _run_views raises before returning and there is nothing to keep.
        classified_views: Dict[str, Dict[str, Any]] = {}
        try:
            semantic_results, keyword_results, status = await self._run_views(query, limit, category, semantic_filters)
            classified_views = status.get("views", {})
            rrf_scores: Dict[str, float] = {}
            result_map: Dict[str, Dict[str, Any]] = {}
            contributions: ContributionMap = {}

            for leg, view in ((semantic_results, self.VIEW_SEMANTIC), (keyword_results, self.VIEW_KEYWORD)):
                self.process_rrf_results(leg, rrf_scores, result_map, self.RRF_K, view, contributions)

            return self.build_rrf_results(rrf_scores, result_map, limit, contributions), status
        except Exception as e:
            logger.error("Hybrid search failed: %s", e)
            fallback = await self.semantic_search(query, top_k=limit, filters=semantic_filters, mode="vector")
            # Shape parity: the fused path always attaches these two keys, so a caller
            # reading them unconditionally would raise KeyError only on the degraded
            # path -- the failure mode hardest to notice. They are empty rather than
            # invented: no fusion ran, so no view agreement was measured. The
            # discriminator is ``fused``, not a zero count.
            for result in fallback:
                result.setdefault("view_contributions", {})
                result.setdefault("view_count", 0)
            return fallback, {"fused": False, "error": str(e), "views": classified_views}

    async def search(
        self,
        query: str,
        limit: int,
        category: str | None = None,
        board_filter: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining semantic and keyword results.

        Issue #281 refactor: Uses RRF with k=60 for fusion.
        Issue #3242: board_filter is threaded into the semantic ``where`` clause.
        Issue #17207: delegates to ``search_with_provenance``; each result carries
        ``view_contributions`` and ``view_count``. On the degraded fallback path those
        are ``{}`` and ``0`` because no fusion ran -- an empty map here means "not
        fused", not "no view agreed". This return value cannot express the difference;
        use ``search_with_provenance`` and read ``fused`` when it matters.

        Args:
            query: Search query
            limit: Maximum results to return
            category: Optional category filter
            board_filter: Optional ChromaDB metadata filter for board scoping

        Returns:
            Combined and ranked search results
        """
        results, _status = await self.search_with_provenance(query, limit, category, board_filter)
        return results
