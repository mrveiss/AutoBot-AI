# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one MMR pass over `RankedResult` lists (#18141, #10600).

The advanced RAG optimizer and the neural-mesh path both diversify reranked results. They share
this function, so the same `mmr_lambda` produces the same ordering whichever retriever ran.
"""

from __future__ import annotations

from typing import Any, List

from knowledge.search_components.reranking import apply_mmr_reorder_by_content


def diversify_ranked_results(results: List[Any], mmr_lambda: float) -> List[Any]:
    """MMR-reorder ranked results by content redundancy; a no-op when ``mmr_lambda`` is 0.

    ``RankedResult`` carries no embedding, so redundancy is measured on ``content``. The
    relevance term is ``rerank_score``.
    """
    if mmr_lambda <= 0.0:
        return results
    return apply_mmr_reorder_by_content(
        results,
        mmr_lambda,
        content_getter=lambda r: r.content,
        score_getter=lambda r: r.rerank_score or 0.0,
    )
