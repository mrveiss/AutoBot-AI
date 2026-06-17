#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
CAG Service — Context-Augmented Generation.

Loads full source documents (ranked by RAGService.advanced_search) into the
context window when the combined token count fits the model's adaptive budget.
Falls back to RAGService.get_optimized_context when documents don't fit or
when no source paths can be resolved.

Issue #9018 Phase 1.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, List, Tuple

from autobot_shared.logging_manager import get_llm_logger

if TYPE_CHECKING:
    from advanced_rag_optimizer import RAGMetrics
    from services.rag_service import RAGService

logger = get_llm_logger("cag_service")

# Reserve this many tokens for the model's output when computing the CAG budget.
# Overridden by RAGConfig.cag_output_headroom_tokens at runtime.
_DEFAULT_OUTPUT_HEADROOM = 2048

# Maximum number of full documents to load in a single CAG pass.
# Overridden by RAGConfig.cag_max_documents at runtime.
_DEFAULT_MAX_DOCUMENTS = 10


@dataclass
class _CandidateDoc:
    """Internal representation of a ranked candidate document."""

    source_path: str
    chunks: List[str] = field(default_factory=list)
    rank: int = 0


def _unique_source_paths(results: list) -> List[_CandidateDoc]:
    """Map ranked SearchResult list → deduplicated CandidateDoc list (rank-ordered)."""
    seen: dict[str, _CandidateDoc] = {}
    for result in results:
        sp = result.source_path or ""
        if not sp or sp in ("unknown", "topic_cache", "semantic_cache"):
            continue
        if sp not in seen:
            seen[sp] = _CandidateDoc(source_path=sp, rank=len(seen))
        seen[sp].chunks.append(result.content)
    return list(seen.values())


async def _read_source_file(source_path: str) -> str | None:
    """Read a source file asynchronously. Returns None when unreadable."""
    import asyncio
    from pathlib import Path

    path = Path(source_path)
    try:
        if not await asyncio.to_thread(path.exists):
            return None
        return await asyncio.to_thread(path.read_text, encoding="utf-8")
    except Exception as exc:
        logger.debug("CAG: cannot read %s — %s", source_path, exc)
        return None


def _assemble_context(docs: List[tuple[str, str]]) -> str:
    """Format (source_path, content) pairs into a CAG context block."""
    parts: List[str] = []
    for source_path, content in docs:
        header = f"=== Source: {source_path} ==="
        parts.append(f"{header}\n{content.strip()}")
    return "\n\n".join(parts)


class CAGService:
    """Context-Augmented Generation: loads full documents within the token budget.

    Depends on RAGService for candidate ranking; never re-implements search.
    """

    def __init__(self, rag_service: "RAGService") -> None:
        self._rag = rag_service

    def _budget(self, model: str | None, config: Any) -> int:
        """Return effective token budget for CAG assembly."""
        from context_window_manager import ContextWindowManager

        cwm = ContextWindowManager()
        adaptive = cwm.get_adaptive_context_length(model)
        headroom = getattr(config, "cag_output_headroom_tokens", _DEFAULT_OUTPUT_HEADROOM)
        budget = adaptive - headroom
        if adaptive <= 4096:
            logger.warning(
                "CAG: model %r resolved to default 4 096-token window — " "budget source may be the fallback value",
                model,
            )
        return max(budget, 0)

    async def get_full_context(
        self,
        query: str,
        collection: str | None = None,
        model: str | None = None,
    ) -> "Tuple[str, RAGMetrics]":
        """Return (context, metrics) with strategy='cag' or fall back to RAG.

        Steps:
        1. Rank candidates via RAGService.advanced_search.
        2. Map chunks → unique source documents by source_path.
        3. Read full files; keep top-N that fit within the token budget.
        4. If any docs fit, assemble CAG context and emit metrics.
        5. Otherwise fall back to RAGService.get_optimized_context.
        """
        from context_window_manager import ContextWindowManager

        config = self._rag.config
        t_start = time.monotonic()

        results, search_metrics = await self._rag.advanced_search(query=query)
        candidates = _unique_source_paths(results)

        if not candidates:
            logger.debug("CAG: no source paths in results — falling back to RAG")
            return await self._fallback(query, search_metrics)

        budget = self._budget(model, config)
        cwm = ContextWindowManager()
        max_docs = getattr(config, "cag_max_documents", _DEFAULT_MAX_DOCUMENTS)

        loaded: List[tuple[str, str]] = []
        tokens_used = 0

        for doc in candidates[:max_docs]:
            content = await _read_source_file(doc.source_path)
            if content is None:
                logger.debug("CAG: %s unreadable — skipping", doc.source_path)
                continue
            doc_tokens = cwm.estimate_tokens(content)
            if tokens_used + doc_tokens > budget:
                logger.debug(
                    "CAG: %s (%d tok) would exceed budget %d — stopping",
                    doc.source_path,
                    doc_tokens,
                    budget,
                )
                break
            loaded.append((doc.source_path, content))
            tokens_used += doc_tokens

        if not loaded:
            logger.info("CAG: no documents fit within budget %d — falling back to RAG", budget)
            return await self._fallback(query, search_metrics)

        context = _assemble_context(loaded)
        elapsed = time.monotonic() - t_start

        from advanced_rag_optimizer import RAGMetrics

        metrics = RAGMetrics(
            query_processing_time=search_metrics.query_processing_time,
            retrieval_time=elapsed,
            reranking_time=search_metrics.reranking_time,
            total_time=elapsed,
            documents_considered=len(candidates),
            final_results_count=len(loaded),
            hybrid_search_enabled=search_metrics.hybrid_search_enabled,
        )
        # Strategy + CAG observability — declared fields on RAGMetrics (#9018).
        metrics.strategy = "cag"
        metrics.documents_loaded = len(loaded)
        metrics.tokens_used = tokens_used
        metrics.budget = budget

        logger.info(
            "CAG assembled %d document(s) (%d tokens, budget %d) for query %r",
            len(loaded),
            tokens_used,
            budget,
            query,
        )
        return context, metrics

    async def _fallback(self, query: str, prior_metrics: "RAGMetrics") -> "Tuple[str, RAGMetrics]":
        """Delegate to RAGService.get_optimized_context and tag metrics."""
        context, metrics = await self._rag.get_optimized_context(query=query)
        metrics.strategy = "rag"
        logger.debug("CAG fell back to RAG for query %r", query)
        return context, metrics
