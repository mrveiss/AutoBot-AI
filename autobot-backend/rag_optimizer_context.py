# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Optimized-context assembly for ``AdvancedRAGOptimizer`` (#620, #18944).

Split out of ``advanced_rag_optimizer.py`` to keep it under its file-size ceiling; a move plus the
required ``principal`` (#18944), not a second retrieval path. Assumes the composing class provides
``advanced_search``, ``kb`` and ``_analyze_query_context``.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, List, Tuple

from autobot_shared.logging_manager import get_llm_logger
from knowledge.search_filters import KbPrincipal, require_kb_principal

if TYPE_CHECKING:  # runtime import would be circular: advanced_rag_optimizer imports this module
    from advanced_rag_optimizer import QueryContext, RAGMetrics, RankedResult

logger = get_llm_logger("advanced_rag_optimizer")

#: Results assembled into one optimized context.
CONTEXT_MAX_RESULTS = 8


class OptimizedContextMixin:
    """Context-assembly methods mixed into ``AdvancedRAGOptimizer``."""

    def _build_context_parts(
        self,
        results: List[RankedResult],
        max_context_length: int,
        query_context: QueryContext,
    ) -> List[str]:
        """Build context parts from search results with length optimization.

        Args:
            results: Search results to build context from.
            max_context_length: Maximum total context length.
            query_context: Query context for complexity-based decisions.

        Returns:
            List of formatted context entries.

        Issue #620.
        """
        context_parts = []
        current_length = 0

        for i, result in enumerate(results):
            source_info = f"Source: {result.source_path}"
            if result.chunk_index > 0:
                source_info += f" (section {result.chunk_index + 1})"

            context_entry = f"{source_info}\nContent: {result.content}\n"
            entry_length = len(context_entry)

            if current_length + entry_length > max_context_length and context_parts:
                break

            context_parts.append(context_entry)
            current_length += entry_length

            if i >= 2 and query_context.complexity_score < 0.6:
                break

        return context_parts

    def _build_context_header(self, query: str, context_parts: List[str], query_context: QueryContext) -> str:
        """Build the header for optimized context output.

        Args:
            query: Original query string.
            context_parts: List of context entries.
            query_context: Query context with type information.

        Returns:
            Formatted header string.

        Issue #620.
        """
        header = f"Relevant Information for: {query}\n"
        header += f"Sources: {len(context_parts)} documents\n"
        header += f"Query type: {query_context.query_type}\n\n"
        return header

    async def search_visible(
        self, query: str, max_results: int, principal: KbPrincipal
    ) -> Tuple[List[RankedResult], RAGMetrics]:
        """``advanced_search`` keeping only what *principal* may read, via ``filter_ranked`` (#18944).

        The counts in the returned metrics are taken over the kept list: ``advanced_search`` counts
        before filtering, so passing them on would tell the caller how many facts others hold. The
        metrics object is copied first, because ``query_cache`` hands every reader the same instance.
        """
        from services.rag_visibility import VISIBILITY_OVERFETCH, filter_ranked  # lazy: it imports this module

        results, metrics = await self.advanced_search(query, max_results=max_results * VISIBILITY_OVERFETCH)
        kept = await filter_ranked(results, principal, getattr(self.kb, "ownership_manager", None))
        kept = kept[:max_results]
        visible = dataclasses.replace(metrics, documents_considered=len(kept), final_results_count=len(kept))
        return kept, visible

    async def _render_context(self, query: str, results: List[RankedResult], max_context_length: int) -> str:
        """Format *results* into one context string and pass it through the content firewall."""
        query_context = self._analyze_query_context(query)
        context_parts = self._build_context_parts(results, max_context_length, query_context)
        header = self._build_context_header(query, context_parts, query_context)
        final_context = header + "\n---\n".join(context_parts)

        # #10552, #16771: the one shared RAG inspection point
        from security.content_firewall import inspect_rag_context

        fw_verdict = await inspect_rag_context(final_context, context_label=query[:80])
        if fw_verdict.blocked:
            return "[RAG context blocked by content firewall]"
        logger.info(
            "Optimized context generated: %s characters from %s sources", len(fw_verdict.content), len(context_parts)
        )
        return fw_verdict.content

    async def get_optimized_context(
        self, query: str, max_context_length: int = 2000, *, principal: KbPrincipal
    ) -> Tuple[str, RAGMetrics]:
        """Get optimized context for RAG-based response generation.

        #18944: ``principal`` is required; only results it may read reach the context. ``query_cache``
        holds unfiltered results, so every reader filters after the cache read, never before it.
        """
        principal = require_kb_principal(principal)  # before any read
        try:
            results, metrics = await self.search_visible(query, CONTEXT_MAX_RESULTS, principal)
            if not results:
                return "No relevant information found.", metrics
            return await self._render_context(query, results, max_context_length), metrics
        except Exception as e:
            logger.error("Context optimization failed: %s", e)
            from advanced_rag_optimizer import RAGMetrics

            return "Error retrieving context", RAGMetrics()
