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

    def _retrieve_documentation_context(self, query: str, n_results: int = 3, score_threshold: float = 0.3) -> str:
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

    def _retrieve_raw_doc_results(
        self, query: str, n_results: int = 3, score_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Return raw doc-search results without pre-formatting (#10658).

        Used by ``conversation_aware_retrieve`` to build [Source N] labels that
        continue from the KB citation count, keeping citation indices contiguous.
        """
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
        score_threshold: float = 0.3,
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
