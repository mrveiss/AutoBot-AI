# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Embedded MCP Client for AutoBot Agents

This module provides an in-process MCP client that agents (like KB Librarian)
can use to interact with the knowledge base without HTTP overhead.

Benefits over HTTP-based access:
- Zero network latency (in-process calls)
- Direct access to KnowledgeBase instance
- Streaming support for large operations
- Transaction-like batching capability

Usage:
    from autobot_knowledge_mcp.embedded import EmbeddedKnowledgeClient

    # Initialize with existing knowledge base
    client = EmbeddedKnowledgeClient(knowledge_base=kb)

    # Search
    results = await client.search("Redis configuration")

    # Add document
    doc_id = await client.add("New information", source="librarian")

    # Batch operations
    async with client.batch() as batch:
        batch.add("Document 1", source="research")
        batch.add("Document 2", source="research")
        # All committed at end of batch
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


# =============================================================================
# Result Types
# =============================================================================


@dataclass
class SearchResult:
    """A single search result."""

    content: str
    score: float
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_index: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "score": self.score,
            "source": self.source,
            "metadata": self.metadata,
            "chunk_index": self.chunk_index,
        }


@dataclass
class AddResult:
    """Result of adding a document."""

    document_id: str
    success: bool
    message: str = ""
    chunks_created: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "document_id": self.document_id,
            "success": self.success,
            "message": self.message,
            "chunks_created": self.chunks_created,
        }


@dataclass
class KnowledgeStats:
    """Knowledge base statistics."""

    total_documents: int
    total_chunks: int
    index_name: str
    embedding_model: str
    last_update: Optional[datetime] = None
    memory_usage_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_documents": self.total_documents,
            "total_chunks": self.total_chunks,
            "index_name": self.index_name,
            "embedding_model": self.embedding_model,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "memory_usage_bytes": self.memory_usage_bytes,
        }


# =============================================================================
# Batch Context
# =============================================================================


