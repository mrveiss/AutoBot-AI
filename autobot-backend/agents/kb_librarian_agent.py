# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Knowledge Base Librarian Agent.

This agent automatically searches the knowledge base whenever a question is asked,
acting like a helpful librarian that finds relevant information before answering.
"""

import asyncio
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from autobot_shared.ssot_config import (
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)
from config import config
from constants.path_constants import PATH
from knowledge_base import KnowledgeBase
from services.llm_service import get_llm_service

from .base_agent import DeploymentMode
from .standardized_agent import ActionHandler, StandardizedAgent

logger = get_logger(__name__)


class KBLibrarianAgent(StandardizedAgent):
    """A librarian agent that searches knowledge base for relevant information."""

    # Agent identifier for SSOT config lookup
    AGENT_ID = "kb_librarian"

    def __init__(self):
        """Initialize KB librarian agent (#3387: migrated to StandardizedAgent)."""
        super().__init__("kb_librarian", DeploymentMode.LOCAL)
        self.knowledge_base = KnowledgeBase()
        self.llm = get_llm_service()

        # Use explicit SSOT config - raises AgentConfigurationError if not set
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)

        self.auto_learning_enabled = config.get("agents.kb_librarian.auto_learning_enabled", True)

        # Runtime-configurable parameters (used by api/kb_librarian.py overrides)
        self.enabled: bool = True
        self.max_results: int = config.get("agents.kb_librarian.max_results", 5)
        self.similarity_threshold: float = config.get("agents.kb_librarian.similarity_threshold", 0.6)
        self.auto_summarize: bool = config.get("agents.kb_librarian.auto_summarize", False)

        # Register action handlers for StandardizedAgent routing
        self.register_actions(
            {
                "search": ActionHandler(
                    handler_method="_handle_search",
                    required_params=["query"],
                    description="Search the knowledge base",
                ),
                "answer": ActionHandler(
                    handler_method="_handle_answer",
                    required_params=["question"],
                    description="Answer a question using knowledge base context",
                ),
                "add_knowledge": ActionHandler(
                    handler_method="_handle_add_knowledge",
                    required_params=["content", "title"],
                    description="Add new knowledge to the base",
                ),
                "get_stats": ActionHandler(
                    handler_method="_handle_get_stats",
                    required_params=[],
                    description="Get knowledge base statistics",
                ),
            }
        )

        logger.info(
            "KB Librarian Agent initialized with provider=%s, endpoint=%s, model=%s",
            self.llm_provider,
            self.llm_endpoint,
            self.model_name,
        )

        if self.auto_learning_enabled:
            logger.info("AUTO-LEARNING: Knowledge Base auto-learning is enabled")

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities (#3387)."""
        return ["search", "answer", "add_knowledge", "get_stats", "knowledge_base"]

    def _get_system_prompt(self) -> str:
        """Return agent system prompt."""
        return "You are a knowledge base librarian. " "Find and retrieve relevant information from the knowledge base."

    # Action handler wrappers for StandardizedAgent routing

    async def _handle_search(self, request) -> Dict[str, Any]:
        """Handle search action via StandardizedAgent routing."""
        query = request.payload["query"]
        limit = request.payload.get("limit", 5)
        results = await self.search_knowledge(query, limit=limit)
        return {"results": results, "count": len(results)}

    async def _handle_answer(self, request) -> Dict[str, Any]:
        """Handle answer action via StandardizedAgent routing."""
        question = request.payload["question"]
        context_limit = request.payload.get("context_limit", 3)
        return await self.answer_question(question, context_limit=context_limit)

    async def _handle_add_knowledge(self, request) -> Dict[str, Any]:
        """Handle add_knowledge action via StandardizedAgent routing."""
        content = request.payload["content"]
        title = request.payload["title"]
        source = request.payload.get("source")
        await self.add_new_knowledge(content, title, source=source)
        return {"status": "success", "title": title}

    async def _handle_get_stats(self, request) -> Dict[str, Any]:
        """Handle get_stats action via StandardizedAgent routing."""
        return await self.get_knowledge_stats()

    async def search_knowledge(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search the knowledge base for relevant information."""
        try:
            logger.debug("KB-LIBRARIAN: Searching for '%s'", query)
            results = await self.knowledge_base.search(query, limit=limit)

            if results:
                logger.info("KB-LIBRARIAN: Found %s results for '%s'", len(results), query)
                # Return formatted results with sources
                formatted_results = []
                for result in results:
                    formatted_results.append(
                        {
                            "content": result.get("content", ""),
                            "source": (result.get("metadata", {}).get("source", "Unknown")),
                            "score": result.get("score", 0.0),
                            "metadata": result.get("metadata", {}),
                        }
                    )
                return formatted_results
            else:
                logger.info("KB-LIBRARIAN: No results found for '%s'", query)
                return []

        except Exception as e:
            logger.error("KB-LIBRARIAN: Search error for '%s': %s", query, e)
            return []

    async def get_context_for_question(self, question: str) -> str:
        """Get relevant context from knowledge base for a question."""
        results = await self.search_knowledge(question, limit=3)

        if not results:
            return "No relevant information found in knowledge base."

        context_parts = []
        for result in results:
            context_parts.append(f"Source: {result['source']}\n" f"Content: {result['content']}\n")

        return "\n---\n".join(context_parts)

    def _is_question(self, query: str) -> bool:
        """Return True if the query looks like a natural-language question."""
        stripped = query.strip()
        return stripped.endswith("?") or stripped.lower().startswith(
            ("what", "who", "where", "when", "why", "how", "is", "are", "can", "does")
        )

    async def process_query(self, query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Process a KB query and return results compatible with KBQueryResponse.

        This is the primary entry-point used by api/kb_librarian.py,
        api/workflow.py, and agent_execution.py (#4531).

        Args:
            query: Natural-language query string.
            context: Optional context dict (currently unused, reserved for future use).

        Returns:
            Dict with keys: enabled, is_question, query, documents_found,
            documents, summary, response, knowledge_base_results, sources.
        """
        documents = await self.search_knowledge(query, limit=self.max_results)

        summary: str = ""
        if self.auto_summarize and documents:
            answer_result = await self.answer_question(query, context_limit=self.max_results)
            summary = answer_result.get("answer", "")

        return {
            "enabled": self.enabled,
            "is_question": self._is_question(query),
            "query": query,
            "documents_found": len(documents),
            "documents": documents,
            "summary": summary,
            # Aliases used by agent_execution.py and workflow.py
            "response": summary or (documents[0]["content"] if documents else ""),
            "knowledge_base_results": documents,
            "sources": [doc.get("source", "Unknown") for doc in documents],
        }

    async def answer_question(self, question: str, context_limit: int = 3) -> Dict[str, Any]:
        """Answer a question using knowledge base context."""
        # Search for relevant knowledge
        kb_results = await self.search_knowledge(question, limit=context_limit)

        # Build context using list + join (O(n)) instead of += (O(n²))
        if kb_results:
            result_lines = [f"- {result['content']} (Source: {result['source']})" for result in kb_results]
            context = "Based on the following information from the knowledge base:\n\n" + "\n".join(result_lines)
            prompt = f"{context}\n\nQuestion: {question}\n\nAnswer:"
        else:
            # No knowledge base results - trigger auto-learning if enabled
            if self.auto_learning_enabled:
                await self._trigger_auto_learning(question)

            prompt = (
                f"Question: {question}\n\nNote: No specific information was found in the knowledge base"
                f"for this question.\n\nAnswer:"
            )

        # Generate response using LLM
        try:
            llm_response = await self.llm.chat([{"role": "user", "content": prompt}])
            return {
                "answer": llm_response.content,
                "knowledge_base_results": kb_results,
                "sources": [result["source"] for result in kb_results],
            }
        except Exception as e:
            logger.error("KB-LIBRARIAN: LLM error: %s", e)
            return {
                "answer": ("I'm sorry, I encountered an error while generating a response."),
                "knowledge_base_results": kb_results,
                "sources": [result["source"] for result in kb_results],
                "error": "LLM response generation failed",
            }

    def _get_learning_extensions(self) -> tuple:
        """Get file extensions for auto-learning (Issue #334 - extracted helper)."""
        return (".md", ".txt", ".py", ".yaml", ".yml")

    async def _scan_directory_for_docs(self, docs_dir: str) -> None:
        """Scan directory for documents to import (Issue #334 - extracted helper)."""
        import os

        # Issue #358 - avoid blocking
        if not await asyncio.to_thread(os.path.exists, docs_dir):
            return

        extensions = self._get_learning_extensions()
        for root, dirs, files in os.walk(docs_dir):
            for file in files:
                if not file.endswith(extensions):
                    continue
                file_path = os.path.join(root, file)
                await self._import_document(file_path)

    async def _trigger_auto_learning(self, question: str):
        """Trigger auto-learning process for missing knowledge."""
        try:
            logger.info("AUTO-LEARNING: Triggered for question: %s", question)

            docs_dirs = [
                f"{PATH.PROJECT_ROOT}/docs",
                f"{PATH.PROJECT_ROOT}",
                f"{PATH.PROJECT_ROOT}/config",
                f"{PATH.PROJECT_ROOT}/scripts",
            ]

            for docs_dir in docs_dirs:
                await self._scan_directory_for_docs(docs_dir)

            await self.knowledge_base.populate_knowledge_base()

        except Exception as e:
            logger.error("AUTO-LEARNING: Failed to trigger population: %s", e)

    async def _import_document(self, file_path: str):
        """Import a single document into the knowledge base."""
        try:
            import os

            # Issue #358 - avoid blocking
            if not await asyncio.to_thread(os.path.exists, file_path):
                return

            # CRITICAL FIX: Use asyncio.to_thread to prevent blocking the event loop
            async def _read_file_async(path: str) -> str:
                """Read file content asynchronously."""

                def _sync_read():
                    """Synchronously read file content with UTF-8 encoding."""
                    with open(path, "r", encoding="utf-8") as f:
                        return f.read()

                return await asyncio.to_thread(_sync_read)

            # Read file content asynchronously
            content = await _read_file_async(file_path)

            # Add to knowledge base
            await self.knowledge_base.add_text(
                content,
                title=os.path.basename(file_path),
                source=f"AutoBot Documentation: {file_path}",
            )
            logger.info("AUTO-LEARNING: Added %s to knowledge base", file_path)

        except Exception as e:
            logger.error("AUTO-LEARNING: Failed to import %s: %s", file_path, e)

    async def get_knowledge_stats(self) -> Dict[str, Any]:
        """Get knowledge base statistics."""
        try:
            stats = await self.knowledge_base.get_stats()
            return stats
        except Exception as e:
            logger.error("KB-LIBRARIAN: Failed to get stats: %s", e)
            return {"error": "Failed to retrieve knowledge base stats"}

    async def add_new_knowledge(self, content: str, title: str, source: str = None):
        """Add new knowledge to the base."""
        try:
            if not source:
                source = f"Added by KB Librarian: {title}"

            await self.knowledge_base.add_text(content, title=title, source=source)
            logger.info("KB-LIBRARIAN: Added new knowledge: %s", title)
        except Exception as e:
            logger.error("KB-LIBRARIAN: Failed to add knowledge '%s': %s", title, e)
            raise


get_kb_librarian = lazy_singleton(KBLibrarianAgent)
