#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat Knowledge Service - RAG integration layer for chat workflow.

Issue #381: This file has been refactored. Implementation moved to
src/services/knowledge/ package. This file now serves as a thin facade
for backward compatibility.

Provides knowledge retrieval capabilities for the chat system, integrating
with RAGService to add context-aware knowledge to LLM prompts.

Features:
- Semantic search for relevant knowledge facts
- Score-based filtering for quality control
- Graceful degradation on errors
- Performance logging
- Citation formatting for source attribution
- Query intent detection for smart RAG triggering (Issue #249 Phase 2)
- Conversation-aware query enhancement (Issue #249 Phase 3)
"""

# Issue #381: Re-export all public API from the knowledge package
# This maintains backward compatibility with existing imports
from src.services.knowledge import (
    ChatKnowledgeService,
    ConversationContextEnhancer,
    DocumentationSearcher,
    EnhancedQuery,
    QueryIntentResult,
    QueryKnowledgeIntent,
    QueryKnowledgeIntentDetector,
    get_context_enhancer,
    get_documentation_searcher,
    get_query_intent_detector,
)

__all__ = [
    # Types and dataclasses
    "QueryKnowledgeIntent",
    "QueryIntentResult",
    "EnhancedQuery",
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
