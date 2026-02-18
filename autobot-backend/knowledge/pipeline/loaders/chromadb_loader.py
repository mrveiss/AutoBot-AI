# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ChromaDB Loader - Load chunks and summaries with embeddings to ChromaDB.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import logging
from typing import Any, List, Optional

from backend.knowledge.pipeline.base import BaseLoader, PipelineContext
from backend.knowledge.pipeline.models.chunk import ProcessedChunk
from backend.knowledge.pipeline.models.summary import Summary
from backend.knowledge.pipeline.registry import TaskRegistry
from backend.utils.async_chromadb_client import get_async_chromadb_client

logger = logging.getLogger(__name__)


@TaskRegistry.register_loader("chromadb")
class ChromaDBLoader(BaseLoader):
    """Load chunks and summaries with embeddings to ChromaDB."""

    def __init__(
        self,
        collection_name: str = "knowledge_vectors",
        summary_collection_name: str = "knowledge_summaries",
        batch_size: int = 100,
        load_summaries: bool = True,
    ) -> None:
        """
        Initialize ChromaDB loader.

        Args:
            collection_name: ChromaDB collection for chunks
            summary_collection_name: ChromaDB collection for summaries
            batch_size: Batch size for upserts
            load_summaries: Whether to load summary embeddings
        """
        self.collection_name = collection_name
        self.summary_collection_name = summary_collection_name
        self.batch_size = batch_size
        self.load_summaries = load_summaries
        self.client: Optional[Any] = None

    async def load(self, context: PipelineContext) -> None:
        """
        Load chunks and summaries to ChromaDB.

        Args:
            context: Pipeline context with processed data
        """
        self.client = await get_async_chromadb_client()

        chunks: List[ProcessedChunk] = context.chunks
        if chunks:
            await self._load_chunks(chunks)

        if self.load_summaries:
            summaries: List[Summary] = context.summaries
            if summaries:
                await self._load_summaries(summaries)

        logger.info(
            f"Loaded {len(chunks)} chunks, "
            f"{len(context.summaries)} summaries to ChromaDB"
        )

    async def _load_chunks(self, chunks: List[ProcessedChunk]) -> None:
        """Load chunks to ChromaDB collection."""
        try:
            collection = await self.client.get_or_create_collection(
                name=self.collection_name
            )

            for i in range(0, len(chunks), self.batch_size):
                batch = chunks[i : i + self.batch_size]
                await self._upsert_chunk_batch(collection, batch)

            logger.info("Loaded %s chunks to ChromaDB", len(chunks))
        except Exception as e:
            logger.error("Failed to load chunks to ChromaDB: %s", e)

    async def _upsert_chunk_batch(
        self, collection: Any, chunks: List[ProcessedChunk]
    ) -> None:
        """Upsert a batch of chunks."""
        ids = [str(chunk.id) for chunk in chunks]
        documents = [chunk.content for chunk in chunks]
        metadatas = [
            {
                "document_id": str(chunk.document_id),
                "chunk_index": chunk.chunk_index,
                "document_type": chunk.document_type,
                **chunk.metadata,
            }
            for chunk in chunks
        ]

        await collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    async def _load_summaries(self, summaries: List[Summary]) -> None:
        """Load summaries to ChromaDB collection."""
        try:
            collection = await self.client.get_or_create_collection(
                name=self.summary_collection_name
            )

            for i in range(0, len(summaries), self.batch_size):
                batch = summaries[i : i + self.batch_size]
                await self._upsert_summary_batch(collection, batch)

            logger.info("Loaded %s summaries to ChromaDB", len(summaries))
        except Exception as e:
            logger.error("Failed to load summaries to ChromaDB: %s", e)

    async def _upsert_summary_batch(
        self, collection: Any, summaries: List[Summary]
    ) -> None:
        """Upsert a batch of summaries."""
        ids = [str(summary.id) for summary in summaries]
        documents = [summary.content for summary in summaries]
        metadatas = [
            {
                "level": summary.level,
                "document_id": str(summary.source_document_id),
                "parent_summary_id": str(summary.parent_summary_id)
                if summary.parent_summary_id
                else None,
                "key_topics": ",".join(summary.key_topics),
                "word_count": summary.word_count,
            }
            for summary in summaries
        ]

        await collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
