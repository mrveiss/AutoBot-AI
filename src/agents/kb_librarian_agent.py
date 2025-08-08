"""Knowledge Base Librarian Agent.

This agent automatically searches the knowledge base whenever a question is asked,
acting like a helpful librarian that finds relevant information before answering.
"""

import logging
from typing import Dict, List, Any
from src.knowledge_base import KnowledgeBase
from src.llm_interface import LLMInterface
from src.config import Config

logger = logging.getLogger(__name__)


class KBLibrarianAgent:
    """A librarian agent that searches knowledge base for relevant information."""

    def __init__(self):
        """Initialize the KB Librarian Agent."""
        self.config = Config()
        self.knowledge_base = KnowledgeBase()
        self.llm = LLMInterface()
        self.enabled = self.config.get("kb_librarian.enabled", True)
        self.similarity_threshold = self.config.get(
            "kb_librarian.similarity_threshold", 0.7
        )
        self.max_results = self.config.get("kb_librarian.max_results", 5)
        self.auto_summarize = self.config.get("kb_librarian.auto_summarize", True)

    def detect_question(self, text: str) -> bool:
        """Detect if the text contains a question.

        Args:
            text: The input text to analyze

        Returns:
            True if the text appears to be a question
        """
        # Simple heuristic for question detection
        question_indicators = [
            "?",
            "what ",
            "when ",
            "where ",
            "who ",
            "why ",
            "how ",
            "which ",
            "can ",
            "could ",
            "would ",
            "should ",
            "is ",
            "are ",
            "do ",
            "does ",
            "did ",
            "will ",
            "has ",
            "have ",
            "tell me",
            "explain",
            "describe",
            "find ",
            "search ",
        ]

        text_lower = text.lower().strip()
        return any(indicator in text_lower for indicator in question_indicators)

    async def search_knowledge_base(self, query: str) -> List[Dict[str, Any]]:
        """Search the knowledge base for relevant information.

        Args:
            query: The search query

        Returns:
            List of relevant documents from the knowledge base
        """
        try:
            # Search for relevant documents
            results = self.knowledge_base.search(
                query,
                limit=self.max_results,
                similarity_threshold=self.similarity_threshold,
            )

            logger.info(
                f"KB Librarian found {len(results)} relevant documents "
                f"for query: {query}"
            )
            return results

        except Exception as e:
            logger.error(f"Error searching knowledge base: {e}")
            return []

    async def summarize_findings(
        self, query: str, documents: List[Dict[str, Any]]
    ) -> str:
        """Summarize the findings from the knowledge base.

        Args:
            query: The original query
            documents: List of found documents

        Returns:
            A summarized response based on the findings
        """
        if not documents:
            return "No relevant information found in the knowledge base."

        # Prepare context from documents
        context_parts = []
        for i, doc in enumerate(documents, 1):
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            source = metadata.get("source", "Unknown")
            context_parts.append(f"Document {i} (Source: {source}):\n{content}\n")

        context = "\n---\n".join(context_parts)

        # Create a prompt for summarization
        prompt = (
            f"As a helpful librarian, I found the following information in our "
            f'knowledge base related to the question: "{query}"\n\n'
            f"{context}\n\n"
            f"Please provide a concise and helpful summary of the relevant "
            f"information found."
        )

        try:
            response = await self.llm.chat([{"role": "system", "content": prompt}])
            return response

        except Exception as e:
            logger.error(f"Error summarizing findings: {e}")
            return "Found relevant documents but couldn't generate summary."

    async def process_query(self, query: str) -> Dict[str, Any]:
        """Process a query by searching the knowledge base.

        Args:
            query: The user's query

        Returns:
            Dictionary containing search results and optional summary
        """
        if not self.enabled:
            return {"enabled": False, "message": "KB Librarian is disabled"}

        # Check if this is a question
        is_question = self.detect_question(query)

        if not is_question:
            return {
                "enabled": True,
                "is_question": False,
                "message": "Not detected as a question",
            }

        # Search the knowledge base
        documents = await self.search_knowledge_base(query)

        result = {
            "enabled": True,
            "is_question": True,
            "query": query,
            "documents_found": len(documents),
            "documents": documents,
        }

        # Optionally summarize findings
        if self.auto_summarize and documents:
            summary = await self.summarize_findings(query, documents)
            result["summary"] = summary

        return result

    async def enhance_chat_response(
        self, user_message: str, chat_response: str
    ) -> Dict[str, Any]:
        """Enhance a chat response with knowledge base information.

        Args:
            user_message: The original user message
            chat_response: The initial chat response

        Returns:
            Enhanced response with KB information
        """
        # Process the query
        kb_result = await self.process_query(user_message)

        enhanced_response = {
            "original_response": chat_response,
            "kb_search_performed": kb_result.get("is_question", False),
        }

        if kb_result.get("documents_found", 0) > 0:
            enhanced_response["kb_documents"] = kb_result["documents"]
            if "summary" in kb_result:
                # Prepend KB findings to the response
                enhanced_response["enhanced_response"] = (
                    f"📚 **Knowledge Base Findings:**\n{kb_result['summary']}\n\n"
                    f"**Response:**\n{chat_response}"
                )
            else:
                enhanced_response["enhanced_response"] = chat_response
        else:
            enhanced_response["enhanced_response"] = chat_response

        return enhanced_response


# Singleton instance
_kb_librarian = None


def get_kb_librarian() -> KBLibrarianAgent:
    """Get the singleton KB Librarian Agent instance.

    Returns:
        The KB Librarian Agent instance
    """
    global _kb_librarian
    if _kb_librarian is None:
        _kb_librarian = KBLibrarianAgent()
    return _kb_librarian
