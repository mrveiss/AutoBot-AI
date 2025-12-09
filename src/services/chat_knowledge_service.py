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
- Conversation-aware query enhancement (Issue #249 Phase 3)
"""

import re
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from backend.services.rag_service import RAGService
from src.advanced_rag_optimizer import SearchResult
from src.constants.network_constants import ServiceURLs
from src.constants.path_constants import PATH
from src.utils.logging_manager import get_llm_logger

logger = get_llm_logger("chat_knowledge_service")

# Issue #380: Module-level frozenset for follow-up keywords
_FOLLOWUP_KEYWORDS: FrozenSet[str] = frozenset({"more", "elaborate", "explain"})

# Issue #380: Use centralized PathConstants instead of repeated computation
PROJECT_ROOT = PATH.PROJECT_ROOT


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
        """Initialize the detector with compiled query intent classification patterns."""
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


# Global detector instance for reuse (thread-safe)
import threading as _threading_intent

_query_intent_detector: Optional[QueryKnowledgeIntentDetector] = None
_query_intent_detector_lock = _threading_intent.Lock()


def get_query_intent_detector() -> QueryKnowledgeIntentDetector:
    """Get or create the global query intent detector instance (thread-safe)."""
    global _query_intent_detector
    if _query_intent_detector is None:
        with _query_intent_detector_lock:
            # Double-check after acquiring lock
            if _query_intent_detector is None:
                _query_intent_detector = QueryKnowledgeIntentDetector()
    return _query_intent_detector


@dataclass
class EnhancedQuery:
    """Result of conversation-aware query enhancement."""

    original_query: str
    enhanced_query: str
    context_entities: List[str]  # Entities extracted from conversation
    context_topics: List[str]  # Topics from recent conversation
    enhancement_applied: bool
    reasoning: str


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
        """Initialize the context enhancer with compiled conversation analysis patterns."""
        self._reference_re = re.compile(
            r"\b(" + "|".join(self.REFERENCE_PRONOUNS) + r")\b",
            re.IGNORECASE
        )
        self._context_question_re = [
            re.compile(p, re.IGNORECASE) for p in self.CONTEXT_QUESTION_PATTERNS
        ]
        self._entity_re = [
            re.compile(p, re.IGNORECASE) for p in self.ENTITY_PATTERNS
        ]

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
        # Check if enhancement is needed
        needs_context = self._needs_context_enhancement(query)

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
            query, recent_history, context_entities, context_topics
        )

        return EnhancedQuery(
            original_query=query,
            enhanced_query=enhanced_query,
            context_entities=context_entities,
            context_topics=context_topics,
            enhancement_applied=enhanced_query != query,
            reasoning=self._get_enhancement_reasoning(query, context_entities),
        )

    def _needs_context_enhancement(self, query: str) -> bool:
        """Check if a query would benefit from context enhancement."""
        query_lower = query.lower().strip()

        # Check for pronoun references
        if self._reference_re.search(query_lower):
            return True

        # Check for context-dependent question patterns
        for pattern in self._context_question_re:
            if pattern.search(query_lower):
                return True

        # Very short queries often need context
        if len(query.split()) <= 3:
            return True

        return False

    def _extract_entities(
        self, history: List[Dict[str, str]]
    ) -> List[str]:
        """Extract named entities from conversation history."""
        entities = set()

        for exchange in history:
            user_msg = exchange.get("user", "")
            assistant_msg = exchange.get("assistant", "")

            for pattern in self._entity_re:
                # Extract from user messages
                for match in pattern.finditer(user_msg):
                    entities.add(match.group(0))
                # Extract from assistant messages
                for match in pattern.finditer(assistant_msg):
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
    ) -> str:
        """Build an enhanced query with context."""
        enhanced_parts = [query]

        # If query has pronouns and we have entities, add context
        if self._reference_re.search(query.lower()) and entities:
            # Add most relevant entity as context
            context_phrase = f" (context: {', '.join(entities[:2])})"
            enhanced_parts.append(context_phrase)

        # For very short queries, add recent topic
        elif len(query.split()) <= 3 and topics:
            last_topic = topics[-1]
            # Check if the short query relates to last topic
            enhanced_parts.append(f" (regarding: {last_topic})")

        # If asking "more" about something, include last assistant response snippet
        if any(word in query.lower() for word in _FOLLOWUP_KEYWORDS):
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
        self, query: str, entities: List[str]
    ) -> str:
        """Generate reasoning for the enhancement."""
        reasons = []

        if self._reference_re.search(query.lower()):
            reasons.append("pronoun reference detected")

        if len(query.split()) <= 3:
            reasons.append("short query")

        if entities:
            reasons.append(f"context entities: {', '.join(entities[:2])}")

        if not reasons:
            return "Context enhancement applied"

        return "; ".join(reasons)


# Global context enhancer instance (thread-safe)
import threading as _threading_context

_context_enhancer: Optional[ConversationContextEnhancer] = None
_context_enhancer_lock = _threading_context.Lock()


def get_context_enhancer() -> ConversationContextEnhancer:
    """Get or create the global context enhancer instance (thread-safe)."""
    global _context_enhancer
    if _context_enhancer is None:
        with _context_enhancer_lock:
            # Double-check after acquiring lock
            if _context_enhancer is None:
                _context_enhancer = ConversationContextEnhancer()
    return _context_enhancer


# ============================================================================
# DOCUMENTATION SEARCH INTEGRATION (Issue #250)
# ============================================================================


class DocumentationSearcher:
    """
    Searches indexed AutoBot documentation for relevant context.

    Issue #250: Enables chat agent self-awareness about project documentation.

    Uses the autobot_docs ChromaDB collection populated by tools/index_documentation.py
    to retrieve documentation about deployment, APIs, architecture, and troubleshooting.
    """

    # Patterns indicating documentation-related queries
    DOC_QUERY_PATTERNS = [
        r"\b(how|what|where)\b.*(autobot|deploy|start|run|setup)\b",
        r"\b(redis|chromadb|vm|infrastructure|frontend|backend)\b",
        r"\b(config|configure|configuration|setup)\b",
        r"\b(troubleshoot|debug|fix|error|issue)\b",
        r"\b(architecture|design|pattern|structure)\b",
        r"\b(api|endpoint|route)\b",
        r"\b(claude\.md|system-state|developer setup)\b",
        r"\b(workflow|rule|policy|standard|guideline)\b",
        r"\b(documentation|docs|guide)\b",
        r"\b(how do i|how to|what is|where is)\b",
    ]

    def __init__(self, collection_name: str = "autobot_docs"):
        """
        Initialize the documentation searcher.

        Args:
            collection_name: ChromaDB collection name for documentation
        """
        self.collection_name = collection_name
        self._client = None
        self._collection = None
        self._embed_model = None
        self._initialized = False
        self._doc_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.DOC_QUERY_PATTERNS
        ]

    def initialize(self) -> bool:
        """
        Initialize ChromaDB client and embedding model.

        Returns:
            True if initialization successful, False otherwise
        """
        if self._initialized:
            return True

        try:
            from llama_index.embeddings.ollama import OllamaEmbedding

            from src.utils.chromadb_client import get_chromadb_client

            # Initialize ChromaDB
            chromadb_path = PROJECT_ROOT / "data" / "chromadb"
            self._client = get_chromadb_client(str(chromadb_path))

            # Get documentation collection (don't create if not exists)
            try:
                self._collection = self._client.get_collection(
                    name=self.collection_name
                )
                doc_count = self._collection.count()
                logger.info(
                    f"DocumentationSearcher initialized: {doc_count} documents available"
                )
            except Exception:
                logger.warning(
                    f"Documentation collection '{self.collection_name}' not found. "
                    "Run 'python tools/index_documentation.py --tier 1' to index docs."
                )
                return False

            # Initialize embedding model
            self._embed_model = OllamaEmbedding(
                model_name="nomic-embed-text", base_url=ServiceURLs.OLLAMA_LOCAL
            )

            self._initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize DocumentationSearcher: {e}")
            return False

    def is_documentation_query(self, query: str) -> bool:
        """
        Check if a query is likely about AutoBot documentation.

        Args:
            query: User's chat message

        Returns:
            True if query appears to be about documentation
        """
        query_lower = query.lower()

        # Check patterns
        for pattern in self._doc_patterns:
            if pattern.search(query_lower):
                return True

        return False

    def search(
        self, query: str, n_results: int = 3, score_threshold: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Search documentation for relevant content.

        Args:
            query: Search query
            n_results: Maximum number of results
            score_threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of search result dictionaries with content and metadata
        """
        if not self._initialized:
            if not self.initialize():
                return []

        try:
            # Generate query embedding
            embedding = self._embed_model.get_text_embedding(query)

            # Search collection
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )

            if not results or not results.get("documents"):
                return []

            # Format results
            formatted = []
            for i, (doc, meta, dist) in enumerate(
                zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                )
            ):
                score = 1 - dist  # Convert distance to similarity
                if score >= score_threshold:
                    formatted.append(
                        {
                            "content": doc,
                            "score": round(score, 3),
                            "file_path": meta.get("file_path", "unknown"),
                            "section": meta.get("section", ""),
                            "subsection": meta.get("subsection", ""),
                            "doc_type": meta.get("doc_type", "documentation"),
                            "priority": meta.get("priority", "medium"),
                        }
                    )

            return formatted

        except Exception as e:
            logger.error(f"Documentation search failed: {e}")
            return []

    def format_as_context(self, results: List[Dict[str, Any]]) -> str:
        """
        Format search results as context for LLM prompt.

        Args:
            results: List of search results

        Returns:
            Formatted context string
        """
        if not results:
            return ""

        lines = ["AUTOBOT DOCUMENTATION CONTEXT:"]

        for i, result in enumerate(results, 1):
            source = result.get("file_path", "unknown")
            section = result.get("section", "")
            content = result.get("content", "").strip()

            lines.append(f"\n[{i}] From {source} - {section}:")
            lines.append(content)

        return "\n".join(lines)


