# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Knowledge Base Librarian Agent.

This agent automatically searches the knowledge base whenever a question is asked,
acting like a helpful librarian that finds relevant information before answering.
"""

import asyncio
import logging
from typing import Any, Dict, List

from config import config
from autobot_shared.ssot_config import (
    get_agent_endpoint_explicit,
    get_agent_model_explicit,
    get_agent_provider_explicit,
)
from backend.constants.path_constants import PATH
from knowledge_base import KnowledgeBase
from llm_interface import LLMInterface

logger = logging.getLogger(__name__)


class KBLibrarianAgent:
    """A librarian agent that searches knowledge base for relevant information."""

    # Agent identifier for SSOT config lookup
    AGENT_ID = "kb_librarian"

    def __init__(self):
        """Initialize KB librarian agent with explicit LLM configuration."""
        self.knowledge_base = KnowledgeBase()
        self.llm = LLMInterface()

        # Use explicit SSOT config - raises AgentConfigurationError if not set
        self.llm_provider = get_agent_provider_explicit(self.AGENT_ID)
        self.llm_endpoint = get_agent_endpoint_explicit(self.AGENT_ID)
        self.model_name = get_agent_model_explicit(self.AGENT_ID)

        self.auto_learning_enabled = config.get(
            "agents.kb_librarian.auto_learning_enabled", True
        )

        logger.info(
            "KB Librarian Agent initialized with provider=%s, endpoint=%s, model=%s",
            self.llm_provider,
            self.llm_endpoint,
            self.model_name,
        )

        if self.auto_learning_enabled:
            logger.info("AUTO-LEARNING: Knowledge Base auto-learning is enabled")

    async def search_knowledge(
        self, query: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search the knowledge base for relevant information."""
        try:
            logger.debug("KB-LIBRARIAN: Searching for '%s'", query)
            results = await self.knowledge_base.search(query, limit=limit)

            if results:
                logger.info(
                    "KB-LIBRARIAN: Found %s results for '%s'", len(results), query
                )
                # Return formatted results with sources
                formatted_results = []
                for result in results:
                    formatted_results.append(
                        {
                            "content": result.get("content", ""),
                            "source": (
                                result.get("metadata", {}).get("source", "Unknown")
                            ),
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
            context_parts.append(
                f"Source: {result['source']}\n" f"Content: {result['content']}\n"
            )

        return "\n---\n".join(context_parts)

    async def answer_question(
        self, question: str, context_limit: int = 3
    ) -> Dict[str, Any]:
        """Answer a question using knowledge base context."""
        # Search for relevant knowledge
        kb_results = await self.search_knowledge(question, limit=context_limit)

        # Build context using list + join (O(n)) instead of += (O(n²))
        if kb_results:
            result_lines = [
                f"- {result['content']} (Source: {result['source']})"
                for result in kb_results
            ]
            context = (
                "Based on the following information from the knowledge base:\n\n"
                + "\n".join(result_lines)
            )
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
            response = await self.llm.generate_response(prompt)
            return {
                "answer": response,
                "knowledge_base_results": kb_results,
                "sources": [result["source"] for result in kb_results],
            }
        except Exception as e:
            logger.error("KB-LIBRARIAN: LLM error: %s", e)
            return {
                "answer": (
                    "I'm sorry, I encountered an error while generating a response."
                ),
                "knowledge_base_results": kb_results,
                "sources": [result["source"] for result in kb_results],
                "error": str(e),
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
            return {"error": str(e)}

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


# Global instance for API access (thread-safe)
import threading

_kb_librarian_instance = None
_kb_librarian_lock = threading.Lock()


def get_kb_librarian() -> KBLibrarianAgent:
    """Get or create the KB Librarian Agent instance (thread-safe)."""
    global _kb_librarian_instance
    if _kb_librarian_instance is None:
        with _kb_librarian_lock:
            # Double-check after acquiring lock
            if _kb_librarian_instance is None:
                _kb_librarian_instance = KBLibrarianAgent()
                logger.info("KB-LIBRARIAN: Created new instance")
    return _kb_librarian_instance
