# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared content-firewall inspection for RAG results (#16771).

Split out of ``advanced_rag_optimizer.py``, which sits at its #14236 ceiling:
a new inspection pass is added lines, and a grandfathered file may not grow --
the same reason ``api/code_sync_paths.py`` (#16713) moved out of
``api/code_sync.py`` before it.

Also used by ``services/knowledge/service.py``'s ``doc_searcher`` path -- a
second, separate retrieval source from ``AdvancedRAGOptimizer.advanced_search()``,
not covered by that function's own pass -- so this lives here rather than as a
private method either file would otherwise have to duplicate.

Retrieved KB/doc text is untrusted: it can carry an injection payload stored
before the ingestion guard existed, or through an unguarded write route. A
blocked result is dropped entirely -- its citation goes with it. A surviving
result's clean text (for citations/UI) is never mutated; the firewall's
delimited, model-facing text is carried separately, for a prompt builder to
read instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from autobot_shared.logging_manager import get_llm_logger

if TYPE_CHECKING:
    from advanced_rag_optimizer import SearchResult

logger = get_llm_logger("rag_content_firewall")


async def firewall_filter_search_results(results: "List[SearchResult]", query: str) -> "List[SearchResult]":
    """Inspect each ``SearchResult.content``; drop a blocked one, delimit the rest.

    Sets ``firewall_safe_content``/``firewall_action``/``firewall_risk`` on
    every surviving result. ``content`` itself is left unchanged, so citations
    and any other UI-facing read of it stay clean.
    """
    from security.content_firewall import ContentSource, get_content_firewall

    firewall = get_content_firewall()
    safe_results = []
    for result in results:
        verdict = await firewall.inspect(result.content, source=ContentSource.RAG, context_label=query[:80])
        if verdict.blocked:
            logger.warning(
                "RAG result dropped by content firewall (risk=%s, source=%s)",
                verdict.risk.value,
                result.source_path,
            )
            continue
        result.firewall_safe_content = verdict.content
        result.firewall_action = verdict.action.value
        result.firewall_risk = verdict.risk.value
        safe_results.append(result)
    return safe_results


async def firewall_filter_doc_results(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """Inspect each raw doc-search result dict's ``"content"``; drop a blocked one.

    A surviving dict gains a ``"firewall_safe_content"`` key set to the
    firewall's delimited, model-facing text; its own ``"content"`` key is
    left unchanged, so a citation built from it stays clean.
    """
    from security.content_firewall import ContentSource, get_content_firewall

    firewall = get_content_firewall()
    safe_results = []
    for result in results:
        verdict = await firewall.inspect(result.get("content", ""), source=ContentSource.RAG, context_label=query[:80])
        if verdict.blocked:
            logger.warning(
                "Doc-search result dropped by content firewall (risk=%s, source=%s)",
                verdict.risk.value,
                result.get("file_path", ""),
            )
            continue
        safe_results.append({**result, "firewall_safe_content": verdict.content})
    return safe_results