# Global documentation searcher instance (thread-safe)
import threading as _threading_doc

_doc_searcher: Optional[DocumentationSearcher] = None
_doc_searcher_lock = _threading_doc.Lock()


def get_documentation_searcher() -> DocumentationSearcher:
    """Get or create the global documentation searcher instance (thread-safe)."""
    global _doc_searcher
    if _doc_searcher is None:
        with _doc_searcher_lock:
            # Double-check after acquiring lock
            if _doc_searcher is None:
                _doc_searcher = DocumentationSearcher()
    return _doc_searcher


class ChatKnowledgeService:
    """
    Service for retrieving and formatting knowledge for chat interactions.

    This service acts as a bridge between the chat workflow and the RAG system,
    providing knowledge retrieval with appropriate filtering and formatting.

    Issue #249 Phase 2: Now includes smart intent detection to optimize
    when to use knowledge retrieval.

    Issue #250: Added documentation search integration for AutoBot self-awareness.
    """

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
            f"conversation-aware RAG, doc_search={enable_doc_search}"
        )

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
            # Issue #382: metrics unused, using _ to indicate intentionally discarded
            results, _ = await self.rag_service.advanced_search(
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

    async def smart_retrieve_knowledge(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.7,
        force_retrieval: bool = False,
    ) -> Tuple[str, List[Dict], QueryIntentResult]:
        """
        Smart knowledge retrieval with intent detection.

        Issue #249 Phase 2: Uses query intent detection to decide whether
        to perform knowledge retrieval, optimizing performance by skipping
        RAG for queries that don't need it.

        Args:
            query: User's chat message/query
            top_k: Maximum number of knowledge facts to retrieve
            score_threshold: Minimum relevance score (0.0-1.0) to include
            force_retrieval: If True, bypass intent detection and always retrieve

        Returns:
            Tuple of (context_string, citations, intent_result)
            - context_string: Knowledge context for LLM prompt (empty if skipped)
            - citations: List of citation dicts (empty if skipped)
            - intent_result: The intent detection result for logging/debugging
        """
        start_time = time.time()

        # Detect query intent
        intent_result = self.intent_detector.detect_intent(query)

        # Decide whether to retrieve knowledge
        if not force_retrieval and not intent_result.should_use_knowledge:
            logger.info(
                f"[Smart RAG] Skipping retrieval - intent={intent_result.intent.value}, "
                f"confidence={intent_result.confidence:.2f}, reason={intent_result.reasoning}"
            )
            return "", [], intent_result

        # Perform retrieval
        logger.info(
            f"[Smart RAG] Retrieving - intent={intent_result.intent.value}, "
            f"confidence={intent_result.confidence:.2f}"
        )

        context_string, citations = await self.retrieve_relevant_knowledge(
            query=query,
            top_k=top_k,
            score_threshold=score_threshold,
        )

        retrieval_time = time.time() - start_time
        logger.info(
            f"[Smart RAG] Completed in {retrieval_time:.3f}s - "
            f"{len(citations)} citations found"
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

    async def conversation_aware_retrieve(
        self,
        query: str,
        conversation_history: List[Dict[str, str]],
        top_k: int = 5,
        score_threshold: float = 0.7,
        force_retrieval: bool = False,
    ) -> Tuple[str, List[Dict], QueryIntentResult, Optional[EnhancedQuery]]:
        """
        Conversation-aware knowledge retrieval with context enhancement.

        Issue #249 Phase 3: Uses conversation history to enhance queries
        before performing RAG retrieval. Combines intent detection (Phase 2)
        with context enhancement for optimal results.

        Args:
            query: User's chat message/query
            conversation_history: List of conversation exchanges
                Format: [{"user": "msg", "assistant": "response"}, ...]
            top_k: Maximum number of knowledge facts to retrieve
            score_threshold: Minimum relevance score (0.0-1.0) to include
            force_retrieval: If True, bypass intent detection and always retrieve

        Returns:
            Tuple of (context_string, citations, intent_result, enhanced_query)
            - context_string: Knowledge context for LLM prompt (empty if skipped)
            - citations: List of citation dicts (empty if skipped)
            - intent_result: The intent detection result
            - enhanced_query: The enhanced query result (None if not enhanced)
        """
        start_time = time.time()

        # Step 1: Detect query intent
        intent_result = self.intent_detector.detect_intent(query)

        # Step 2: Check if we should skip retrieval
        if not force_retrieval and not intent_result.should_use_knowledge:
            logger.info(
                f"[Conversation RAG] Skipping - intent={intent_result.intent.value}, "
                f"confidence={intent_result.confidence:.2f}"
            )
            return "", [], intent_result, None

        # Step 3: Enhance query with conversation context
        enhanced_query = self.context_enhancer.enhance_query(
            query=query,
            conversation_history=conversation_history,
            max_history_items=3,
        )

        # Log enhancement if applied
        if enhanced_query.enhancement_applied:
            logger.info(
                f"[Conversation RAG] Query enhanced: "
                f"'{query[:50]}...' → '{enhanced_query.enhanced_query[:80]}...' "
                f"(entities: {enhanced_query.context_entities})"
            )
        else:
            logger.debug(
                f"[Conversation RAG] No enhancement needed for query: '{query[:50]}...'"
            )

        # Step 4: Perform retrieval with enhanced query
        search_query = (
            enhanced_query.enhanced_query
            if enhanced_query.enhancement_applied
            else query
        )

        context_string, citations = await self.retrieve_relevant_knowledge(
            query=search_query,
            top_k=top_k,
            score_threshold=score_threshold,
        )

        retrieval_time = time.time() - start_time
        logger.info(
            f"[Conversation RAG] Completed in {retrieval_time:.3f}s - "
            f"{len(citations)} citations, enhanced={enhanced_query.enhancement_applied}"
        )

        return context_string, citations, intent_result, enhanced_query

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

            # Check if query is about documentation
            if not self.doc_searcher.is_documentation_query(query):
                logger.debug(
                    f"[Doc Search] Query not documentation-related: '{query[:50]}...'"
                )
                return "", []

            # Search documentation
            results = self.doc_searcher.search(
                query=query,
                n_results=n_results,
                score_threshold=score_threshold,
            )

            if not results:
                logger.debug(f"[Doc Search] No results for: '{query[:50]}...'")
                return "", []

            # Format as context
            context = self.doc_searcher.format_as_context(results)

            retrieval_time = time.time() - start_time
            logger.info(
                f"[Doc Search] Found {len(results)} documentation chunks "
                f"in {retrieval_time:.3f}s for: '{query[:50]}...'"
            )

            return context, results

        except Exception as e:
            logger.error(f"Documentation retrieval failed: {e}")
            return "", []

    async def retrieve_combined_knowledge(
        self,
        query: str,
        top_k: int = 5,
        doc_results: int = 3,
        score_threshold: float = 0.7,
        doc_threshold: float = 0.6,
    ) -> Tuple[str, List[Dict], List[Dict[str, Any]]]:
        """
        Retrieve combined knowledge from RAG and documentation sources.

        Issue #250: Combines general knowledge retrieval with documentation
        search for comprehensive context.

        Args:
            query: User's chat message/query
            top_k: Maximum knowledge facts from RAG
            doc_results: Maximum documentation chunks
            score_threshold: Minimum RAG relevance score
            doc_threshold: Minimum documentation relevance score

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
