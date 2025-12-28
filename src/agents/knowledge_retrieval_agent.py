# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Retrieval Agent - Fast fact lookup and simple knowledge queries.

Uses lightweight Llama 3.2 1B model for efficient knowledge base searches,
simple fact retrieval, and quick question answering without complex synthesis.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from src.config.ssot_config import (
    AgentConfigurationError,
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)
from src.constants.threshold_constants import LLMDefaults
from src.knowledge_base import KnowledgeBase
from src.llm_interface import LLMInterface

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuples for knowledge retrieval patterns
_KNOWLEDGE_PATTERNS = (
    "what is",
    "who is",
    "when did",
    "where is",
    "how much",
    "tell me about",
    "find information",
    "look up",
    "search for",
    "do you know",
    "can you find",
    "what do you know about",
    "fact",
    "information",
    "details",
    "definition",
    "meaning",
)
_QUICK_LOOKUP_PATTERNS = ("quick", "fast", "briefly", "simple", "basic", "just tell me")


class KnowledgeRetrievalAgent:
    """Fast knowledge retrieval agent for simple facts and quick lookups."""

    # Agent identifier for SSOT config lookup
    AGENT_ID = "knowledge_retrieval"

    def __init__(self):
        """Initialize the Knowledge Retrieval Agent with explicit LLM configuration."""
        self.llm_interface = LLMInterface()

        # Use explicit SSOT config - raises AgentConfigurationError if not set
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)

        self.agent_type = "knowledge_retrieval"
        self.knowledge_base = None

        # Initialize knowledge base (lazy loading)
        self._kb_initialized = False

        logger.info(
            "Knowledge Retrieval Agent initialized with provider=%s, endpoint=%s, model=%s",
            self.llm_provider, self.llm_endpoint, self.model_name
        )

    async def _ensure_kb_initialized(self):
        """Ensure knowledge base is initialized (lazy loading)."""
        if not self._kb_initialized:
            try:
                self.knowledge_base = KnowledgeBase()
                await self.knowledge_base.ainit()
                self._kb_initialized = True
                logger.info("Knowledge base initialized successfully")
            except Exception as e:
                logger.error("Failed to initialize knowledge base: %s", e)
                self.knowledge_base = None

    def _build_kb_unavailable_response(self) -> Dict[str, Any]:
        """
        Build response when knowledge base is unavailable.

        (Issue #398: extracted helper)
        """
        return {
            "status": "error",
            "message": "Knowledge base not available",
            "documents_found": 0,
            "documents": [],
            "agent_type": "knowledge_retrieval",
        }

    def _build_success_response(
        self,
        query: str,
        processed_results: Dict[str, Any],
        summary: str,
        processing_time: float,
        similarity_threshold: float,
    ) -> Dict[str, Any]:
        """
        Build successful query response.

        (Issue #398: extracted helper)
        """
        return {
            "status": "success",
            "query": query,
            "documents_found": processed_results["documents_found"],
            "documents": processed_results["documents"],
            "summary": summary,
            "processing_time": processing_time,
            "is_question": self._is_question(query),
            "agent_type": "knowledge_retrieval",
            "model_used": self.model_name,
            "metadata": {
                "agent": "KnowledgeRetrievalAgent",
                "search_type": "fast_lookup",
                "similarity_threshold": similarity_threshold,
            },
        }

    def _build_error_response(self, query: str, error: Exception) -> Dict[str, Any]:
        """
        Build error response for query failures.

        (Issue #398: extracted helper)
        """
        return {
            "status": "error",
            "message": f"Knowledge retrieval failed: {str(error)}",
            "documents_found": 0,
            "documents": [],
            "query": query,
            "agent_type": "knowledge_retrieval",
            "model_used": self.model_name,
        }

    async def process_query(
        self,
        query: str,
        limit: int = 5,
        similarity_threshold: float = 0.6,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Process a simple knowledge query and return quick results.

        (Issue #398: refactored to use extracted helpers)

        Args:
            query: User's question or search query
            limit: Maximum number of results to return
            similarity_threshold: Minimum similarity score for results
            context: Optional context information

        Returns:
            Dict containing search results and metadata
        """
        try:
            logger.info("Knowledge Retrieval Agent processing query: %s...", query[:50])
            start_time = time.time()

            await self._ensure_kb_initialized()

            if not self.knowledge_base:
                return self._build_kb_unavailable_response()

            search_results = await self.knowledge_base.search(query, n_results=limit)
            processing_time = time.time() - start_time

            processed_results = self._process_search_results(
                search_results, similarity_threshold, query
            )

            summary = ""
            if processed_results["documents"]:
                summary = await self._generate_quick_summary(
                    query, processed_results["documents"][:3]
                )

            return self._build_success_response(
                query, processed_results, summary, processing_time, similarity_threshold
            )

        except Exception as e:
            logger.error("Knowledge Retrieval Agent error: %s", e)
            return self._build_error_response(query, e)

    async def find_similar_documents(
        self, query: str, top_k: int = 10, min_score: float = 0.5
    ) -> Dict[str, Any]:
        """
        Find documents similar to the query without LLM processing.

        Args:
            query: Search query
            top_k: Maximum number of results
            min_score: Minimum similarity score

        Returns:
            Dict containing similar documents
        """
        try:
            await self._ensure_kb_initialized()

            if not self.knowledge_base:
                return {"status": "error", "documents": []}

            # Direct vector search without LLM processing
            results = await self.knowledge_base.search(query, n_results=top_k)

            # Filter by minimum score if vector scores are available
            filtered_docs = []
            for doc in results:
                # Note: Actual similarity score depends on KB implementation
                filtered_docs.append(doc)

            return {
                "status": "success",
                "query": query,
                "documents": filtered_docs[:top_k],
                "count": len(filtered_docs[:top_k]),
                "agent_type": "knowledge_retrieval",
            }

        except Exception as e:
            logger.error("Similar document search error: %s", e)
            return {"status": "error", "documents": [], "error": str(e)}

    async def quick_fact_lookup(
        self, fact_query: str, max_docs: int = 3
    ) -> Dict[str, Any]:
        """
        Quick fact lookup optimized for specific factual questions.

        Args:
            fact_query: Specific factual question
            max_docs: Maximum documents to consider

        Returns:
            Dict containing fact or indication if not found
        """
        try:
            logger.info("Quick fact lookup: %s...", fact_query[:50])

            # Search for relevant documents
            search_result = await self.process_query(
                fact_query,
                limit=max_docs,
                similarity_threshold=0.7,  # Higher threshold for facts
            )

            if search_result["documents_found"] == 0:
                return {
                    "status": "not_found",
                    "message": "No relevant information found in knowledge base",
                    "fact_query": fact_query,
                    "agent_type": "knowledge_retrieval",
                }

            # Use lightweight LLM to extract specific fact
            fact_response = await self._extract_fact_from_documents(
                fact_query, search_result["documents"]
            )

            return {
                "status": "success",
                "fact_query": fact_query,
                "fact_response": fact_response,
                "source_documents": len(search_result["documents"]),
                "agent_type": "knowledge_retrieval",
            }

        except Exception as e:
            logger.error("Quick fact lookup error: %s", e)
            return {
                "status": "error",
                "message": str(e),
                "fact_query": fact_query,
                "agent_type": "knowledge_retrieval",
            }

    def _process_search_results(
        self, raw_results: List[Dict[str, Any]], similarity_threshold: float, query: str
    ) -> Dict[str, Any]:
        """Process and filter search results based on relevance."""
        processed_docs = []

        for i, result in enumerate(raw_results):
            # Basic relevance scoring (simplified)
            content = result.get("content", "").lower()
            query_words = query.lower().split()

            # Simple word matching score
            matches = sum(1 for word in query_words if word in content)
            relevance_score = matches / len(query_words) if query_words else 0

            if relevance_score >= (similarity_threshold - 0.2):  # Slightly more lenient
                processed_doc = {
                    "content": result.get("content", ""),
                    "metadata": result.get("metadata", {}),
                    "relevance_score": relevance_score,
                    "rank": i + 1,
                }
                processed_docs.append(processed_doc)

        # Sort by relevance score
        processed_docs.sort(key=lambda x: x["relevance_score"], reverse=True)

        return {"documents_found": len(processed_docs), "documents": processed_docs}

    async def _generate_quick_summary(
        self, query: str, documents: List[Dict[str, Any]]
    ) -> str:
        """Generate a quick summary using the lightweight model."""
        try:
            if not documents:
                return "No relevant information found."

            # Prepare context from documents
            context_parts = []
            for doc in documents[:3]:  # Limit to top 3 for speed
                content = doc.get("content", "")
                if len(content) > 200:  # Truncate for speed
                    content = content[:200] + "..."
                context_parts.append(content)

            context_text = "\n\n".join(context_parts)

            # Simple prompt for quick summarization
            system_prompt = """You are a fast fact retrieval assistant. Provide a brief, direct answer based on the provided context.

Guidelines:
- Be concise and factual
- Answer directly without unnecessary elaboration
- If the context doesn't contain the answer, say so clearly
- Keep responses under 100 words"""

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Context:\n{context_text}\n\nQuestion: {query}\n\nProvide a brief answer:"
                    ),
                },
            ]

            # Use knowledge retrieval model for quick response
            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="knowledge_retrieval",
                temperature=0.3,  # Low temperature for factual responses
                max_tokens=LLMDefaults.RETRIEVAL_MAX_TOKENS,
                top_p=0.8,
            )

            # Extract response content
            summary = self._extract_response_content(response)

            # Ensure summary is concise
            if len(summary) > 300:
                summary = summary[:300] + "..."

            return summary

        except Exception as e:
            logger.error("Quick summary generation error: %s", e)
            return f"Found {len(documents)} relevant documents but couldn't generate summary."

    async def _extract_fact_from_documents(
        self, fact_query: str, documents: List[Dict[str, Any]]
    ) -> str:
        """Extract specific fact using lightweight LLM."""
        try:
            if not documents:
                return "No information found."

            # Issue #383: Use list + join for document content combination
            content_parts = []
            total_len = 0
            for doc in documents[:2]:  # Limit for speed
                content = doc.get("content", "")
                if total_len + len(content) < 800:  # Total limit for speed
                    content_parts.append(content)
                    total_len += len(content)
            combined_content = "\n\n".join(content_parts)

            system_prompt = """Extract the specific fact requested. Be direct and concise.
If the information is not in the provided text, respond with "Information not found"."""

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Text: {combined_content}\n\nExtract: {fact_query}",
                },
            ]

            response = await self.llm_interface.chat_completion(
                messages=messages,
                llm_type="knowledge_retrieval",
                temperature=0.2,
                max_tokens=LLMDefaults.DEFAULT_MAX_TOKENS,
                top_p=0.7,
            )

            return self._extract_response_content(response)

        except Exception as e:
            logger.error("Fact extraction error: %s", e)
            return "Could not extract fact from documents."

    def _try_extract_message_content(self, response: Dict) -> Optional[str]:
        """Try to extract content from message dict (Issue #334 - extracted helper)."""
        if "message" not in response or not isinstance(response["message"], dict):
            return None
        content = response["message"].get("content")
        return content.strip() if content else None

    def _try_extract_choices_content(self, response: Dict) -> Optional[str]:
        """Try to extract content from choices list (Issue #334 - extracted helper)."""
        if "choices" not in response or not isinstance(response["choices"], list):
            return None
        if not response["choices"]:
            return None
        choice = response["choices"][0]
        if "message" not in choice or "content" not in choice["message"]:
            return None
        return choice["message"]["content"].strip()

    def _extract_response_content(self, response: Any) -> str:
        """Extract text content from LLM response."""
        try:
            if isinstance(response, dict):
                content = self._try_extract_message_content(response)
                if content:
                    return content
                content = self._try_extract_choices_content(response)
                if content:
                    return content
                if "content" in response:
                    return response["content"].strip()

            if isinstance(response, str):
                return response.strip()

            return str(response)

        except Exception as e:
            logger.error("Error extracting response content: %s", e)
            return "Error processing response"

    def _is_question(self, text: str) -> bool:
        """Determine if the text is a question."""
        question_indicators = [
            "?",
            "what",
            "how",
            "why",
            "when",
            "where",
            "who",
            "which",
            "can you",
            "could you",
            "would you",
            "do you",
            "is there",
            "are there",
            "tell me",
            "explain",
            "describe",
        ]

        text_lower = text.lower()
        return any(indicator in text_lower for indicator in question_indicators)

    def is_knowledge_retrieval_appropriate(self, message: str) -> bool:
        """
        Determine if a message is appropriate for knowledge retrieval agent.

        Args:
            message: The user's message

        Returns:
            bool: True if knowledge retrieval agent should handle it
        """
        # Issue #380: Use module-level constants for pattern matching
        message_lower = message.lower()

        # Strong indicators for knowledge retrieval
        if any(pattern in message_lower for pattern in _KNOWLEDGE_PATTERNS):
            return True

        # Questions that seem factual
        if self._is_question(message) and len(message.split()) <= 15:
            return True

        # Quick lookup requests
        if any(pattern in message_lower for pattern in _QUICK_LOOKUP_PATTERNS):
            return True

        return False


# Singleton instance (thread-safe)
import threading

_knowledge_retrieval_agent_instance = None
_knowledge_retrieval_agent_lock = threading.Lock()


def get_knowledge_retrieval_agent() -> KnowledgeRetrievalAgent:
    """Get the singleton Knowledge Retrieval Agent instance (thread-safe)."""
    global _knowledge_retrieval_agent_instance
    if _knowledge_retrieval_agent_instance is None:
        with _knowledge_retrieval_agent_lock:
            # Double-check after acquiring lock
            if _knowledge_retrieval_agent_instance is None:
                _knowledge_retrieval_agent_instance = KnowledgeRetrievalAgent()
    return _knowledge_retrieval_agent_instance
