"""Knowledge Base Librarian Agent.

This agent automatically searches the knowledge base whenever a question is asked,
acting like a helpful librarian that finds relevant information before answering.
"""

import asyncio
import logging
from typing import Any, Dict, List

from src.unified_config_manager import config
from src.knowledge_base import KnowledgeBase
from src.llm_interface import LLMInterface
from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class KBLibrarianAgent:
    """A librarian agent that searches knowledge base for relevant information."""

    def __init__(self):
        self.knowledge_base = KnowledgeBase()
        self.llm = LLMInterface()
        self.auto_learning_enabled = config.get(
            "agents.kb_librarian.auto_learning_enabled", True
        )

        if self.auto_learning_enabled:
            logger.info("AUTO-LEARNING: Knowledge Base auto-learning is enabled")

    async def search_knowledge(
        self, query: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search the knowledge base for relevant information."""
        try:
            logger.debug(f"KB-LIBRARIAN: Searching for '{query}'")
            results = await self.knowledge_base.search(query, limit=limit)

            if results:
                logger.info(f"KB-LIBRARIAN: Found {len(results)} results for '{query}'")
                # Return formatted results with sources
                formatted_results = []
                for result in results:
                    formatted_results.append(
                        {
                            "content": result.get("content", ""),
                            "source": result.get("metadata", {}).get(
                                "source", "Unknown"
                            ),
                            "score": result.get("score", 0.0),
                            "metadata": result.get("metadata", {}),
                        }
                    )
                return formatted_results
            else:
                logger.info(f"KB-LIBRARIAN: No results found for '{query}'")
                return []

        except Exception as e:
            logger.error(f"KB-LIBRARIAN: Search error for '{query}': {e}")
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

        # Build context
        if kb_results:
            context = "Based on the following information from the knowledge base:\n\n"
            for result in kb_results:
                context += f"- {result['content']} (Source: {result['source']})\n"

            prompt = f"{context}\n\nQuestion: {question}\n\nAnswer:"
        else:
            # No knowledge base results - trigger auto-learning if enabled
            if self.auto_learning_enabled:
                await self._trigger_auto_learning(question)

            prompt = f"Question: {question}\n\nNote: No specific information was found in the knowledge base for this question.\n\nAnswer:"

        # Generate response using LLM
        try:
            response = await self.llm.generate_response(prompt)
            return {
                "answer": response,
                "knowledge_base_results": kb_results,
                "sources": [result["source"] for result in kb_results],
            }
        except Exception as e:
            logger.error(f"KB-LIBRARIAN: LLM error: {e}")
            return {
                "answer": "I'm sorry, I encountered an error while generating a response.",
                "knowledge_base_results": kb_results,
                "sources": [result["source"] for result in kb_results],
                "error": str(e),
            }

    async def _trigger_auto_learning(self, question: str):
        """Trigger auto-learning process for missing knowledge."""
        try:
            logger.info(f"AUTO-LEARNING: Triggered for question: {question}")

            # Try to find relevant documentation files
            import os

            docs_dirs = [
                "/home/kali/Desktop/AutoBot/docs",
                "/home/kali/Desktop/AutoBot",
                "/home/kali/Desktop/AutoBot/config",
                "/home/kali/Desktop/AutoBot/scripts",
            ]

            for docs_dir in docs_dirs:
                if os.path.exists(docs_dir):
                    for root, dirs, files in os.walk(docs_dir):
                        for file in files:
                            if file.endswith((".md", ".txt", ".py", ".yaml", ".yml")):
                                file_path = os.path.join(root, file)
                                await self._import_document(file_path)

            # Also try to populate knowledge base if it hasn't been done recently
            await self.knowledge_base.populate_knowledge_base()

        except Exception as e:
            logger.error(f"AUTO-LEARNING: Failed to trigger population: {e}")

    async def _import_document(self, file_path: str):
        """Import a single document into the knowledge base."""
        try:
            import os

            if not os.path.exists(file_path):
                return

            # CRITICAL FIX: Use asyncio.to_thread to prevent blocking the event loop
            async def _read_file_async(path: str) -> str:
                """Read file content asynchronously."""

                def _sync_read():
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
            logger.info(f"AUTO-LEARNING: Added {file_path} to knowledge base")

        except Exception as e:
            logger.error(f"AUTO-LEARNING: Failed to import {file_path}: {e}")

    async def get_knowledge_stats(self) -> Dict[str, Any]:
        """Get knowledge base statistics."""
        try:
            stats = await self.knowledge_base.get_stats()
            return stats
        except Exception as e:
            logger.error(f"KB-LIBRARIAN: Failed to get stats: {e}")
            return {"error": str(e)}

    async def add_new_knowledge(self, content: str, title: str, source: str = None):
        """Add new knowledge to the base."""
        try:
            if not source:
                source = f"Added by KB Librarian: {title}"

            await self.knowledge_base.add_text(content, title=title, source=source)
            logger.info(f"KB-LIBRARIAN: Added new knowledge: {title}")
        except Exception as e:
            logger.error(f"KB-LIBRARIAN: Failed to add knowledge '{title}': {e}")
            raise


# Global instance for API access
_kb_librarian_instance = None


def get_kb_librarian() -> KBLibrarianAgent:
    """Get or create the KB Librarian Agent instance."""
    global _kb_librarian_instance
    if _kb_librarian_instance is None:
        _kb_librarian_instance = KBLibrarianAgent()
        logger.info("KB-LIBRARIAN: Created new instance")
    return _kb_librarian_instance
