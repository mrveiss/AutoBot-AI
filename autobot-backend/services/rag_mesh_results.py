# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Normalise Neural Mesh retriever output to ``RankedResult`` so every RAG branch shares one shape (#18141).

The mesh reranker returns plain dicts while the vector branch returns ``RankedResult``;
the stale-chunk filter and the feedback emitters read ``RankedResult`` attributes.
"""

from typing import Any

from advanced_rag_optimizer import RankedResult
from knowledge.chunk_identity import resolve_chunk_id


def _from_dict(index: int, chunk: dict[str, Any]) -> RankedResult:
    """Build a ``RankedResult`` from a reranker result dict."""
    score = float(chunk.get("score", 0.0) or 0.0)
    metadata = dict(chunk.get("metadata") or {})
    chunk_id = resolve_chunk_id(chunk)
    metadata.setdefault("chunk_id", chunk_id)
    return RankedResult(
        content=chunk.get("content", ""),
        metadata=metadata,
        semantic_score=score,
        keyword_score=0.0,
        hybrid_score=float(chunk.get("original_score", score) or 0.0),
        relevance_rank=index + 1,
        source_path=chunk.get("source_path") or chunk_id,
        rerank_score=chunk.get("rerank_score"),
    )


def coerce_ranked_results(chunks: list) -> list[RankedResult]:
    """Return ``chunks`` as ``RankedResult`` objects, converting reranker dicts."""
    return [_from_dict(i, c) if isinstance(c, dict) else c for i, c in enumerate(chunks)]
