# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Basic vector-search path for :class:`knowledge.search.SearchMixin` (#12771).

Extracted so the dispatcher in ``search.py`` stays within the function-length
limit (#620).  The path delegates to VectorSearchEngine and falls back to a
direct ChromaDB query.  Issue #398, #934, #3828.
"""

from __future__ import annotations

from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from knowledge.vector_search_engine import VectorSearchResult, get_vector_search_engine

logger = get_logger(__name__)


class BasicVectorSearchMixin:
    """The unfiltered, unranked vector-search path of the knowledge base."""

    async def _search_basic(
        self,
        query: str,
        top_k: int,
        similarity_top_k: int | None,
        filters: Dict[str, Any] | None,
    ) -> List[Dict[str, Any]]:
        """Run the basic vector search, falling back to direct ChromaDB on error."""
        self.ensure_initialized()
        similarity_top_k = similarity_top_k or top_k

        invalid_result = self._validate_search_inputs(query)
        if invalid_result is not None:
            return invalid_result

        # Issue #5064: sanitize query before embedding to block prompt injection.
        sanitized = self._sanitize_search_query(query)
        if sanitized is None:
            return []
        query = sanitized

        try:
            engine = await get_vector_search_engine()
            engine_results: List[VectorSearchResult] = await engine.search(
                query=query,
                top_k=similarity_top_k,
                filters=filters,
                hardware_backend="auto",
            )
            # Convert canonical VectorSearchResult -> legacy dict format expected by callers
            results = [
                {
                    "content": r.text,
                    "score": r.score,
                    "metadata": r.metadata,
                    "node_id": r.source,
                    "doc_id": r.source,  # V1 compatibility
                }
                for r in engine_results
            ]
            # A1 (#12552): reinforce facts surfaced by a real query. Fire-and-forget;
            # never blocks or alters the returned results.
            try:
                await self.record_fact_access([r.source for r in engine_results if r.source])
            except Exception:
                logger.debug("search: record_fact_access skipped", exc_info=True)
            return results
        except Exception as exc:
            logger.warning(
                "VectorSearchEngine delegation failed (%s), falling back to direct ChromaDB",
                exc,
            )

        # Fallback: original direct ChromaDB path
        try:
            return await self._execute_vector_search(query, similarity_top_k, filters=filters)
        except Exception as e:
            logger.error("Knowledge base search failed: %s", e)
            return []
