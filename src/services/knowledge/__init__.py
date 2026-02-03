# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Service Package

Issue #381: Extracted from chat_knowledge_service.py god class refactoring.
This package provides knowledge retrieval and query enhancement for chat interactions.

Components:
- types: Enums and dataclasses for intent detection and query enhancement
- intent_detector: Query intent classification for smart RAG triggering
- context_enhancer: Conversation-aware query enhancement
- doc_searcher: Documentation search integration
- service: Main ChatKnowledgeService coordinator
"""

from .context_enhancer import ConversationContextEnhancer, get_context_enhancer
from .doc_searcher import DocumentationSearcher, get_documentation_searcher
from .intent_detector import QueryKnowledgeIntentDetector, get_query_intent_detector
from .service import KNOWLEDGE_CATEGORIES, ChatKnowledgeService
from .types import EnhancedQuery, QueryIntentResult, QueryKnowledgeIntent

__all__ = [
    # Types and dataclasses
    "QueryKnowledgeIntent",
    "QueryIntentResult",
    "EnhancedQuery",
    # Constants
    "KNOWLEDGE_CATEGORIES",
    # Classes
    "QueryKnowledgeIntentDetector",
    "ConversationContextEnhancer",
    "DocumentationSearcher",
    "ChatKnowledgeService",
    # Factory functions
    "get_query_intent_detector",
    "get_context_enhancer",
    "get_documentation_searcher",
]
