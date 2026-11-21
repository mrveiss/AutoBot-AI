# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ChatKnowledgeService's AutoBot-documentation search methods.

Issue #250: indexed-documentation search (the autobot_docs ChromaDB
collection), kept on the same ChatKnowledgeService class as the RAG
(autobot_memory) path via mixin composition, so call sites keep calling
``self.retrieve_documentation(...)`` unchanged. Extracted from service.py
(#16930 review split, to keep it under its file-size ceiling) -- a move, not
a behaviour change.
"""

import time
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_llm_logger
from constants.rag_graph_constants import RAG_SCORE_THRESHOLD
from knowledge.search_filters import KbPrincipal, filter_for_principal, require_kb_principal

from .doc_searcher import DocumentationSearcher

logger = get_llm_logger("chat_knowledge_service")


class DocumentationRetrievalMixin:
    """Documentation-search methods mixed into ChatKnowledgeService.

    Assumes the composing class sets ``self.doc_searcher`` (a
    DocumentationSearcher instance, or None when doc search is disabled)
    before any of these methods are called -- see
    ChatKnowledgeService.__init__.
    """

    doc_searcher: DocumentationSearcher | None

    def _retrieve_documentation_context(
        self, query: str, n_results: int = 3, score_threshold: float = RAG_SCORE_THRESHOLD
    ) -> str:
        """Retrieve documentation context if query matches doc patterns.

        Issue #1261: Searches autobot_docs ChromaDB collection to provide
        real AutoBot documentation context instead of relying on LLM
        training data.

        Args:
            query: User's chat message
            n_results: Max documentation chunks to retrieve
            score_threshold: Minimum similarity score

        Returns:
            Formatted documentation context string, or empty string
        """
        if not self.doc_searcher:
            return ""

        try:
            if not self.doc_searcher.is_documentation_query(query):
                return ""

            results = self.doc_searcher.search(
                query=query,
                n_results=n_results,
                score_threshold=score_threshold,
            )
            if not results:
                return ""

            context = self.doc_searcher.format_as_context(results)
            logger.info(
                "[Doc Search] Added %d documentation chunks for: '%s...'",
                len(results),
                query[:50],
            )
            return context

        except Exception as e:
            logger.warning("[Doc Search] Failed: %s", e)
            return ""

    async def _retrieve_raw_doc_results(
        self, query: str, n_results: int = 3, score_threshold: float = RAG_SCORE_THRESHOLD, *, principal: KbPrincipal
    ) -> List[Dict[str, Any]]:
        """Return raw doc-search results without pre-formatting (#10658).

        Issue #18944: only the chunks *principal* may read, through ``filter_for_principal``. Doc chunks
        carry the platform-docs grant, so any signed-in user keeps them. Needs ``self.rag_service``.

        Used by ``conversation_aware_retrieve`` to build [Source N] labels that
        continue from the KB citation count, keeping citation indices contiguous.
        """
        principal = require_kb_principal(principal)
        if not self.doc_searcher:
            return []
        try:
            if not self.doc_searcher.is_documentation_query(query):
                return []
            results = self.doc_searcher.search(
                query=query,
                n_results=n_results,
                score_threshold=score_threshold,
            )
            results = await filter_for_principal(results, principal, self.rag_service._ownership_manager())
            if results:
                logger.info(
                    "[Doc Search] Retrieved %d raw documentation chunks for: '%s...'",
                    len(results),
                    query[:50],
                )
            return results
        except Exception as e:
            logger.warning("[Doc Search] Raw retrieval failed: %s", e)
            return []

    @staticmethod
    def _label_doc_sources(doc_results: List[Dict[str, Any]], citations: List[Dict]) -> str:
        """Label raw doc chunks ``[Source N]``, continuing the KB numbering; append their citations.

        Issue #1261, #10658: the citation indices stay contiguous so the frontend can resolve
        them. Returns the "AUTOBOT DOCUMENTATION CONTEXT" block. A move out of
        ``conversation_aware_retrieve`` (to keep service.py under its ceiling), not a behaviour change.
        """
        kb_count = len(citations)
        doc_lines: List[str] = []
        for offset, result in enumerate(doc_results, 1):
            source_n = kb_count + offset
            content = result.get("content", "").strip()
            doc_lines.append(f"[Source {source_n}] {content}")
            citations.append(
                {
                    "id": f"doc_{offset}",
                    "content": content,
                    "score": result.get("score", 0.0),
                    "source": result.get("file_path", ""),
                    "title": result.get("section", ""),
                    "rank": source_n,
                    "metadata": {
                        "doc_type": result.get("doc_type", "documentation"),
                        "section": result.get("section", ""),
                        "subsection": result.get("subsection", ""),
                    },
                }
            )
        return "AUTOBOT DOCUMENTATION CONTEXT:\n" + "\n".join(doc_lines)

    def _search_and_format_documentation(
        self,
        query: str,
        n_results: int,
        score_threshold: float,
        start_time: float,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Search documentation and format results as context.

        Issue #620.
        """
        results = self.doc_searcher.search(
            query=query,
            n_results=n_results,
            score_threshold=score_threshold,
        )

        if not results:
            logger.debug("[Doc Search] No results for: '%s...'", query[:50])
            return "", []

        context = self.doc_searcher.format_as_context(results)
        retrieval_time = time.time() - start_time
        logger.info(
            "[Doc Search] Found %d documentation chunks in %.3fs for: '%s...'",
            len(results),
            retrieval_time,
            query[:50],
        )
        return context, results

    async def retrieve_documentation(
        self,
        query: str,
        n_results: int = 3,
        score_threshold: float = RAG_SCORE_THRESHOLD,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Retrieve relevant AutoBot documentation for a query.

        Issue #250: Searches indexed documentation to provide context about
        AutoBot deployment, APIs, architecture, and troubleshooting.

        Args:
            query: User's chat message/query
            n_results: Maximum number of documentation chunks to retrieve
            score_threshold: Minimum relevance score (0.0-1.0) to include

        Returns:
            Tuple of (formatted_context_string, documentation_results)
            - formatted_context_string: Documentation context for LLM prompt
            - documentation_results: List of result dicts with content and metadata
        """
        if not self.doc_searcher:
            return "", []

        try:
            start_time = time.time()

            if not self.doc_searcher.is_documentation_query(query):
                logger.debug("[Doc Search] Query not documentation-related: '%s...'", query[:50])
                return "", []

            return self._search_and_format_documentation(query, n_results, score_threshold, start_time)

        except Exception as e:
            logger.error("Documentation retrieval failed: %s", e)
            return "", []
