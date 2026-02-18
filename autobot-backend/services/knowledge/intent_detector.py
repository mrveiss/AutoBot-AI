# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Query Intent Detector

Issue #381: Extracted from chat_knowledge_service.py god class refactoring.
Contains QueryKnowledgeIntentDetector for smart RAG triggering.
"""

import re
import threading
from typing import Optional

from .types import QueryIntentResult, QueryKnowledgeIntent


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
        """Initialize the detector with compiled query intent classification patterns."""
        self._knowledge_re = [
            re.compile(p, re.IGNORECASE) for p in self.KNOWLEDGE_PATTERNS
        ]
        self._command_re = [re.compile(p, re.IGNORECASE) for p in self.COMMAND_PATTERNS]
        self._conversational_re = [
            re.compile(p, re.IGNORECASE) for p in self.CONVERSATIONAL_PATTERNS
        ]
        self._code_gen_re = [
            re.compile(p, re.IGNORECASE) for p in self.CODE_GENERATION_PATTERNS
        ]

    def _check_pattern_match(
        self, patterns: list, query_lower: str
    ) -> Optional[QueryIntentResult]:
        """
        Check if query matches any pattern in a list and return corresponding result.

        Args:
            patterns: List of compiled regex patterns to check
            query_lower: Lowercase query string to match against

        Returns:
            QueryIntentResult if match found, None otherwise

        Issue #620.
        """
        for pattern in patterns:
            if pattern.search(query_lower):
                return pattern
        return None

    def _classify_by_query_length(self, query: str) -> QueryIntentResult:
        """
        Classify query based on word count when no patterns matched.

        Args:
            query: Original user query

        Returns:
            QueryIntentResult based on query length heuristics

        Issue #620.
        """
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
        if self._check_pattern_match(self._conversational_re, query_lower):
            return QueryIntentResult(
                intent=QueryKnowledgeIntent.CONVERSATIONAL,
                should_use_knowledge=False,
                confidence=0.9,
                reasoning="Conversational message detected - no knowledge needed",
            )

        # Check command patterns (skip RAG - execute directly)
        if self._check_pattern_match(self._command_re, query_lower):
            return QueryIntentResult(
                intent=QueryKnowledgeIntent.COMMAND_REQUEST,
                should_use_knowledge=False,
                confidence=0.85,
                reasoning="Command request detected - execute directly",
            )

        # Check knowledge patterns (use RAG)
        knowledge_matches = sum(1 for p in self._knowledge_re if p.search(query_lower))
        if knowledge_matches >= 1:
            confidence = min(0.7 + (knowledge_matches * 0.1), 0.95)
            return QueryIntentResult(
                intent=QueryKnowledgeIntent.KNOWLEDGE_QUERY,
                should_use_knowledge=True,
                confidence=confidence,
                reasoning=f"Knowledge query detected ({knowledge_matches} patterns matched)",
            )

        # Check code generation patterns (might use RAG for context)
        if self._check_pattern_match(self._code_gen_re, query_lower):
            return QueryIntentResult(
                intent=QueryKnowledgeIntent.CODE_GENERATION,
                should_use_knowledge=True,
                confidence=0.75,
                reasoning="Code generation request - RAG may provide useful context",
            )

        # Default: classify based on query length
        return self._classify_by_query_length(query)


# Global detector instance for reuse (thread-safe)
_query_intent_detector: Optional[QueryKnowledgeIntentDetector] = None
_query_intent_detector_lock = threading.Lock()


def get_query_intent_detector() -> QueryKnowledgeIntentDetector:
    """Get or create the global query intent detector instance (thread-safe)."""
    global _query_intent_detector
    if _query_intent_detector is None:
        with _query_intent_detector_lock:
            # Double-check after acquiring lock
            if _query_intent_detector is None:
                _query_intent_detector = QueryKnowledgeIntentDetector()
    return _query_intent_detector
