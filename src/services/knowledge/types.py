# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Service Types

Issue #381: Extracted from chat_knowledge_service.py god class refactoring.
Contains enums and data classes for knowledge retrieval operations.
"""

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, List

# Issue #380: Module-level frozenset for follow-up keywords
FOLLOWUP_KEYWORDS: FrozenSet[str] = frozenset({"more", "elaborate", "explain"})


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


@dataclass
class EnhancedQuery:
    """Result of conversation-aware query enhancement."""

    original_query: str
    enhanced_query: str
    context_entities: List[str]  # Entities extracted from conversation
    context_topics: List[str]  # Topics from recent conversation
    enhancement_applied: bool
    reasoning: str