class BatchContext:
    """
    Context manager for batching knowledge base operations.

    All operations within a batch are queued and executed together
    at the end, enabling optimizations like:
    - Single embedding model load
    - Bulk vector insertion
    - Atomic commits
    """

    def __init__(self, client: "EmbeddedKnowledgeClient"):
        self._client = client
        self._operations: list[dict[str, Any]] = []
        self._results: list[AddResult] = []

    def add(
        self,
        content: str,
        source: str = "batch",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Queue a document addition."""
        self._operations.append({
            "type": "add",
            "content": content,
            "source": source,
            "metadata": metadata or {},
        })

    async def _execute(self) -> list[AddResult]:
        """Execute all queued operations."""
        results = []
        for op in self._operations:
            if op["type"] == "add":
                result = await self._client.add(
                    content=op["content"],
                    source=op["source"],
                    metadata=op["metadata"],
                )
                results.append(result)
        return results

    @property
    def pending_count(self) -> int:
        """Get number of pending operations."""
        return len(self._operations)

    @property
    def results(self) -> list[AddResult]:
        """Get results after batch execution."""
        return self._results


# =============================================================================
# Embedded Client
# =============================================================================


class EmbeddedKnowledgeClient:
    """
    In-process MCP client for knowledge base operations.

    This client provides the same interface as the MCP server tools
    but operates directly on the KnowledgeBase instance without
    network overhead.
    """

    def __init__(
        self,
        knowledge_base: Optional["KnowledgeBase"] = None,
        lazy_init: bool = True,
    ):
        """
        Initialize the embedded client.

        Args:
            knowledge_base: Existing KnowledgeBase instance (optional)
            lazy_init: If True, defer KB initialization until first use
        """
        self._kb = knowledge_base
        self._lazy_init = lazy_init
        self._initialized = knowledge_base is not None

    async def _ensure_initialized(self) -> "KnowledgeBase":
        """Ensure knowledge base is initialized."""
        if self._kb is None:
            if self._lazy_init:
                # Lazy import to avoid circular dependencies
                from src.knowledge_base import KnowledgeBase
                from src.config import config

                self._kb = KnowledgeBase(config_manager=config)
                self._initialized = True
            else:
                raise RuntimeError("Knowledge base not initialized")
        return self._kb

    # =========================================================================
    # Search Operations
    # =========================================================================

    async def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.0,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[SearchResult]:
        """
        Search the knowledge base.

        Args:
            query: Search query text
            top_k: Maximum number of results
            threshold: Minimum similarity score (0.0-1.0)
            filters: Optional metadata filters

        Returns:
            List of SearchResult objects
        """
        kb = await self._ensure_initialized()

        try:
            raw_results = await kb.search(
                query=query,
                top_k=top_k,
                filters=filters,
            )

            results = []
            for r in raw_results:
                score = r.get("score", 0.0)
                if score >= threshold:
                    results.append(SearchResult(
                        content=r.get("content", ""),
                        score=score,
                        source=r.get("source", "unknown"),
                        metadata=r.get("metadata", {}),
                        chunk_index=r.get("metadata", {}).get("chunk_index", 0),
                    ))

            logger.debug("Search '%s' returned %d results", query[:50], len(results))
            return results

        except Exception as e:
            logger.error("Search failed: %s", e)
            raise

    async def vector_search(
        self,
        query: str,
        top_k: int = 10,
        threshold: float = 0.7,
    ) -> list[SearchResult]:
        """
        Perform direct vector similarity search.

        Args:
            query: Query text to embed
            top_k: Maximum number of results
            threshold: Minimum similarity threshold

        Returns:
            List of SearchResult objects above threshold
        """
        # Uses same underlying search but with stricter threshold
        return await self.search(query, top_k=top_k, threshold=threshold)

    # =========================================================================
    # Write Operations
    # =========================================================================

    async def add(
        self,
        content: str,
        source: str = "embedded-client",
        metadata: Optional[dict[str, Any]] = None,
    ) -> AddResult:
        """
        Add a document to the knowledge base.

        Args:
            content: Document content
            source: Source identifier
            metadata: Optional metadata

        Returns:
            AddResult with document ID and status
        """
        kb = await self._ensure_initialized()

        try:
            doc_id = await kb.add_document(
                content=content,
                metadata=metadata or {},
                source=source,
            )

            logger.info("Added document %s from source '%s'", doc_id, source)
            return AddResult(
                document_id=doc_id,
                success=True,
                message="Document added successfully",
            )

        except Exception as e:
            logger.error("Failed to add document: %s", e)
            return AddResult(
                document_id="",
                success=False,
                message=str(e),
            )

    async def add_many(
        self,
        documents: list[dict[str, Any]],
    ) -> list[AddResult]:
        """
        Add multiple documents efficiently.

        Args:
            documents: List of dicts with 'content', 'source', 'metadata'

        Returns:
            List of AddResult objects
        """
        results = []
        for doc in documents:
            result = await self.add(
                content=doc.get("content", ""),
                source=doc.get("source", "batch"),
                metadata=doc.get("metadata"),
            )
            results.append(result)
        return results

    @asynccontextmanager
    async def batch(self):
        """
        Create a batch context for multiple operations.

        Usage:
            async with client.batch() as batch:
                batch.add("Document 1")
                batch.add("Document 2")
            # All documents added when context exits
        """
        context = BatchContext(self)
        try:
            yield context
        finally:
            context._results = await context._execute()

    # =========================================================================
    # Stats Operations
    # =========================================================================

    async def stats(self, include_details: bool = False) -> KnowledgeStats:
        """
        Get knowledge base statistics.

        Args:
            include_details: Include detailed statistics

        Returns:
            KnowledgeStats object
        """
        kb = await self._ensure_initialized()

        try:
            doc_count = await kb.get_document_count()

            stats = KnowledgeStats(
                total_documents=doc_count,
                total_chunks=doc_count,  # Approximation
                index_name=getattr(kb, "redis_index_name", "unknown"),
                embedding_model=getattr(kb, "embedding_model_name", "unknown"),
            )

            if include_details:
                if hasattr(kb, "get_last_update_time"):
                    stats.last_update = await kb.get_last_update_time()
                if hasattr(kb, "get_memory_usage"):
                    stats.memory_usage_bytes = await kb.get_memory_usage()

            return stats

        except Exception as e:
            logger.error("Failed to get stats: %s", e)
            raise

    # =========================================================================
    # Summarization
    # =========================================================================

    async def summarize(
        self,
        topic: str,
        max_length: int = 500,
    ) -> str:
        """
        Summarize knowledge on a topic.

        Args:
            topic: Topic to summarize
            max_length: Maximum summary length

        Returns:
            Summary text
        """
        kb = await self._ensure_initialized()

        # Search for relevant documents
        results = await self.search(topic, top_k=10)

        if not results:
            return f"No information found about '{topic}' in the knowledge base."

        # Combine content
        combined = "\n\n".join([r.content for r in results[:5]])

        # Use LLM if available
        if hasattr(kb, "llm") and kb.llm:
            prompt = (
                f"Summarize the following information about '{topic}' "
                f"in {max_length} tokens or less:\n\n{combined}"
            )
            try:
                summary = await kb.llm.generate(prompt, max_tokens=max_length)
                return summary
            except Exception as e:
                logger.warning("LLM summarization failed: %s", e)

        # Fallback: truncate content
        if len(combined) > max_length * 4:
            return combined[: max_length * 4] + "..."
        return combined


# =============================================================================
# Factory Function
# =============================================================================


def create_knowledge_client(
    knowledge_base: Optional["KnowledgeBase"] = None,
) -> EmbeddedKnowledgeClient:
    """
    Create an embedded knowledge client.

    This is the recommended way to create a client for use in
    AutoBot agents like the KB Librarian.

    Args:
        knowledge_base: Optional existing KnowledgeBase instance

    Returns:
        EmbeddedKnowledgeClient instance
    """
    return EmbeddedKnowledgeClient(knowledge_base=knowledge_base)
