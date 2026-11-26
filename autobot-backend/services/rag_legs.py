# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
RAGService retrieval legs (#21606): the timed optimizer search, the category cut, the docs merge
and the basic-search fallback, split out of ``rag_service`` along the mixin pattern of
``rag_cache_tiers``. Behaviour is unchanged by the split.
"""

import asyncio
import time
from typing import List, Set, Tuple

from advanced_rag_optimizer import RAGMetrics, RankedResult
from autobot_shared.logging_manager import get_llm_logger
from knowledge.search_filters import KbPrincipal
from knowledge.stale_filter import drop_stale
from services.rag_visibility import VISIBILITY_OVERFETCH, filter_ranked

logger = get_llm_logger("rag_service")


class RAGLegsMixin:
    """The retrieval legs of ``RAGService``; relies on its ``config``, ``optimizer`` and ``kb_adapter``."""

    async def _execute_search_with_timeout(
        self,
        query: str,
        fetch_limit: int,
        enable_reranking: bool,
        timeout_seconds: float,
        principal: KbPrincipal,
    ) -> Tuple[List[RankedResult], RAGMetrics]:
        """Execute search with timeout protection and keep what *principal* may read.

        Issue #665: extracted helper. Issue #16664: the optimizer's results are filtered here,
        before anything caches, cuts or merges them.
        Issue #4696: when enable_rlm_refinement is True, delegates to
        advanced_search_with_refinement() for RLM-driven query refinement.
        The extra refinement_history is logged at debug level and discarded.
        """
        reranking = enable_reranking and self.config.enable_reranking
        if self.config.enable_rlm_refinement:
            results, metrics, history = await asyncio.wait_for(
                self.optimizer.advanced_search_with_refinement(
                    query=query,
                    max_results=fetch_limit,
                    enable_reranking=reranking,
                ),
                timeout=timeout_seconds,
            )
            if history:
                logger.debug("RLM refinement completed: %d iteration(s) for query %r", len(history), query)
        else:
            results, metrics = await asyncio.wait_for(
                self.optimizer.advanced_search(query=query, max_results=fetch_limit, enable_reranking=reranking),
                timeout=timeout_seconds,
            )
        return await filter_ranked(results, principal, self._ownership_manager()), metrics

    def _apply_category_filter(
        self,
        results: List[RankedResult],
        metrics: RAGMetrics,
        categories: List[str] | None,
        max_results: int,
    ) -> List[RankedResult]:
        """Category-filter already-visible *results* and cut them to *max_results*. Ref: #1088."""
        if categories:
            filtered = self._filter_by_categories(results, categories)
            if filtered or not results:
                logger.info("Category filter applied: %s, results: %d/%d", categories, len(filtered), len(results))
                results = filtered
            else:
                logger.warning(
                    "Category filter %s eliminated all %d results — returning unfiltered results instead",
                    categories,
                    len(results),
                )
        results = results[:max_results]
        metrics.final_results_count = len(results)
        return results

    async def _execute_and_cache_search(
        self,
        query: str,
        max_results: int,
        enable_reranking: bool,
        timeout_seconds: float,
        categories: List[str] | None,
        cache_key: str,
        principal: KbPrincipal,
    ) -> Tuple[List[RankedResult], RAGMetrics]:
        """Helper for advanced_search. Ref: #1088.

        Executes timed search, keeps what *principal* may read, applies the category filter,
        caches the filtered result and handles timeout/exception fallback according to config.
        """
        fetch_limit = max_results * VISIBILITY_OVERFETCH * (2 if categories else 1)
        try:
            results, metrics = await self._execute_search_with_timeout(
                query, fetch_limit, enable_reranking, timeout_seconds, principal
            )
            results = self._apply_category_filter(results, metrics, categories, max_results)
            if cache_key:
                await self._add_to_cache(cache_key, (results, metrics))
            logger.info(f"Advanced search completed: {len(results)} results in {metrics.total_time:.3f}s")
            return results, metrics
        except asyncio.TimeoutError:
            logger.error(f"Advanced search timed out after {timeout_seconds}s, using fallback")
            if self.config.fallback_to_basic_search:
                return await self._fallback_basic_search(query, max_results, principal=principal)
            raise
        except Exception as e:
            logger.error("Advanced search failed: %s", e)
            if self.config.fallback_to_basic_search:
                return await self._fallback_basic_search(query, max_results, principal=principal)
            raise

    async def _filter_stale_chunks(self, results: List[RankedResult]) -> List[RankedResult]:
        """*results* through the shared stale filter, ``knowledge.stale_filter.drop_stale`` (#4689, #19280)."""
        return await drop_stale(results)

    def _filter_by_categories(
        self,
        results: List[RankedResult],
        categories: List[str],
    ) -> List[RankedResult]:
        """
        Filter search results by category.

        Issue #556: Category-based filtering for chat RAG.

        Args:
            results: List of search results to filter
            categories: List of category names to include

        Returns:
            Filtered list of results matching any of the specified categories
        """
        if not categories:
            return results

        categories_set: Set[str] = set(categories)
        filtered = []

        for result in results:
            # Check category in metadata
            result_category = result.metadata.get("category", "")

            # Also check category_id or category_path
            if not result_category:
                result_category = result.metadata.get("category_id", "")
            if not result_category:
                result_category = result.metadata.get("category_path", "")

            # Match against categories (exact match or path prefix)
            if result_category:
                # Handle hierarchical categories (e.g., "system_knowledge/commands")
                category_parts = result_category.split("/")
                if any(part in categories_set for part in category_parts):
                    filtered.append(result)
                elif result_category in categories_set:
                    filtered.append(result)
            else:
                # If no category metadata, include by default (uncategorized)
                # This can be changed to exclude if strict category filtering is needed
                filtered.append(result)

        if not filtered and results:
            actual_categories = {r.metadata.get("category", "<none>") for r in results}
            logger.debug(
                "Category filter: 0/%d matched %s — actual categories: %s",
                len(results),
                categories,
                actual_categories,
            )
        else:
            logger.debug(
                "Category filter: %d/%d results matched categories %s",
                len(filtered),
                len(results),
                categories,
            )
        return filtered

    async def _fallback_basic_search(
        self,
        query: str,
        max_results: int,
        categories: List[str] | None = None,
        *,
        principal: KbPrincipal,
    ) -> Tuple[List[RankedResult], RAGMetrics]:
        """
        Fallback to basic search when advanced RAG fails.

        Issue #556: Added categories parameter for filtering.
        Issue #16664: keeps only what *principal* may read.

        Args:
            query: Search query
            max_results: Maximum results to return
            categories: Optional list of categories to filter
            principal: Who is asking, or SYSTEM_SCOPE

        Returns:
            Tuple of (basic_results, empty_metrics)
        """
        logger.info("Using basic search fallback")
        metrics = RAGMetrics()

        try:
            start_time = time.time()

            # Fetch more: the visibility filter (and a category filter) can only remove results
            fetch_limit = max_results * VISIBILITY_OVERFETCH * (2 if categories else 1)

            # Use knowledge base adapter for consistent interface
            basic_results = await self.kb_adapter.search(query=query, top_k=fetch_limit)

            # Convert to RankedResult objects
            search_results = []
            for i, result in enumerate(basic_results):
                sr = RankedResult(
                    content=result.get("content", result.get("text", "")),
                    metadata=result.get("metadata", {}),
                    semantic_score=result.get("score", 0.0),
                    keyword_score=0.0,
                    hybrid_score=result.get("score", 0.0),
                    relevance_rank=i + 1,
                    source_path=result.get("metadata", {}).get("source", "unknown"),
                )
                search_results.append(sr)

            # #16664: visibility first, so the category cut and top-k are taken over readable results
            search_results = await filter_ranked(search_results, principal, self._ownership_manager())
            if categories:
                search_results = self._filter_by_categories(search_results, categories)
            search_results = search_results[:max_results]

            # Issue #4721: filter stale chunks on the fallback path too.
            search_results = await self._filter_stale_chunks(search_results)

            metrics.total_time = time.time() - start_time
            metrics.final_results_count = len(search_results)

            return search_results, metrics

        except Exception as e:
            logger.error("Basic search fallback failed: %s", e)
            return [], metrics

    async def _merge_docs_leg(
        self,
        query: str,
        results: List[RankedResult],
        categories: List[str] | None,
        max_results: int,
        principal: KbPrincipal,
    ) -> List[RankedResult]:
        """Merge ``autobot_docs`` hits into *results* by hybrid score (Issue #4953).

        Runs when a category is requested or no category filter is active (search-all); a failing
        docs index is skipped, never fatal.
        """
        if categories is not None and "autobot_docs" not in categories:
            return results
        try:
            from services.knowledge.doc_indexer import get_doc_indexer_service

            doc_svc = get_doc_indexer_service()
            if not doc_svc._initialized:
                return results
            doc_results = await doc_svc.search(query, n_results=max_results * VISIBILITY_OVERFETCH)
            # #16664: the docs carry the platform grant, so this keeps them for any signed-in user
            doc_results = await filter_ranked(doc_results, principal, self._ownership_manager())
            if not doc_results:
                return results
            combined = results + doc_results
            combined.sort(key=lambda r: r.hybrid_score, reverse=True)
            logger.debug("autobot_docs merged %d result(s) into search", len(doc_results))
            return combined[:max_results]
        except Exception as _doc_exc:
            logger.debug("autobot_docs search skipped: %s", _doc_exc)
            return results
