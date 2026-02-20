# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AI Stack Client - Communication layer for AI Stack VM agents integration.

This module provides a centralized interface for communicating with the AI Stack VM
(see NetworkConstants.AI_STACK_VM_IP), enabling seamless integration of advanced AI agents.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin

import aiohttp

from autobot_shared.http_client import get_http_client
from backend.constants.network_constants import NetworkConstants
from backend.type_defs.common import Metadata

logger = logging.getLogger(__name__)


class AIStackError(Exception):
    """Base exception for AI Stack communication errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        details: Optional[Dict] = None,
    ):
        """Initialize AI Stack error with message, status code, and details."""
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


async def _process_ai_stack_response(
    response, url: str, attempt: int, retry_attempts: int
) -> tuple:
    """Process AI Stack HTTP response (Issue #315: extracted).

    Returns:
        Tuple of (result_data, should_retry, error_or_none)
        - result_data: Response data if successful, None otherwise
        - should_retry: True if should retry on server error
        - error_or_none: AIStackError if request failed, None if successful
    """
    response_text = await response.text()

    if response.status >= 400:
        logger.error("AI Stack error %s: %s", response.status, response_text)

        if response.status >= 500 and attempt < retry_attempts - 1:
            return None, True, None  # Retry on server errors

        return (
            None,
            False,
            AIStackError(
                f"AI Stack request failed: {response.status}",
                status_code=response.status,
                details={"response": response_text, "url": url},
            ),
        )

    try:
        return await response.json(), False, None
    except json.JSONDecodeError:
        return {"content": response_text}, False, None


class AIStackClient:
    """
    Client for communicating with AI Stack VM agents.

    Provides centralized communication with all AI agents running on
    the AI Stack VM.
    """

    RETRY_INTERVAL_SECONDS = 60

    def __init__(self, base_url: Optional[str] = None):
        """Initialize AI Stack client with base URL and HTTP client configuration."""
        # Connection status: "unknown" -> "connected" | "error"
        self.connection_status: str = "unknown"
        self._retry_task: Optional[asyncio.Task] = None

        # Use NetworkConstants for AI Stack configuration
        ai_stack_config = {
            "host": str(NetworkConstants.AI_STACK_HOST),
            "port": NetworkConstants.AI_STACK_PORT,
            "timeout": 60,
            "retry_attempts": 3,
            "retry_delay": 1.0,
        }

        # Get base_url from configuration if not provided
        if base_url is None:
            host = ai_stack_config.get("host")
            port = ai_stack_config.get("port")
            if not host or not port:
                raise ValueError("AI Stack configuration missing 'host' or 'port'")
            base_url = f"http://{host}:{port}"
        self.base_url = base_url.rstrip("/")
        self.http_client = get_http_client()

        # Get timeout, retry, and connection configuration from config
        timeout_seconds = ai_stack_config.get("timeout", 60)
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.retry_attempts = ai_stack_config.get("retry_attempts", 3)
        self.retry_delay = ai_stack_config.get("retry_delay", 1.0)

        # Agent endpoint mappings — AI Stack API uses /agents/{type}/process
        self.agent_endpoints = {
            "rag": "/agents/rag/process",
            "chat": "/agents/chat/process",
            "kb_librarian": "/agents/kb_librarian/process",
            "knowledge_extraction": "/agents/knowledge_extraction/process",
            "knowledge_retrieval": "/agents/knowledge_retrieval/process",
            "enhanced_kb_librarian": "/agents/enhanced_kb_librarian/process",
            "system_knowledge_manager": "/agents/system_knowledge_manager/process",
            "research": "/agents/research/process",
            "web_research_assistant": "/agents/web_research_assistant/process",
            "npu_code_search": "/agents/npu_code_search/process",
            "development_speedup": "/agents/development_speedup/process",
            "classification": "/agents/classification/process",
        }

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def connect(self):
        """Initialize HTTP session and verify AI Stack reachability."""
        logger.info("AI Stack client connecting to %s", self.base_url)
        check = await self.health_check()
        if check["status"] != "healthy":
            logger.warning(
                "AI Stack at %s is not reachable — will retry every %ds",
                self.base_url,
                self.RETRY_INTERVAL_SECONDS,
            )

    async def close(self):
        """Close the HTTP session and stop retry loop."""
        self.stop_retry_loop()
        logger.info("AI Stack client session closed")

    def start_retry_loop(self) -> None:
        """Start background task that retries AI Stack health every 60s."""
        if self._retry_task and not self._retry_task.done():
            return  # Already running
        self._retry_task = asyncio.create_task(self._retry_health_loop())

    def stop_retry_loop(self) -> None:
        """Cancel the background retry task."""
        if self._retry_task and not self._retry_task.done():
            self._retry_task.cancel()
            self._retry_task = None

    async def _retry_health_loop(self) -> None:
        """Periodically check AI Stack health and update status."""
        while True:
            await asyncio.sleep(self.RETRY_INTERVAL_SECONDS)
            try:
                result = await self.health_check()
                if result["status"] == "healthy":
                    logger.info(
                        "AI Stack API now reachable at %s",
                        self.base_url,
                    )
                    return  # Stop retrying once connected
            except Exception:
                pass  # health_check already sets connection_status

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Metadata] = None,
        params: Optional[Metadata] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Metadata:
        """
        Make HTTP request to AI Stack with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request body data
            params: URL parameters
            headers: Additional headers

        Returns:
            Response data as dictionary

        Raises:
            AIStackError: If request fails after retries
        """
        url = urljoin(self.base_url, endpoint)
        request_headers = headers or {}

        for attempt in range(self.retry_attempts):
            try:
                logger.debug(
                    f"AI Stack request: {method} {url} (attempt {attempt + 1})"
                )

                async with await self.http_client.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    headers=request_headers,
                    timeout=self.timeout,
                ) as response:
                    # Use helper to process response (Issue #315: reduced nesting)
                    result, should_retry, error = await _process_ai_stack_response(
                        response, url, attempt, self.retry_attempts
                    )
                    if should_retry:
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
                        continue
                    if error:
                        raise error
                    return result

            except aiohttp.ClientError as e:
                logger.error("AI Stack client error (attempt %s): %s", attempt + 1, e)
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue

                raise AIStackError(
                    f"Failed to connect to AI Stack: {str(e)}",
                    details={"error": str(e), "url": url},
                )
            except Exception as e:
                logger.error("Unexpected error in AI Stack request: %s", e)
                raise AIStackError(
                    f"Unexpected error: {str(e)}", details={"error": str(e), "url": url}
                )

        raise AIStackError("All retry attempts failed")

    async def _agent_request(
        self, agent_type: str, action: str, payload: Metadata
    ) -> Metadata:
        """Send a properly-formatted AgentRequest to an agent endpoint."""
        endpoint = self.agent_endpoints.get(agent_type)
        if not endpoint:
            raise AIStackError(f"Unknown agent type: {agent_type}")
        request_body = {
            "request_id": str(uuid.uuid4()),
            "agent_type": agent_type,
            "action": action,
            "payload": payload,
        }
        return await self._make_request("POST", endpoint, data=request_body)

    async def health_check(self) -> Metadata:
        """Check AI Stack health status and update connection_status."""
        try:
            response = await self._make_request("GET", "/health")
            if self.connection_status != "connected":
                logger.info("AI Stack connection restored at %s", self.base_url)
            self.connection_status = "connected"
            return {
                "status": "healthy",
                "ai_stack_response": response,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except AIStackError as e:
            prev = self.connection_status
            self.connection_status = "error"
            if prev != "error":
                logger.warning(
                    "AI Stack unreachable at %s: %s — starting retry loop",
                    self.base_url,
                    e.message,
                )
                self.start_retry_loop()
            return {
                "status": "unhealthy",
                "error": e.message,
                "timestamp": datetime.utcnow().isoformat(),
            }

    async def list_available_agents(self) -> Metadata:
        """Get list of available AI agents."""
        try:
            response = await self._make_request("GET", "/agents")
            return response
        except AIStackError as e:
            logger.warning("Cannot list AI Stack agents: %s", e.message)
            # Fallback: return configured agents
            return {
                "agents": list(self.agent_endpoints.keys()),
                "total": len(self.agent_endpoints),
                "source": "fallback_config",
            }

    # ====================================================================
    # RAG Agent Integration
    # ====================================================================

    async def rag_query(
        self,
        query: str,
        documents: Optional[List[Dict]] = None,
        context: Optional[str] = None,
        max_results: int = 10,
    ) -> Metadata:
        """
        Perform RAG query using advanced document synthesis.

        Args:
            query: Search query
            documents: Optional pre-retrieved documents
            context: Additional context for the query
            max_results: Maximum number of results to return

        Returns:
            RAG response with synthesized answer and sources
        """
        payload = {"query": query, "max_results": max_results}
        if documents:
            payload["documents"] = documents
        if context:
            payload["context"] = context

        return await self._agent_request("rag", "document_query", payload)

    async def reformulate_query(
        self, query: str, context: Optional[str] = None
    ) -> Metadata:
        """
        Reformulate query for better retrieval results.

        Args:
            query: Original query
            context: Additional context

        Returns:
            Reformulated query suggestions
        """
        payload = {"query": query}
        if context:
            payload["context"] = context

        return await self._agent_request("rag", "reformulate_query", payload)

    async def analyze_documents(self, documents: List[Dict]) -> Metadata:
        """
        Analyze and synthesize multiple documents.

        Args:
            documents: List of documents to analyze

        Returns:
            Document analysis and synthesis results
        """
        return await self._agent_request(
            "rag", "analyze_documents", {"documents": documents}
        )

    # ====================================================================
    # Chat Agent Integration
    # ====================================================================

    async def chat_message(
        self,
        message: str,
        context: Optional[str] = None,
        chat_history: Optional[List[Dict]] = None,
    ) -> Metadata:
        """
        Process chat message with intelligent conversation handling.

        Args:
            message: User message
            context: Conversation context
            chat_history: Previous chat messages

        Returns:
            Chat response
        """
        payload = {"message": message}
        if context:
            payload["context"] = context
        if chat_history:
            payload["chat_history"] = chat_history

        return await self._agent_request("chat", "chat", payload)

    # ====================================================================
    # Knowledge Base Librarian Integration
    # ====================================================================

    async def search_knowledge_enhanced(
        self, query: str, search_type: str = "comprehensive", max_results: int = 10
    ) -> Metadata:
        """
        Enhanced knowledge base search using KB Librarian.

        Args:
            query: Search query
            search_type: Type of search (comprehensive, precise, broad)
            max_results: Maximum results to return

        Returns:
            Enhanced search results with relevance ranking
        """
        payload = {
            "query": query,
            "search_type": search_type,
            "max_results": max_results,
        }

        return await self._agent_request(
            "enhanced_kb_librarian", "enhanced_search", payload
        )

    async def extract_knowledge(
        self,
        content: str,
        content_type: str = "text",
        extraction_mode: str = "comprehensive",
    ) -> Metadata:
        """
        Extract structured knowledge from content.

        Args:
            content: Content to extract knowledge from
            content_type: Type of content (text, document, url)
            extraction_mode: Extraction detail level

        Returns:
            Extracted knowledge structures
        """
        payload = {
            "content": content,
            "content_type": content_type,
            "extraction_mode": extraction_mode,
        }

        return await self._agent_request(
            "knowledge_extraction", "extract_knowledge", payload
        )

    async def retrieve_knowledge(
        self,
        query: str,
        knowledge_types: Optional[List[str]] = None,
        confidence_threshold: float = 0.7,
    ) -> Metadata:
        """
        Retrieve knowledge with advanced filtering.

        Args:
            query: Retrieval query
            knowledge_types: Types of knowledge to retrieve
            confidence_threshold: Minimum confidence score

        Returns:
            Retrieved knowledge with confidence scores
        """
        payload = {"query": query, "confidence_threshold": confidence_threshold}
        if knowledge_types:
            payload["knowledge_types"] = knowledge_types

        return await self._agent_request(
            "knowledge_retrieval", "retrieve_knowledge", payload
        )

    # ====================================================================
    # Research Agents Integration
    # ====================================================================

    async def research_query(
        self,
        query: str,
        research_depth: str = "comprehensive",
        sources: Optional[List[str]] = None,
    ) -> Metadata:
        """
        Perform comprehensive research query.

        Args:
            query: Research question
            research_depth: Depth of research (quick, standard, comprehensive)
            sources: Specific sources to search

        Returns:
            Research results with sources and analysis
        """
        payload = {"query": query, "research_depth": research_depth}
        if sources:
            payload["sources"] = sources

        return await self._agent_request("research", "research", payload)

    async def web_research(
        self, query: str, max_pages: int = 10, include_analysis: bool = True
    ) -> Metadata:
        """
        Perform web research with analysis.

        Args:
            query: Web research query
            max_pages: Maximum pages to analyze
            include_analysis: Whether to include content analysis

        Returns:
            Web research results with analysis
        """
        payload = {
            "query": query,
            "max_pages": max_pages,
            "include_analysis": include_analysis,
        }

        return await self._agent_request(
            "web_research_assistant", "web_research", payload
        )

    # ====================================================================
    # Development & Code Analysis Integration
    # ====================================================================

    async def search_code(
        self, query: str, search_scope: str = "codebase", include_npu: bool = True
    ) -> Metadata:
        """
        Search codebase using NPU acceleration.

        Args:
            query: Code search query
            search_scope: Scope of search (file, function, class, codebase)
            include_npu: Whether to use NPU acceleration

        Returns:
            Code search results with context
        """
        payload = {
            "query": query,
            "search_scope": search_scope,
            "include_npu": include_npu,
        }

        return await self._agent_request("npu_code_search", "search_code", payload)

    async def analyze_development_speedup(
        self, code_path: Optional[str] = None, analysis_type: str = "comprehensive"
    ) -> Metadata:
        """
        Analyze codebase for development speedup opportunities.

        Args:
            code_path: Specific path to analyze (optional)
            analysis_type: Type of analysis (quick, standard, comprehensive)

        Returns:
            Development speedup analysis with recommendations
        """
        payload = {"analysis_type": analysis_type}
        if code_path:
            payload["code_path"] = code_path

        return await self._agent_request(
            "development_speedup", "analyze_speedup", payload
        )

    # ====================================================================
    # Content Classification Integration
    # ====================================================================

    async def classify_content(
        self, content: str, classification_types: Optional[List[str]] = None
    ) -> Metadata:
        """
        Classify content using AI classification agent.

        Args:
            content: Content to classify
            classification_types: Specific classification types to apply

        Returns:
            Classification results with confidence scores
        """
        payload = {"content": content}
        if classification_types:
            payload["classification_types"] = classification_types

        return await self._agent_request("classification", "classify", payload)

    # ====================================================================
    # System Knowledge Management
    # ====================================================================

    async def get_system_knowledge(
        self, knowledge_category: Optional[str] = None
    ) -> Metadata:
        """
        Get system-wide knowledge insights.

        Args:
            knowledge_category: Specific category to retrieve

        Returns:
            System knowledge insights
        """
        payload = {}
        if knowledge_category:
            payload["knowledge_category"] = knowledge_category

        return await self._agent_request(
            "system_knowledge_manager", "get_system_knowledge", payload
        )

    async def update_system_knowledge(self, knowledge_update: Metadata) -> Metadata:
        """
        Update system-wide knowledge.

        Args:
            knowledge_update: Knowledge update payload

        Returns:
            Update confirmation
        """
        return await self._agent_request(
            "system_knowledge_manager",
            "update_system_knowledge",
            {"knowledge_update": knowledge_update},
        )


# Global AI Stack client instance with thread-safe initialization (Issue #662)
_ai_stack_client: Optional[AIStackClient] = None
_ai_stack_client_lock = asyncio.Lock()


async def get_ai_stack_client() -> AIStackClient:
    """Get or create global AI Stack client instance (thread-safe)."""
    global _ai_stack_client

    if _ai_stack_client is None:
        async with _ai_stack_client_lock:
            # Double-check after acquiring lock
            if _ai_stack_client is None:
                _ai_stack_client = AIStackClient()
                await _ai_stack_client.connect()

    return _ai_stack_client


async def close_ai_stack_client():
    """Close global AI Stack client."""
    global _ai_stack_client

    if _ai_stack_client:
        await _ai_stack_client.close()
        _ai_stack_client = None
