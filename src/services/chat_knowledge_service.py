#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat Knowledge Service - RAG integration layer for chat workflow.

Provides knowledge retrieval capabilities for the chat system, integrating
with RAGService to add context-aware knowledge to LLM prompts.

Features:
- Semantic search for relevant knowledge facts
- Score-based filtering for quality control
- Graceful degradation on errors
- Performance logging
- Citation formatting for source attribution
- Query intent detection for smart RAG triggering (Issue #249 Phase 2)
"""

import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from backend.services.rag_service import RAGService
from src.advanced_rag_optimizer import SearchResult
from src.utils.logging_manager import get_llm_logger

logger = get_llm_logger("chat_knowledge_service")


class QueryKnowledgeIntent(Enum):
    """Intent categories for knowledge retrieval decisions."""

    KNOWLEDGE_QUERY = "knowledge_query"  # Factual questions, how-to, explanations
    COMMAND_REQUEST = "command_request"  # Execute terminal commands
    CONVERSATIONAL = "conversational"  # Greetings, thanks, acknowledgments
    CODE_GENERATION = "code_generation"  # Write/generate code
    CLARIFICATION = "clarification"  # Follow-up questions about prior context


@dataclass
class QueryIntentResult:
    """Result of query intent detection."""

    intent: QueryKnowledgeIntent
    should_use_knowledge: bool
    confidence: float
    reasoning: str


class QueryKnowledgeIntentDetector:
    """
    Detects query intent to optimize knowledge retrieval decisions.

    Issue #249 Phase 2: Smart RAG triggering based on query type.

    Uses pattern matching for fast (<5ms) classification to determine
    if a query would benefit from knowledge base retrieval.
    """

    # Patterns indicating knowledge queries (should use RAG)
    KNOWLEDGE_PATTERNS = [
        r"\b(what|how|why|when|where|which|who)\b.*\?",  # Question words
        r"\b(explain|describe|tell me about|what is|what are)\b",
        r"\b(difference between|compare|versus|vs\.?)\b",
        r"\b(configure|setup|install|deploy|troubleshoot)\b",
        r"\b(documentation|docs|guide|tutorial|example)\b",
        r"\b(error|issue|problem|bug|fix|solve)\b",
        r"\b(best practice|recommend|suggestion)\b",
        r"\b(architecture|design|pattern|structure)\b",
    ]

    # Patterns indicating command requests (skip RAG - execute directly)
    COMMAND_PATTERNS = [
        r"^(run|execute|start|stop|restart|kill)\b",
        r"\b(ls|cd|pwd|cat|grep|find|mkdir|rm|cp|mv)\b",
        r"\b(git\s+(status|add|commit|push|pull|clone|checkout))\b",
        r"\b(docker|kubectl|npm|pip|apt|systemctl)\b",
        r"\b(curl|wget|ssh|scp)\b",
        r"^(show|list|check)\s+(files|processes|status|logs)",
    ]

    # Patterns indicating conversational (skip RAG - respond directly)
    CONVERSATIONAL_PATTERNS = [
        r"^(hi|hello|hey|good\s+(morning|afternoon|evening))\b",
        r"^(thanks|thank you|thx|ty)\b",
        r"^(bye|goodbye|see you|ttyl)\b",
        r"^(ok|okay|got it|understood|sure|yes|no)\b",
        r"^(nice|great|awesome|perfect|cool)\b",
    ]

    # Patterns indicating code generation (might use RAG for context)
    CODE_GENERATION_PATTERNS = [
        r"\b(write|create|generate|implement|code)\b.*\b(function|class|script|code)\b",
        r"\b(refactor|optimize|improve)\b.*\b(code|function|class)\b",
        r"```",  # Code blocks in message
    ]

    def __init__(self):
        """Initialize the detector with compiled regex patterns."""
        self._knowledge_re = [
            re.compile(p, re.IGNORECASE) for p in self.KNOWLEDGE_PATTERNS
        ]
        self._command_re = [
            re.compile(p, re.IGNORECASE) for p in self.COMMAND_PATTERNS
        ]
        self._conversational_re = [
            re.compile(p, re.IGNORECASE) for p in self.CONVERSATIONAL_PATTERNS
        ]
        self._code_gen_re = [
            re.compile(p, re.IGNORECASE) for p in self.CODE_GENERATION_PATTERNS
        ]

    def detect_intent(self, query: str) -> QueryIntentResult:
        """
        Detect the intent of a query to determine if knowledge retrieval is needed.

        Args:
            query: User's chat message

        Returns:
            QueryIntentResult with intent type and recommendation
        """
        query_lower = query.lower().strip()

        # Check conversational patterns first (highest priority for skipping)
        for pattern in self._conversational_re:
            if pattern.search(query_lower):
                return QueryIntentResult(
                    intent=QueryKnowledgeIntent.CONVERSATIONAL,
                    should_use_knowledge=False,
                    confidence=0.9,
                    reasoning="Conversational message detected - no knowledge needed",
                )

        # Check command patterns (skip RAG - execute directly)
        for pattern in self._command_re:
            if pattern.search(query_lower):
                return QueryIntentResult(
                    intent=QueryKnowledgeIntent.COMMAND_REQUEST,
                    should_use_knowledge=False,
                    confidence=0.85,
                    reasoning="Command request detected - execute directly",
                )

        # Check knowledge patterns (use RAG)
        knowledge_matches = sum(
            1 for p in self._knowledge_re if p.search(query_lower)
        )
        if knowledge_matches >= 1:
            confidence = min(0.7 + (knowledge_matches * 0.1), 0.95)
            return QueryIntentResult(
                intent=QueryKnowledgeIntent.KNOWLEDGE_QUERY,
                should_use_knowledge=True,
                confidence=confidence,
                reasoning=f"Knowledge query detected ({knowledge_matches} patterns matched)",
            )

        # Check code generation patterns (might use RAG for context)
        for pattern in self._code_gen_re:
            if pattern.search(query_lower):
                return QueryIntentResult(
                    intent=QueryKnowledgeIntent.CODE_GENERATION,
                    should_use_knowledge=True,  # Use RAG for code context
                    confidence=0.75,
                    reasoning="Code generation request - RAG may provide useful context",
                )

        # Default: Use knowledge for longer queries, skip for short ones
        word_count = len(query.split())
        if word_count >= 5:
            return QueryIntentResult(
                intent=QueryKnowledgeIntent.KNOWLEDGE_QUERY,
                should_use_knowledge=True,
                confidence=0.6,
                reasoning=f"Query length ({word_count} words) suggests knowledge may help",
            )
        else:
            return QueryIntentResult(
                intent=QueryKnowledgeIntent.CLARIFICATION,
                should_use_knowledge=False,
                confidence=0.5,
                reasoning="Short query - likely a follow-up or clarification",
            )


# Global detector instance for reuse
_query_intent_detector: Optional[QueryKnowledgeIntentDetector] = None


def get_query_intent_detector() -> QueryKnowledgeIntentDetector:
    """Get or create the global query intent detector instance."""
    global _query_intent_detector
    if _query_intent_detector is None:
        _query_intent_detector = QueryKnowledgeIntentDetector()
    return _query_intent_detector


class ChatKnowledgeService:
    """
    Service for retrieving and formatting knowledge for chat interactions.

    This service acts as a bridge between the chat workflow and the RAG system,
    providing knowledge retrieval with appropriate filtering and formatting.
    """

    def __init__(self, rag_service: RAGService):
        """
        Initialize chat knowledge service.

        Args:
            rag_service: Configured RAGService instance
        """
        self.rag_service = rag_service
        logger.info("ChatKnowledgeService initialized")

    async def retrieve_relevant_knowledge(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.7,
    ) -> Tuple[str, List[Dict]]:
        """
        Retrieve relevant knowledge facts for a chat query.

        Args:
            query: User's chat message/query
            top_k: Maximum number of knowledge facts to retrieve
            score_threshold: Minimum relevance score (0.0-1.0) to include

        Returns:
            Tuple of (formatted_context_string, citation_list)
            - formatted_context_string: Knowledge context for LLM prompt
            - citation_list: List of citation dicts with metadata

        Example:
            context, citations = await service.retrieve_relevant_knowledge(
                "How do I configure Redis?",
                top_k=5,
                score_threshold=0.7
            )
        """
        start_time = time.time()

        try:
            # Perform advanced search using RAGService
            results, metrics = await self.rag_service.advanced_search(
                query=query,
                max_results=top_k,
                enable_reranking=True,
            )

            # Filter by score threshold
            filtered_results = self._filter_by_score(results, score_threshold)

            # Format for chat integration
            context_string = self.format_knowledge_context(filtered_results)
            citations = self.format_citations(filtered_results)

            retrieval_time = time.time() - start_time
            logger.info(
                f"Retrieved {len(filtered_results)}/{len(results)} facts "
                f"(threshold: {score_threshold}) in {retrieval_time:.3f}s"
            )

            return context_string, citations

        except Exception as e:
            # Graceful degradation - don't break chat flow
            logger.error(f"Knowledge retrieval failed for query '{query[:50]}...': {e}")
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
                    f"Filtered out result (score {score:.3f} < {threshold}): "
                    f"{result.content[:80]}..."
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

    async def get_knowledge_stats(self) -> Dict:
        """
        Get statistics about knowledge retrieval service.

        Returns:
            Dictionary with service statistics
        """
        rag_stats = self.rag_service.get_stats()

        return {
            "service": "ChatKnowledgeService",
            "rag_service_initialized": rag_stats.get("initialized", False),
            "rag_cache_entries": rag_stats.get("cache_entries", 0),
            "kb_implementation": rag_stats.get("kb_implementation", "unknown"),
        }


# Example usage pattern for integration into ChatWorkflowManager:
"""
Integration example:

In chat_workflow_manager.py, modify _prepare_llm_request_params():

    # Add after conversation history, before building full_prompt:

    # Retrieve relevant knowledge
    knowledge_context = ""
    citations = []

    if self.knowledge_service:  # Optional integration
        try:
            knowledge_context, citations = (
                await self.knowledge_service.retrieve_relevant_knowledge(
                    query=message,
                    top_k=5,
                    score_threshold=0.7
                )
            )
        except Exception as e:
            logger.error(f"Knowledge retrieval failed: {e}")
            # Continue without knowledge - graceful degradation

    # Build complete prompt with knowledge
    full_prompt = (
        system_prompt
        + knowledge_context + "\n\n"  # Add knowledge context
        + conversation_context
        + f"\n**Current user message:** {message}\n\nAssistant:"
    )

    # Store citations in session for frontend
    session.last_citations = citations
"""
