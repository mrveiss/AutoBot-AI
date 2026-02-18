# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Documentation Searcher

Issue #381: Extracted from chat_knowledge_service.py god class refactoring.
Contains DocumentationSearcher for AutoBot documentation search integration.
"""

import re
import threading
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_llm_logger
from autobot_shared.ssot_config import get_ollama_url
from backend.constants.path_constants import PATH

logger = get_llm_logger("doc_searcher")

# Issue #380: Use centralized PathConstants instead of repeated computation
PROJECT_ROOT = PATH.PROJECT_ROOT


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
            from utils.chromadb_client import get_chromadb_client

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
                    "DocumentationSearcher initialized: %d documents available",
                    doc_count,
                )
            except Exception:
                logger.warning(
                    "Documentation collection '%s' not found. "
                    "Run 'python tools/index_documentation.py --tier 1' to index docs.",
                    self.collection_name,
                )
                return False

            # Initialize embedding model
            self._embed_model = OllamaEmbedding(
                model_name="nomic-embed-text", base_url=get_ollama_url()
            )

            self._initialized = True
            return True

        except Exception as e:
            logger.error("Failed to initialize DocumentationSearcher: %s", e)
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

    def _query_chromadb(
        self, embedding: List[float], n_results: int
    ) -> Optional[Dict[str, Any]]:
        """Query ChromaDB collection with embedding.

        Args:
            embedding: Query embedding vector.
            n_results: Maximum number of results.

        Returns:
            ChromaDB query results or None if empty. Issue #620.
        """
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        if not results or not results.get("documents"):
            return None
        return results

    def _format_result_item(
        self, doc: str, meta: Dict[str, Any], distance: float
    ) -> Dict[str, Any]:
        """Format a single search result item.

        Args:
            doc: Document content.
            meta: Document metadata.
            distance: Distance score from embedding search.

        Returns:
            Formatted result dictionary. Issue #620.
        """
        score = 1 - distance  # Convert distance to similarity
        return {
            "content": doc,
            "score": round(score, 3),
            "file_path": meta.get("file_path", "unknown"),
            "section": meta.get("section", ""),
            "subsection": meta.get("subsection", ""),
            "doc_type": meta.get("doc_type", "documentation"),
            "priority": meta.get("priority", "medium"),
        }

    def search(
        self, query: str, n_results: int = 3, score_threshold: float = 0.6
    ) -> List[Dict[str, Any]]:
        """Search documentation for relevant content.

        Args:
            query: Search query
            n_results: Maximum number of results
            score_threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of search result dictionaries with content and metadata
        """
        if not self._initialized and not self.initialize():
            return []

        try:
            embedding = self._embed_model.get_text_embedding(query)
            results = self._query_chromadb(embedding, n_results)

            if not results:
                return []

            formatted = []
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                item = self._format_result_item(doc, meta, dist)
                if item["score"] >= score_threshold:
                    formatted.append(item)

            return formatted

        except Exception as e:
            logger.error("Documentation search failed: %s", e)
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
_doc_searcher: Optional[DocumentationSearcher] = None
_doc_searcher_lock = threading.Lock()


def get_documentation_searcher() -> DocumentationSearcher:
    """Get or create the global documentation searcher instance (thread-safe)."""
    global _doc_searcher
    if _doc_searcher is None:
        with _doc_searcher_lock:
            # Double-check after acquiring lock
            if _doc_searcher is None:
                _doc_searcher = DocumentationSearcher()
    return _doc_searcher
