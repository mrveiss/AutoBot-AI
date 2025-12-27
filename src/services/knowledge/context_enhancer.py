# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation Context Enhancer

Issue #381: Extracted from chat_knowledge_service.py god class refactoring.
Contains ConversationContextEnhancer for conversation-aware RAG.
"""

import re
import threading
from typing import Dict, List, Optional

from .types import FOLLOWUP_KEYWORDS, EnhancedQuery


class ConversationContextEnhancer:
    """
    Enhances queries with conversation context for better RAG results.

    Issue #249 Phase 3: Conversation-Aware RAG.

    Uses conversation history to:
    1. Resolve pronouns and references (it, this, that, they)
    2. Extract key entities and topics from conversation
    3. Expand queries with relevant context
    """

    # Pronouns that may refer to previous context
    REFERENCE_PRONOUNS = {
        "it", "this", "that", "these", "those", "they", "them",
        "its", "their", "the same", "such", "above", "previous",
    }

    # Question words that often need context
    CONTEXT_QUESTION_PATTERNS = [
        r"^(how|why|what|when|where)\s+(about|does|do|is|are|can|should)\s+(it|this|that)",
        r"^(can you|could you|would you)\s+.*\s+(it|this|that|them)",
        r"^(tell me more|explain more|elaborate)",
        r"^(and|but|also|what about)",
    ]

    # Patterns to extract entities from text
    ENTITY_PATTERNS = [
        r"\b(Redis|Docker|Kubernetes|PostgreSQL|MongoDB|Nginx|Apache)\b",
        r"\b(Python|JavaScript|TypeScript|Vue|React|FastAPI|Django)\b",
        r"\b(API|REST|GraphQL|WebSocket|SSE|HTTP)\b",
        r"\b(database|server|service|worker|queue|cache)\b",
        r"\b(config|configuration|setup|deployment|installation)\b",
        r"\b(error|exception|bug|issue|problem|failure)\b",
    ]

    def __init__(self):
        """Initialize the context enhancer with compiled conversation analysis patterns.

        Issue #509: Optimized entity extraction by combining patterns into
        single regex for O(n) instead of O(n*p) where p = number of patterns.
        """
        self._reference_re = re.compile(
            r"\b(" + "|".join(self.REFERENCE_PRONOUNS) + r")\b",
            re.IGNORECASE
        )
        self._context_question_re = [
            re.compile(p, re.IGNORECASE) for p in self.CONTEXT_QUESTION_PATTERNS
        ]
        # Issue #509: Combined entity pattern for single-pass extraction
        # O(1) regex compilation, O(n) matching instead of O(n*p)
        self._combined_entity_re = re.compile(
            "|".join(f"({p})" for p in self.ENTITY_PATTERNS),
            re.IGNORECASE
        )

    def enhance_query(
        self,
        query: str,
        conversation_history: List[Dict[str, str]],
        max_history_items: int = 3,
    ) -> EnhancedQuery:
        """
        Enhance a query with conversation context.

        Args:
            query: Current user query
            conversation_history: List of conversation exchanges
                Format: [{"user": "msg", "assistant": "response"}, ...]
            max_history_items: Maximum number of history items to consider

        Returns:
            EnhancedQuery with original and enhanced query
        """
        # #624: Compute word_count once, pass to all methods
        word_count = len(query.split())

        # Check if enhancement is needed
        needs_context = self._needs_context_enhancement(query, word_count)

        if not needs_context or not conversation_history:
            return EnhancedQuery(
                original_query=query,
                enhanced_query=query,
                context_entities=[],
                context_topics=[],
                enhancement_applied=False,
                reasoning="No context enhancement needed",
            )

        # Get recent conversation context
        recent_history = conversation_history[-max_history_items:]

        # Extract entities and topics from conversation
        context_entities = self._extract_entities(recent_history)
        context_topics = self._extract_topics(recent_history)

        # Build enhanced query
        enhanced_query = self._build_enhanced_query(
            query, recent_history, context_entities, context_topics, word_count
        )

        return EnhancedQuery(
            original_query=query,
            enhanced_query=enhanced_query,
            context_entities=context_entities,
            context_topics=context_topics,
            enhancement_applied=enhanced_query != query,
            reasoning=self._get_enhancement_reasoning(
                query, context_entities, word_count
            ),
        )

    def _needs_context_enhancement(
        self, query: str, word_count: Optional[int] = None
    ) -> bool:
        """Check if a query would benefit from context enhancement."""
        query_lower = query.lower().strip()

        # Check for pronoun references
        if self._reference_re.search(query_lower):
            return True

        # Check for context-dependent question patterns
        for pattern in self._context_question_re:
            if pattern.search(query_lower):
                return True

        # Very short queries often need context (#624: avoid repeated split)
        if word_count is None:
            word_count = len(query.split())
        if word_count <= 3:
            return True

        return False

    def _extract_entities(
        self, history: List[Dict[str, str]]
    ) -> List[str]:
        """Extract named entities from conversation history.

        Issue #509: Optimized O(n³) → O(n²) by using combined regex pattern
        for single-pass extraction instead of iterating over multiple patterns.
        """
        entities = set()

        for exchange in history:
            user_msg = exchange.get("user", "")
            assistant_msg = exchange.get("assistant", "")

            # Issue #509: Single-pass extraction using combined pattern
            # Instead of: for pattern in patterns → for match in pattern.finditer()
            for match in self._combined_entity_re.finditer(user_msg):
                entities.add(match.group(0))
            for match in self._combined_entity_re.finditer(assistant_msg):
                entities.add(match.group(0))

        return list(entities)[:5]  # Limit to 5 most recent entities

    def _extract_topics(
        self, history: List[Dict[str, str]]
    ) -> List[str]:
        """Extract main topics from conversation history."""
        topics = []

        # Look at user messages to understand conversation topics
        for exchange in history:
            user_msg = exchange.get("user", "")
            # Extract first significant noun phrase (simplified approach)
            words = user_msg.split()
            if len(words) >= 3:
                # Take key phrase from user message
                topic = " ".join(words[:min(5, len(words))])
                if len(topic) > 10:  # Only meaningful topics
                    topics.append(topic)

        return topics[-3:]  # Last 3 topics

    def _build_enhanced_query(
        self,
        query: str,
        history: List[Dict[str, str]],
        entities: List[str],
        topics: List[str],
        word_count: Optional[int] = None,
    ) -> str:
        """Build an enhanced query with context."""
        enhanced_parts = [query]

        # If query has pronouns and we have entities, add context
        if self._reference_re.search(query.lower()) and entities:
            # Add most relevant entity as context
            context_phrase = f" (context: {', '.join(entities[:2])})"
            enhanced_parts.append(context_phrase)

        # For very short queries, add recent topic (#624: avoid repeated split)
        elif (word_count if word_count is not None else len(query.split())) <= 3 and topics:
            last_topic = topics[-1]
            # Check if the short query relates to last topic
            enhanced_parts.append(f" (regarding: {last_topic})")

        # If asking "more" about something, include last assistant response snippet
        if any(word in query.lower() for word in FOLLOWUP_KEYWORDS):
            if history:
                last_response = history[-1].get("assistant", "")
                if last_response:
                    # Add snippet of last response for context
                    snippet = last_response[:100].strip()
                    if len(last_response) > 100:
                        snippet += "..."
                    enhanced_parts.append(f" (following up on: {snippet})")

        return "".join(enhanced_parts)

    def _get_enhancement_reasoning(
        self, query: str, entities: List[str], word_count: Optional[int] = None
    ) -> str:
        """Generate reasoning for the enhancement."""
        reasons = []

        if self._reference_re.search(query.lower()):
            reasons.append("pronoun reference detected")

        # #624: avoid repeated split
        if (word_count if word_count is not None else len(query.split())) <= 3:
            reasons.append("short query")

        if entities:
            reasons.append(f"context entities: {', '.join(entities[:2])}")

        if not reasons:
            return "Context enhancement applied"

        return "; ".join(reasons)


# Global context enhancer instance (thread-safe)
_context_enhancer: Optional[ConversationContextEnhancer] = None
_context_enhancer_lock = threading.Lock()


def get_context_enhancer() -> ConversationContextEnhancer:
    """Get or create the global context enhancer instance (thread-safe)."""
    global _context_enhancer
    if _context_enhancer is None:
        with _context_enhancer_lock:
            # Double-check after acquiring lock
            if _context_enhancer is None:
                _context_enhancer = ConversationContextEnhancer()
    return _context_enhancer
