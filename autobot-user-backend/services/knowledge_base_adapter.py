#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Adapter - Unified interface for KnowledgeBase V1 and V2.

This adapter resolves API differences between KnowledgeBase implementations,
providing a consistent interface for the RAG service layer.
"""

from typing import Any, List, Protocol

from backend.type_defs.common import Metadata
from autobot_shared.logging_manager import get_llm_logger

logger = get_llm_logger("knowledge_base_adapter")


class KnowledgeBaseProtocol(Protocol):
    """Protocol defining the expected interface for knowledge base implementations."""

    async def search(self, query: str, **kwargs) -> List[Metadata]:
        """Search for documents matching the query."""
        ...

    async def get_stats(self) -> Metadata:
        """Get knowledge base statistics."""
        ...

    async def get_all_facts(self) -> List[Metadata]:
        """Get all facts from the knowledge base."""
        ...


class KnowledgeBaseAdapter:
    """
    Adapter providing unified interface for different KnowledgeBase implementations.

    Handles differences between:
    - KnowledgeBase V1: Uses 'similarity_top_k' parameter
    - KnowledgeBase V2: Uses 'top_k' parameter

    This ensures the RAG optimizer can work with any KB implementation without
    knowing the specific version or method signatures.
    """

    def __init__(self, knowledge_base: Any):
        """
        Initialize adapter with a knowledge base instance.

        Args:
            knowledge_base: Instance of KnowledgeBase or KnowledgeBaseV2
        """
        self.kb = knowledge_base
        self.kb_type = knowledge_base.__class__.__name__
        logger.info("KnowledgeBaseAdapter initialized with %s", self.kb_type)

    async def search(
        self,
        query: str,
        top_k: int = 10,
        mode: str = "auto",
        **kwargs,
    ) -> List[Metadata]:
        """
        Unified search interface that works with both KB implementations.

        Args:
            query: Search query string
            top_k: Number of results to return
            mode: Search mode (for V1 compatibility)
            **kwargs: Additional parameters passed through

        Returns:
            List of search results with consistent structure
        """
        try:
            if self.kb_type == "KnowledgeBaseV2":
                # V2 uses 'top_k' parameter
                results = await self.kb.search(query=query, top_k=top_k, **kwargs)
            else:
                # V1 uses 'similarity_top_k' parameter
                results = await self.kb.search(
                    query=query, similarity_top_k=top_k, mode=mode, **kwargs
                )

            # Normalize result format if needed
            normalized_results = self._normalize_results(results)

            logger.debug(
                f"Search completed: {len(normalized_results)} results for '{query[:50]}...'"
            )
            return normalized_results

        except Exception as e:
            logger.error("Search failed in %s: %s", self.kb_type, e)
            raise

    async def get_all_facts(self) -> List[Metadata]:
        """
        Get all facts from the knowledge base.

        Returns:
            List of all facts with metadata
        """
        try:
            facts = await self.kb.get_all_facts()
            logger.debug("Retrieved %s facts from %s", len(facts), self.kb_type)
            return facts
        except Exception as e:
            logger.error("Failed to get all facts: %s", e)
            raise

    async def get_stats(self) -> Metadata:
        """
        Get knowledge base statistics.

        Returns:
            Dictionary containing KB statistics
        """
        try:
            stats = await self.kb.get_stats()
            stats["kb_implementation"] = self.kb_type
            return stats
        except Exception as e:
            logger.error("Failed to get stats: %s", e)
            raise

    def _normalize_results(self, results: List[Any]) -> List[Metadata]:
        """
        Normalize search results to consistent format.

        Ensures all results have required fields:
        - content: The text content
        - metadata: Additional metadata
        - score: Relevance score (if available)

        Args:
            results: Raw results from knowledge base

        Returns:
            Normalized list of result dictionaries
        """
        normalized = []

        for result in results:
            # Handle different result formats
            if isinstance(result, dict):
                # Already a dictionary, ensure required fields
                normalized_result = {
                    "content": result.get("content", result.get("text", "")),
                    "metadata": result.get("metadata", {}),
                    "score": result.get("score", result.get("similarity", 0.0)),
                }

                # Preserve additional fields
                for key, value in result.items():
                    if key not in normalized_result:
                        normalized_result[key] = value

                normalized.append(normalized_result)
            else:
                # Handle other formats (objects, tuples, etc.)
                logger.warning("Unexpected result type: %s", type(result))
                normalized.append(
                    {"content": str(result), "metadata": {}, "score": 0.0}
                )

        return normalized

    @property
    def implementation_type(self) -> str:
        """Get the knowledge base implementation type."""
        return self.kb_type
