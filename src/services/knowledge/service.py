# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat Knowledge Service

Issue #381: Extracted from chat_knowledge_service.py god class refactoring.
Contains the main ChatKnowledgeService class that coordinates knowledge retrieval.
"""

import time
from typing import Any, Dict, List, Optional, Tuple

from backend.services.rag_service import RAGService
from src.advanced_rag_optimizer import SearchResult
from src.utils.logging_manager import get_llm_logger

from .context_enhancer import get_context_enhancer
from .doc_searcher import DocumentationSearcher, get_documentation_searcher
from .intent_detector import get_query_intent_detector
from .types import EnhancedQuery, QueryIntentResult, QueryKnowledgeIntent

# Issue #556: Standard knowledge categories for chat RAG
KNOWLEDGE_CATEGORIES = {
    "system_knowledge": "OS commands, man pages, system configurations",
    "user_knowledge": "User-specific facts, preferences, learned behaviors",
    "autobot_knowledge": "AutoBot documentation, capabilities, how-to guides",
}

logger = get_llm_logger("chat_knowledge_service")


class ChatKnowledgeService:
    """
    Service for retrieving and formatting knowledge for chat interactions.

    This service acts as a bridge between the chat workflow and the RAG system,
    providing knowledge retrieval with appropriate filtering and formatting.

    Issue #249 Phase 2: Now includes smart intent detection to optimize
    when to use knowledge retrieval.

    Issue #250: Added documentation search integration for AutoBot self-awareness.
    """

    # Issue #620: Extracted keyword sets from _select_categories_for_intent
    AUTOBOT_KEYWORDS = frozenset(
        {
            "autobot",
            "how do i use",
            "how to use autobot",
            "what can you do",
            "help me with autobot",
            "autobot feature",
            "this tool",
            "your capability",
            "your feature",
        }
    )

    SYSTEM_KEYWORDS = frozenset(
        {
            "command",
            "terminal",
            "bash",
            "shell",
            "linux",
            "install",
            "configure",
            "config",
            "setup",
            "man page",
            "syntax",
            "chmod",
            "chown",
            "grep",
            "awk",
            "sed",
            "systemctl",
            "docker",
            "kubernetes",
            "service",
            "daemon",
            "process",
        }
    )

    USER_KEYWORDS = frozenset(
        {
            "my preference",
            "i like",
            "i prefer",
            "remember that",
            "last time",
            "as i mentioned",
            "my settings",
        }
    )

    def __init__(self, rag_service: RAGService, enable_doc_search: bool = True):
        """
        Initialize chat knowledge service.

        Args:
            rag_service: Configured RAGService instance
            enable_doc_search: Enable documentation search integration (Issue #250)
        """
        self.rag_service = rag_service
        self.intent_detector = get_query_intent_detector()
        self.context_enhancer = get_context_enhancer()

        # Issue #250: Documentation search integration
        self.doc_searcher: Optional[DocumentationSearcher] = None
        if enable_doc_search:
            self.doc_searcher = get_documentation_searcher()
            self.doc_searcher.initialize()

        logger.info(
            "ChatKnowledgeService initialized with intent detection, "
            "conversation-aware RAG, doc_search=%s",
            enable_doc_search,
        )

    async def retrieve_relevant_knowledge(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.7,
        categories: Optional[List[str]] = None,
    ) -> Tuple[str, List[Dict]]:
        """
        Retrieve relevant knowledge facts for a chat query.

        Issue #556: Added categories parameter for category-based filtering.

        Args:
            query: User's chat message/query
            top_k: Maximum number of knowledge facts to retrieve
            score_threshold: Minimum relevance score (0.0-1.0) to include
            categories: Optional list of categories to filter results
                       (e.g., ["system_knowledge", "user_knowledge", "autobot_knowledge"])

        Returns:
            Tuple of (formatted_context_string, citation_list)
            - formatted_context_string: Knowledge context for LLM prompt
            - citation_list: List of citation dicts with metadata

        Example:
            context, citations = await service.retrieve_relevant_knowledge(
                "How do I configure Redis?",
                top_k=5,
                score_threshold=0.7,
                categories=["system_knowledge"]
            )
        """
        start_time = time.time()

        try:
            # Perform advanced search using RAGService
            # Issue #382: metrics unused, using _ to indicate intentionally discarded
            # Issue #556: Pass categories for filtering
            results, _ = await self.rag_service.advanced_search(
                query=query,
                max_results=top_k,
                enable_reranking=True,
                categories=categories,
            )

            # Filter by score threshold
            filtered_results = self._filter_by_score(results, score_threshold)

            # Format for chat integration
            context_string = self.format_knowledge_context(filtered_results)
            citations = self.format_citations(filtered_results)

            retrieval_time = time.time() - start_time
            logger.info(
                "Retrieved %d/%d facts (threshold: %s) in %.3fs",
                len(filtered_results),
                len(results),
                score_threshold,
                retrieval_time,
            )

            return context_string, citations

        except Exception as e:
            # Graceful degradation - don't break chat flow
            logger.error(
                "Knowledge retrieval failed for query '%s...': %s", query[:50], e
            )
            logger.debug("Returning empty knowledge context due to error")
            return "", []

    def _filter_by_score(
        self, results: List[SearchResult], threshold: float
    ) -> List[SearchResult]:
        """
        Filter search results by relevance score.

        Uses rerank_score if available (more accurate), otherwise falls back
        to hybrid_score.

        Args:
            results: List of search results
            threshold: Minimum score to include (0.0-1.0)

        Returns:
            Filtered list of results meeting threshold
        """
        filtered = []
        for result in results:
            # Prefer rerank_score if available (cross-encoder is more accurate)
            score = (
                result.rerank_score
                if result.rerank_score is not None
                else result.hybrid_score
            )

            if score >= threshold:
                filtered.append(result)
            else:
                logger.debug(
                    "Filtered out result (score %.3f < %s): %s...",
                    score,
                    threshold,
                    result.content[:80],
                )

        return filtered

    def format_knowledge_context(self, facts: List[SearchResult]) -> str:
        """
        Format knowledge facts into context string for LLM prompt.

        Creates a clean, numbered list of relevant facts that can be
        prepended to the LLM prompt.

        Args:
            facts: List of filtered search results

        Returns:
            Formatted context string for LLM
        """
        if not facts:
            return ""

        # Build context header
        context_lines = ["KNOWLEDGE CONTEXT:"]

        # Add each fact with ranking
        for i, fact in enumerate(facts, 1):
            # Use rerank_score if available for display
            score = (
                fact.rerank_score
                if fact.rerank_score is not None
                else fact.hybrid_score
            )

            # Format: "1. [score: 0.95] Fact content here"
            context_lines.append(f"{i}. [score: {score:.2f}] {fact.content.strip()}")

        # Join with newlines
        return "\n".join(context_lines)

    def format_citations(self, facts: List[SearchResult]) -> List[Dict]:
        """
        Format facts into citation objects for frontend display.

        Creates structured citation data that can be sent to frontend
        for source attribution.

        Args:
            facts: List of filtered search results

        Returns:
            List of citation dictionaries with metadata
        """
        citations = []

        for i, fact in enumerate(facts, 1):
            # Extract relevant metadata
            score = (
                fact.rerank_score
                if fact.rerank_score is not None
                else fact.hybrid_score
            )

            citation = {
                "id": fact.metadata.get("id", f"citation_{i}"),
                "content": fact.content.strip(),
                "score": round(score, 3),
                "source": fact.source_path,
                "rank": i,
                "metadata": {
                    "semantic_score": round(fact.semantic_score, 3),
                    "keyword_score": round(fact.keyword_score, 3),
                    "hybrid_score": round(fact.hybrid_score, 3),
                    "chunk_index": fact.chunk_index,
                },
            }

            # Add rerank_score if available
            if fact.rerank_score is not None:
                citation["metadata"]["rerank_score"] = round(fact.rerank_score, 3)

            citations.append(citation)

        return citations

    def _match_category_keywords(
        self, query_lower: str, keywords: frozenset, category: str
    ) -> Optional[List[str]]:
        """
        Check if query matches any keywords for a category.

        Issue #620: Extracted from _select_categories_for_intent.

        Args:
            query_lower: Lowercase query string
            keywords: Set of keywords to match
            category: Category name to return if matched

        Returns:
            List containing the category if matched, None otherwise
        """
        if any(kw in query_lower for kw in keywords):
            logger.debug("[Smart Category] Selected: %s", category)
            return [category]
        return None

    def _select_categories_for_intent(
        self,
        intent_result: QueryIntentResult,
        query: str,
    ) -> Optional[List[str]]:
        """
        Select appropriate categories based on query intent.

        Issue #556: Smart category selection for optimized retrieval.
        Issue #620: Refactored to use class constants and helper method.

        Args:
            intent_result: Detected query intent
            query: Original query string

        Returns:
            List of categories to search, or None for all categories
        """
        query_lower = query.lower()

        # Check each category in priority order
        category_checks = [
            (self.AUTOBOT_KEYWORDS, "autobot_knowledge"),
            (self.SYSTEM_KEYWORDS, "system_knowledge"),
            (self.USER_KEYWORDS, "user_knowledge"),
        ]

        for keywords, category in category_checks:
            result = self._match_category_keywords(query_lower, keywords, category)
            if result:
                return result

        # For KNOWLEDGE_QUERY intent, search all relevant categories
        if intent_result.intent == QueryKnowledgeIntent.KNOWLEDGE_QUERY:
            logger.debug("[Smart Category] No specific category - searching all")
            return None

        return None

    def _should_skip_retrieval(
        self, intent_result: QueryIntentResult, force_retrieval: bool
    ) -> bool:
        """
        Determine if knowledge retrieval should be skipped.

        Issue #665: Extracted from smart_retrieve_knowledge to reduce function length.
        Issue #750: Deduplicated from conversation_aware_retrieve.

        Args:
            intent_result: Query intent detection result
            force_retrieval: If True, never skip retrieval

        Returns:
            True if retrieval should be skipped
        """
        if force_retrieval:
            return False

        if not intent_result.should_use_knowledge:
            logger.info(
                "[RAG] Skipping retrieval - intent=%s, confidence=%.2f",
                intent_result.intent.value,
                intent_result.confidence,
            )
            return True

        return False

    async def smart_retrieve_knowledge(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.7,
        force_retrieval: bool = False,
        categories: Optional[List[str]] = None,
        enable_smart_categories: bool = True,
    ) -> Tuple[str, List[Dict], QueryIntentResult]:
        """
        Smart knowledge retrieval with intent detection.

        Issue #665: Refactored to use extracted helper methods.

        Args:
            query: User's chat message/query
            top_k: Maximum number of knowledge facts to retrieve
            score_threshold: Minimum relevance score (0.0-1.0) to include
            force_retrieval: If True, bypass intent detection and always retrieve
            categories: Optional list of categories to filter results
            enable_smart_categories: If True, automatically select categories

        Returns:
            Tuple of (context_string, citations, intent_result)
        """
        start_time = time.time()
        intent_result = self.intent_detector.detect_intent(query)

        # Issue #665: Use helper for skip decision
        if self._should_skip_retrieval(intent_result, force_retrieval):
            return "", [], intent_result

        # Issue #556: Smart category selection if not explicitly provided
        effective_categories = categories
        if effective_categories is None and enable_smart_categories:
            effective_categories = self._select_categories_for_intent(
                intent_result, query
            )

        logger.info(
            "[Smart RAG] Retrieving - intent=%s, confidence=%.2f, categories=%s",
            intent_result.intent.value,
            intent_result.confidence,
            effective_categories or "all",
        )

        context_string, citations = await self.retrieve_relevant_knowledge(
            query=query,
            top_k=top_k,
            score_threshold=score_threshold,
            categories=effective_categories,
        )

        logger.info(
            "[Smart RAG] Completed in %.3fs - %d citations found",
            time.time() - start_time,
            len(citations),
        )

        return context_string, citations, intent_result

    def detect_query_intent(self, query: str) -> QueryIntentResult:
        """
        Detect the intent of a query without performing retrieval.

        Useful for logging, debugging, or making decisions before retrieval.

        Args:
            query: User's chat message

        Returns:
            QueryIntentResult with intent type and recommendation
        """
        return self.intent_detector.detect_intent(query)

    def _enhance_query_with_context(
        self,
        query: str,
        conversation_history: List[Dict[str, str]],
    ) -> EnhancedQuery:
        """
        Enhance query with conversation context (Issue #665: extracted).

        Args:
            query: Original query
            conversation_history: Previous exchanges

        Returns:
            EnhancedQuery with context entities
        """
        enhanced_query = self.context_enhancer.enhance_query(
            query=query,
            conversation_history=conversation_history,
            max_history_items=3,
        )

        if enhanced_query.enhancement_applied:
            logger.info(
                "[Conversation RAG] Query enhanced: '%s...' → '%s...' (entities: %s)",
                query[:50],
                enhanced_query.enhanced_query[:80],
                enhanced_query.context_entities,
            )
        else:
            logger.debug(
                "[Conversation RAG] No enhancement needed for query: '%s...'",
                query[:50],
            )

        return enhanced_query

    def _get_effective_categories(
        self,
        intent_result: QueryIntentResult,
        query: str,
        categories: Optional[List[str]],
        enable_smart_categories: bool,
    ) -> Optional[List[str]]:
        """
        Determine effective categories for retrieval.

        Issue #665: Extracted from conversation_aware_retrieve for clarity.

        Args:
            intent_result: Detected query intent
            query: Original query string
            categories: Explicitly provided categories (takes priority)
            enable_smart_categories: Whether to auto-select categories

        Returns:
            List of categories to use, or None for all categories
        """
        if categories is not None:
            return categories
        if enable_smart_categories:
            return self._select_categories_for_intent(intent_result, query)
        return None

    def _get_search_query(
        self,
        query: str,
        enhanced_query: EnhancedQuery,
    ) -> str:
        """
        Get the search query to use for retrieval.

        Issue #665: Extracted from conversation_aware_retrieve for clarity.

        Args:
            query: Original query string
            enhanced_query: Enhanced query result from context enhancer

        Returns:
            Enhanced query if enhancement was applied, otherwise original
        """
        if enhanced_query.enhancement_applied:
            return enhanced_query.enhanced_query
        return query

    async def conversation_aware_retrieve(
        self,
        query: str,
        conversation_history: List[Dict[str, str]],
        top_k: int = 5,
        score_threshold: float = 0.7,
        force_retrieval: bool = False,
        categories: Optional[List[str]] = None,
        enable_smart_categories: bool = True,
    ) -> Tuple[str, List[Dict], QueryIntentResult, Optional[EnhancedQuery]]:
        """Conversation-aware knowledge retrieval with context enhancement.

        Issue #249 Phase 3, #556, #665: Uses conversation history to enhance
        queries before RAG retrieval. Combines intent detection with context
        enhancement. Returns (context_string, citations, intent_result,
        enhanced_query).
        """
        start_time = time.time()
        intent_result = self.intent_detector.detect_intent(query)

        # Check if we should skip retrieval (Issue #665: uses helper)
        if self._should_skip_retrieval(intent_result, force_retrieval):
            return "", [], intent_result, None

        # Enhance query and determine categories (Issue #665: uses helpers)
        enhanced_query = self._enhance_query_with_context(query, conversation_history)
        effective_categories = self._get_effective_categories(
            intent_result, query, categories, enable_smart_categories
        )
        search_query = self._get_search_query(query, enhanced_query)

        # Perform retrieval
        context_string, citations = await self.retrieve_relevant_knowledge(
            query=search_query,
            top_k=top_k,
            score_threshold=score_threshold,
            categories=effective_categories,
        )

        logger.info(
            "[Conversation RAG] Completed in %.3fs - %d citations, enhanced=%s, categories=%s",
            time.time() - start_time,
            len(citations),
            enhanced_query.enhancement_applied,
            effective_categories or "all",
        )
        return context_string, citations, intent_result, enhanced_query

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
        score_threshold: float = 0.6,
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
                logger.debug(
                    "[Doc Search] Query not documentation-related: '%s...'", query[:50]
                )
                return "", []

            return self._search_and_format_documentation(
                query, n_results, score_threshold, start_time
            )

        except Exception as e:
            logger.error("Documentation retrieval failed: %s", e)
            return "", []

    async def retrieve_combined_knowledge(
        self,
        query: str,
        top_k: int = 5,
        doc_results: int = 3,
        score_threshold: float = 0.7,
        doc_threshold: float = 0.6,
        categories: Optional[List[str]] = None,
    ) -> Tuple[str, List[Dict], List[Dict[str, Any]]]:
        """
        Retrieve combined knowledge from RAG and documentation sources.

        Issue #250: Combines general knowledge retrieval with documentation
        search for comprehensive context.

        Issue #556: Added categories parameter for filtering RAG results.

        Args:
            query: User's chat message/query
            top_k: Maximum knowledge facts from RAG
            doc_results: Maximum documentation chunks
            score_threshold: Minimum RAG relevance score
            doc_threshold: Minimum documentation relevance score
            categories: Optional list of categories to filter RAG results

        Returns:
            Tuple of (combined_context, rag_citations, doc_results)
        """
        # Retrieve from both sources in parallel-ish (documentation is sync)
        doc_context, doc_results_list = await self.retrieve_documentation(
            query=query,
            n_results=doc_results,
            score_threshold=doc_threshold,
        )

        rag_context, rag_citations = await self.retrieve_relevant_knowledge(
            query=query,
            top_k=top_k,
            score_threshold=score_threshold,
            categories=categories,
        )

        # Combine contexts
        combined_parts = []
        if doc_context:
            combined_parts.append(doc_context)
        if rag_context:
            combined_parts.append(rag_context)

        combined_context = "\n\n".join(combined_parts) if combined_parts else ""

        return combined_context, rag_citations, doc_results_list

    async def get_knowledge_stats(self) -> Dict:
        """
        Get statistics about knowledge retrieval service.

        Returns:
            Dictionary with service statistics
        """
        rag_stats = self.rag_service.get_stats()

        stats = {
            "service": "ChatKnowledgeService",
            "rag_service_initialized": rag_stats.get("initialized", False),
            "rag_cache_entries": rag_stats.get("cache_entries", 0),
            "kb_implementation": rag_stats.get("kb_implementation", "unknown"),
            "intent_detector_available": self.intent_detector is not None,
            "context_enhancer_available": self.context_enhancer is not None,
            "doc_searcher_enabled": self.doc_searcher is not None,
        }

        # Add documentation stats if available
        if self.doc_searcher and self.doc_searcher._initialized:
            try:
                doc_count = self.doc_searcher._collection.count()
                stats["documentation_chunks"] = doc_count
            except Exception:
                stats["documentation_chunks"] = 0

        return stats
